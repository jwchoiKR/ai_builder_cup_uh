// Voice rehearsal against real Speech-to-Text and real models (DEV_SPEC §14.3, §14.5).
// Host sentences are synthesized with Windows SAPI (en-US voice), streamed as 16 kHz PCM at real-time
// pace through the same audio WebSocket the browser microphone uses; a host page is open in Edge so the
// render acknowledgements are real. The backend must run with LLM_PROVIDER=vertex and STT_PROVIDER=google_v2.
//
//   node e2e/rehearsal-voice.mjs alerts            10 HIGH-risk sentences (P4 latency check)
//   node e2e/rehearsal-voice.mjs script [runs]     the full host script with bursts (P5 rehearsal)
// Writes a JSON report to ../docs/rehearsal-<mode>-<n>.json and prints a summary.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
const MODE = process.argv[2] ?? "alerts";
const RUNS = Number(process.argv[3] ?? 1);
const VOICE_DIR = join(tmpdir(), "live-studio-voice");
const DOCS = resolve(process.env.DOCS ?? "../docs");
mkdirSync(VOICE_DIR, { recursive: true });

const ALERT_LINES = [
  "Use it every night and your wrinkles will disappear overnight.",
  "This cream literally cures eczema.",
  "The ampoule treats acne, so you'll never break out again.",
  "Once you use it, the results are permanent.",
  "It regenerates your skin cells from the inside.",
  "It even removes your old acne scars.",
  "It's totally safe for pregnant women, don't worry.",
  "You'll look ten years younger after one bottle.",
  "It kills the bacteria on your skin.",
  "It's a hundred ml tube, so it lasts forever.",
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(method, path, body) {
  const r = await fetch(`${BASE}/api${path}`, {
    method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
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
    this.ws = new WebSocket(`${BASE.replace("http", "ws")}/api/sessions/${sid}/audio`);
    this.ws.binaryType = "arraybuffer";
    this.finals = [];
    this.ready = new Promise((res, rej) => {
      this.ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "status" && m.state === "listening") res();
        if (m.type === "status" && m.state === "error") rej(new Error(m.message));
        if (m.type === "final") this.finals.push(m);
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
  close() { clearInterval(this.pump); this.ws.send(JSON.stringify({ type: "stop" })); this.ws.close(); }
}

async function alertFor(sid, transcriptId, ms = 10000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    const st = await api("GET", `/sessions/${sid}/state?role=operator`);
    const a = st.alerts.find((x) => x.transcript_id === transcriptId && x.kind === "compliance" && x.status === "active");
    if (a && a.host_rendered_at) return { alert: a, state: st };
    await sleep(200);
  }
  return { alert: null, state: await api("GET", `/sessions/${sid}/state?role=operator`) };
}

async function runAlerts(page) {
  const { session_id: sid } = await api("POST", "/demo/reset");
  await page.goto(`${BASE}/host?session=${sid}`);
  await api("POST", `/sessions/${sid}/start`);
  await sleep(2000);
  const mic = new Mic(sid);
  await mic.ready;
  const rows = [];
  for (const [i, line] of ALERT_LINES.entries()) {
    await mic.say(synth(line));
    const got = await mic.waitFinal(mic.finals.length + 1);
    const final = mic.finals.at(-1);
    let row = { line, final: got ? final.text : null };
    if (got && final.transcript_id) {
      const { alert, state } = await alertFor(sid, final.transcript_id);
      const t = state.transcripts.find((x) => x.transcript_id === final.transcript_id);
      row = {
        ...row, rule: alert?.rule_id ?? null, severity: alert?.severity ?? null,
        stt_ms: t ? t.received_at - t.speech_end_at : null,
        server_ms: alert ? alert.shown_at - t.speech_end_at : null,
        render_ms: alert ? alert.host_rendered_at - t.speech_end_at : null,
      };
      if (alert) await api("POST", `/sessions/${sid}/alerts/${alert.alert_id}/dismiss`);
    }
    rows.push(row);
    console.log(`${i + 1}. ${JSON.stringify(row)}`);
    await sleep(1500);
  }
  mic.close();
  const metrics = await api("GET", `/sessions/${sid}/metrics`);
  return { sid, rows, metrics };
}

async function runScript(page, operatorPage) {
  const steps = (await api("GET", "/demo/script")).steps;
  const { session_id: sid } = await api("POST", "/demo/reset");
  await page.goto(`${BASE}/host?session=${sid}`);
  if (operatorPage) await operatorPage.goto(`${BASE}/operator?session=${sid}`);
  let mic = null;
  const log = [];
  for (const s of steps) {
    const t0 = Date.now();
    if (s.action === "start") {
      await api("POST", `/sessions/${sid}/start`);
      mic = new Mic(sid);
      await mic.ready;
      await sleep(2000);
    } else if (s.action === "host_line") {
      await mic.say(synth(s.text));
      await mic.waitFinal(mic.finals.length + 1);
      await sleep(s.scene === "S12" ? 1500 : 4000);
      if (operatorPage && s.scene === "S07" && s.text.startsWith("Let me correct")) {
        await sleep(5500); // let metrics.updated (every 5 s) carry the measured values
        await operatorPage.screenshot({ path: join(DOCS, "screens", "vertex-operator-metrics.png") });
        console.log("captured vertex-operator-metrics.png (after S07)");
      }
    } else if (s.action === "burst" || s.action === "arm_burst") {
      await api("POST", `/sessions/${sid}/feed/burst/${s.arg}`);
      if (s.action === "burst") await sleep(14000);
    } else if (s.action === "promo_start") {
      await api("POST", `/sessions/${sid}/promos/${s.arg}/start`);
      await sleep(1000);
    } else if (s.action === "auto") {
      await sleep(17000);
    } else if (s.action === "end") {
      mic?.close();
      await api("POST", `/sessions/${sid}/end`);
    }
    log.push({ scene: s.scene, action: s.action, text: s.action === "host_line" ? s.text : s.arg, ms: Date.now() - t0 });
  }
  const finals = mic ? mic.finals.map((f) => f.text) : [];
  await sleep(3000);
  const state = await api("GET", `/sessions/${sid}/state?role=operator`);
  const metrics = await api("GET", `/sessions/${sid}/metrics`);
  return { sid, finals, log, metrics, alerts: state.alerts, transcripts: state.transcripts, groups: state.groups.length };
}

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "msedge" });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const results = [];
for (let r = 1; r <= RUNS; r++) {
  console.log(`== ${MODE} run ${r}`);
  if (MODE === "alerts") results.push(await runAlerts(page));
  else {
    const op = r === RUNS ? await browser.newPage({ viewport: { width: 1920, height: 1080 } }) : null;
    results.push(await runScript(page, op));
  }
}
await browser.close();
const out = join(DOCS, `rehearsal-${MODE}.json`);
writeFileSync(out, JSON.stringify(results, null, 1));
console.log(`report: ${out}`);
