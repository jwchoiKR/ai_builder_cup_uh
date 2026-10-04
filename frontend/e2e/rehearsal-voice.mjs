// Voice rehearsal against real Speech-to-Text and real models (DEV_SPEC §14.3, §14.5).
// Host sentences are synthesized with Windows SAPI (en-US voice), streamed as 16 kHz PCM at real-time
// pace through the same audio WebSocket the browser microphone uses; a host page is open in Edge so the
// render acknowledgements are real. The backend must run with LLM_PROVIDER=vertex and STT_PROVIDER=google_v2.
//
//   node e2e/rehearsal-voice.mjs alerts            10 HIGH-risk sentences (P4 latency check)
//   node e2e/rehearsal-voice.mjs script [runs]     the full host script with bursts (P5 rehearsal)
//   node e2e/rehearsal-voice.mjs lines <file> [runs]  proof-plan §2: each JSONL line (id, text, product, kind
//                                                  compliance|fact, ...) on its product; per-stage times per kind
// Writes a JSON report to ../docs/rehearsal-<mode>.json and prints a summary.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
// Behind IAP (Cloud Run), scripts need an identity token: IAP_TOKEN="$(gcloud auth print-identity-token)"
// for an account the IAP policy allows. It is sent on API calls, the audio WebSocket and the page.
const AUTH = process.env.IAP_TOKEN ? { Authorization: `Bearer ${process.env.IAP_TOKEN}` } : {};
const MODE = process.argv[2] ?? "alerts";
const LINES_FILE = MODE === "lines" ? process.argv[3] : null;
const RUNS = Number(process.argv[MODE === "lines" ? 4 : 3] ?? 1);
const WITHIN_MS = 3000; // proof-plan §2: shown correctly within 3 s of the end of speech
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
    method, headers: { "Content-Type": "application/json", ...AUTH }, body: body ? JSON.stringify(body) : undefined,
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
    this.ws = new WebSocket(`${BASE.replace("http", "ws")}/api/sessions/${sid}/audio`,
      process.env.IAP_TOKEN ? { headers: AUTH } : undefined);
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

/** The first rendered compliance alert raised by any final of the line (a split line can alert on the
 *  first fragment, or under the merged text of the later one), plus the state for per-final records. */
async function alertForLine(sid, transcriptIds, ms = 10000, kind = "compliance") {
  const ids = new Set(transcriptIds);
  const until = Date.now() + ms;
  let st = null;
  let shownSince = null;
  while (Date.now() < until) {
    st = await api("GET", `/sessions/${sid}/state?role=operator`);
    const mine = st.alerts.filter((x) => ids.has(x.transcript_id) && x.kind === kind && x.shown_at);
    const rendered = mine.filter((x) => x.host_rendered_at).sort((a, b) => a.shown_at - b.shown_at);
    if (rendered.length) return { alert: rendered[0], state: st };
    // shown but no render ack within 3 s (a screen without acks for this alert type): keep the alert
    if (mine.length && (shownSince ??= Date.now()) < Date.now() - 3000) {
      return { alert: mine.sort((a, b) => a.shown_at - b.shown_at)[0], state: st };
    }
    await sleep(200);
  }
  return { alert: null, state: st ?? (await api("GET", `/sessions/${sid}/state?role=operator`)) };
}

/** Every final of the line with its compliance verdict and fact claims (agent outputs) and the alerts it raised. */
function perFinal(state, finals) {
  return finals.map((f) => {
    const call = state.agent_calls?.find((c) => c.agent === "compliance_judge" && c.input_preview === f.text);
    const facts = state.agent_calls?.find((c) => c.agent === "fact_checker" && c.input_preview === f.text);
    return {
      text: f.text,
      transcript_id: f.transcript_id ?? null,
      verdict: call?.output?.compliance?.violations?.map((v) => ({ rule: v.rule_id, negated: v.is_negated, quoted: v.is_quoted })) ?? null,
      claims: facts?.output?.claims?.map((c) => ({ field: c.field, verdict: c.verdict, stated: c.stated_value, correct: c.correct_value })) ?? null,
      alerts: state.alerts.filter((a) => a.transcript_id === f.transcript_id)
        .map((a) => ({ kind: a.kind, rule: a.rule_id, field: a.field, severity: a.severity, status: a.status })),
    };
  });
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
    const from = mic.finals.length; // review B6: captured before playback
    await mic.say(synth(line));
    const finals = await mic.finalsSince(from);
    let row = { line, finals: finals.map((f) => f.text) };
    const ids = finals.map((f) => f.transcript_id).filter(Boolean);
    if (ids.length) {
      const { alert, state } = await alertForLine(sid, ids);
      const t = alert ? state.transcripts.find((x) => x.transcript_id === alert.transcript_id) : null;
      row = {
        ...row, rule: alert?.rule_id ?? null, severity: alert?.severity ?? null,
        alert_on_final: alert ? ids.indexOf(alert.transcript_id) + 1 : null,
        stt_ms: t ? t.received_at - t.speech_end_at : null,
        server_ms: alert ? alert.shown_at - t.speech_end_at : null,
        render_ms: alert ? alert.host_rendered_at - t.speech_end_at : null,
        per_final: perFinal(state, finals),
      };
      for (const a of state.alerts.filter((x) => ids.includes(x.transcript_id) && x.status === "active")) {
        await api("POST", `/sessions/${sid}/alerts/${a.alert_id}/dismiss`);
      }
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
      const from = mic.finals.length; // review B6: captured before playback
      await mic.say(synth(s.text));
      await mic.finalsSince(from);
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

/** proof-plan §2: each line on its product; wait for the expected alert kind; per-stage times. */
async function runLines(page, lines) {
  const { session_id: sid } = await api("POST", "/demo/reset");
  await page.goto(`${BASE}/host?session=${sid}`);
  await api("POST", `/sessions/${sid}/start`);
  await sleep(2000);
  const mic = new Mic(sid);
  await mic.ready;
  const rows = [];
  for (const [i, line] of lines.entries()) {
    const st0 = await api("GET", `/sessions/${sid}/state?role=operator`);
    const onAir = st0.segments.find((x) => x.segment_id === st0.session.current_segment_id)?.product_id;
    if (onAir !== line.product) {
      await api("POST", `/sessions/${sid}/segments/switch`, { product_id: line.product });
      await sleep(500);
    }
    const from = mic.finals.length; // review B6: captured before playback
    await mic.say(synth(line.text));
    const finals = await mic.finalsSince(from);
    const ids = finals.map((f) => f.transcript_id).filter(Boolean);
    let row = { id: line.id, kind: line.kind, expected: line.rule_id ?? line.field ?? null, finals: finals.map((f) => f.text) };
    if (ids.length) {
      const { alert, state } = await alertForLine(sid, ids, 10000, line.kind);
      const t = alert ? state.transcripts.find((x) => x.transcript_id === alert.transcript_id) : null;
      const first = state.transcripts.find((x) => x.transcript_id === ids[0]);
      const got = alert ? (line.kind === "fact" ? alert.field : alert.rule_id) : null;
      row = {
        // an adjacent rule the label accepts (expected.also_ok_rule_ids) counts as correct, as in eval_adversarial
        ...row, got, correct: alert !== null && (row.expected === null || got === row.expected
          || (line.also_ok_rule_ids ?? line.expected?.also_ok_rule_ids ?? []).includes(got)),
        alert_on_final: alert ? ids.indexOf(alert.transcript_id) + 1 : null,
        stt_ms: first ? first.received_at - first.speech_end_at : null,
        server_ms: alert ? alert.shown_at - t.speech_end_at : null,
        render_ms: alert?.host_rendered_at ? alert.host_rendered_at - t.speech_end_at : null,
        per_final: perFinal(state, finals),
      };
      for (const a of state.alerts.filter((x) => ids.includes(x.transcript_id) && x.status === "active")) {
        await api("POST", `/sessions/${sid}/alerts/${a.alert_id}/dismiss`);
      }
    } else {
      row = { ...row, got: null, correct: false, stt_ms: null, server_ms: null, render_ms: null, per_final: [] };
    }
    rows.push(row);
    console.log(`${i + 1}/${lines.length} ${row.id} ${row.kind} ${row.correct ? "ok" : "MISS"} ${row.got ?? "-"} render ${row.render_ms ?? "-"} ms`);
    await sleep(1500);
  }
  mic.close();
  await api("POST", `/sessions/${sid}/end`).catch(() => undefined);
  return { sid, rows };
}

function pct(values, q) {
  const v = values.filter((x) => x !== null && x !== undefined).sort((a, b) => a - b);
  return v.length ? v[Math.min(v.length - 1, Math.ceil(q * v.length) - 1)] : null;
}

/** Per kind: p50/p95/max per stage, misses, and the share shown correctly within 3 s (render time). */
function summarizeLines(results) {
  const rows = results.flatMap((r) => r.rows);
  const out = {};
  for (const kind of ["compliance", "fact"]) {
    const k = rows.filter((x) => x.kind === kind);
    if (!k.length) continue;
    const stage = (name) => ({ p50: pct(k.map((x) => x[name]), 0.5), p95: pct(k.map((x) => x[name]), 0.95),
      max: pct(k.map((x) => x[name]), 1) });
    out[kind] = {
      lines: k.length, stt_ms: stage("stt_ms"), server_ms: stage("server_ms"), render_ms: stage("render_ms"),
      misses: k.filter((x) => x.got === null).map((x) => x.id),
      wrong: k.filter((x) => x.got !== null && !x.correct).map((x) => `${x.id}: ${x.got} (expected ${x.expected})`),
      within_3s: k.filter((x) => x.correct && x.render_ms !== null && x.render_ms <= WITHIN_MS).length / k.length,
      // an alert of the right kind on screen within 3 s, whatever its rule or field
      kind_within_3s: k.filter((x) => x.got !== null && x.render_ms !== null && x.render_ms <= WITHIN_MS).length / k.length,
    };
  }
  return out;
}

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "msedge" });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, extraHTTPHeaders: AUTH });
const results = [];
for (let r = 1; r <= RUNS; r++) {
  console.log(`== ${MODE} run ${r}`);
  if (MODE === "alerts") results.push(await runAlerts(page));
  else if (MODE === "lines") {
    const lines = readFileSync(LINES_FILE, "utf-8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
    results.push(await runLines(page, lines));
  } else {
    const op = r === RUNS ? await browser.newPage({ viewport: { width: 1920, height: 1080 } }) : null;
    results.push(await runScript(page, op));
  }
}
await browser.close();
const out = join(DOCS, `rehearsal-${MODE}.json`);
if (MODE === "lines") {
  const summary = summarizeLines(results);
  writeFileSync(out, JSON.stringify({ file: LINES_FILE, runs: RUNS, summary, results }, null, 1));
  console.log(JSON.stringify(summary, null, 1));
} else writeFileSync(out, JSON.stringify(results, null, 1));
console.log(`report: ${out}`);
