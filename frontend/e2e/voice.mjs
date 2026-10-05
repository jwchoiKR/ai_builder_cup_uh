// Shared by the voice drivers (rehearsal-voice.mjs, show-replay.mjs): API calls, Windows SAPI speech
// synthesis (en-US voice, 16 kHz mono PCM) and a microphone that streams it at real-time pace through the
// same audio WebSocket the browser uses. Behind IAP every call carries the token (IAP_TOKEN).
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const VOICE_DIR = join(tmpdir(), "live-studio-voice");
mkdirSync(VOICE_DIR, { recursive: true });

export function voiceTools({ base, auth }) {
  async function api(method, path, body) {
    const r = await fetch(`${base}/api${path}`, {
      method, headers: { "Content-Type": "application/json", ...auth }, body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
    return r.json();
  }

  function synth(text) {
    const file = join(VOICE_DIR, createHash("sha1").update(text).digest("hex").slice(0, 16) + ".wav");
    if (!existsSync(file)) {
      const ps = [
        "Add-Type -AssemblyName System.Speech;",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;",
        "$s.SelectVoice('Microsoft Zira Desktop');",
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);",
        `$s.SetOutputToWaveFile('${file}', $f);`,
        `$s.Speak('${text.replace(/'/g, "''")}');`,
        "$s.Dispose();",
      ].join(" ");
      execFileSync("powershell", ["-NoProfile", "-Command", ps]);
    }
    const wav = readFileSync(file);
    const dataAt = wav.indexOf("data") + 8; // PCM after the 'data' chunk header
    return wav.subarray(dataAt);
  }

  class Mic {
    constructor(sid) {
      // Node's WebSocket (undici) accepts extra headers in its options object
      this.ws = new WebSocket(`${base.replace("http", "ws")}/api/sessions/${sid}/audio`,
        auth.Authorization ? { headers: auth } : undefined);
      this.ws.binaryType = "arraybuffer";
      this.finals = [];
      this.ready = new Promise((res, rej) => {
        this.ws.onmessage = (e) => {
          const m = JSON.parse(e.data);
          if (m.type === "status" && m.state === "listening") res();
          if (m.type === "status" && m.state === "error") rej(new Error(m.message));
          if (m.type === "final") this.finals.push({ ...m, at: Date.now() }); // arrival, to match the spoken line
        };
        this.ws.onerror = () => rej(new Error("audio websocket error"));
      });
      this.silence = new Uint8Array(3200);
      this.pump = setInterval(() => { if (this.idle && this.ws.readyState === 1) this.ws.send(this.silence); }, 100);
      this.idle = true;
    }
    async say(pcm) {
      this.idle = false;
      const t0 = Date.now();
      for (let i = 0, n = 0; i < pcm.length; i += 3200, n++) {
        this.ws.send(pcm.subarray(i, i + 3200));
        const wait = t0 + (n + 1) * 100 - Date.now(); // real-time pace
        if (wait > 0) await sleep(wait);
      }
      this.idle = true; // silence keeps flowing like an open microphone
    }
    async waitFinal(count, ms = 15000) {
      const until = Date.now() + ms;
      while (this.finals.length < count && Date.now() < until) await sleep(100);
      return this.finals.length >= count;
    }
    /** Review B6: every final of one spoken line. `from` is the final count captured BEFORE playback;
     *  after the first new final, keep collecting until no new final arrives for `quietMs`. */
    async finalsSince(from, ms = 15000, quietMs = 1500) {
      if (!(await this.waitFinal(from + 1, ms))) return [];
      let n = this.finals.length;
      let quietUntil = Date.now() + quietMs;
      while (Date.now() < quietUntil) {
        await sleep(100);
        if (this.finals.length !== n) {
          n = this.finals.length;
          quietUntil = Date.now() + quietMs;
        }
      }
      return this.finals.slice(from);
    }
    close() { clearInterval(this.pump); this.ws.send(JSON.stringify({ type: "stop" })); this.ws.close(); }
  }

  /** A fresh session that deletes nobody else's (POST /demo/sessions, D-139); an older service without
   *  that endpoint falls back to /demo/reset, which drops the previous session. */
  async function newSession(body = {}) {
    try {
      return await api("POST", "/demo/sessions", body);
    } catch (e) {
      if (!String(e.message).includes("-> 404") && !String(e.message).includes("-> 405")) throw e;
      return api("POST", "/demo/reset", body);
    }
  }

  return { api, synth, Mic, newSession };
}
