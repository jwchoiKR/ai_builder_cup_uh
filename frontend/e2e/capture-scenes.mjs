// Capture one screenshot per demo scene (DEV_SPEC §15 P3 "done when").
// Backend must run with LLM_PROVIDER=mock, STT_PROVIDER=mock and serve frontend/dist on BASE.
//   node e2e/capture-scenes.mjs            (BASE defaults to http://127.0.0.1:8000)
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
const OUT = resolve(process.env.OUT ?? "../docs/screens");
mkdirSync(OUT, { recursive: true });

async function api(method, path, body) {
  const r = await fetch(`${BASE}/api${path}`, {
    method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const script = (await api("GET", "/demo/script")).steps;
const lines = script.filter((s) => s.action === "host_line");
const session = await api("POST", "/demo/reset");
const sid = session.session_id;
const S = (p) => `/sessions/${sid}${p}`;
const say = (i) => api("POST", S("/transcripts"), { text: lines[i].text, scene: lines[i].scene });

// The bundled Chromium is blocked by OS policy on the dev machine; the installed Edge works.
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "msedge" });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(`${BASE}/studio?session=${sid}&layout=all`);
await page.waitForLoadState("networkidle");
// Standalone screens at their target sizes, for full-size shots of key moments.
const solo = {};
for (const [name, path, viewport] of [
  ["host", "host", { width: 1920, height: 1080 }],
  ["operator", "operator", { width: 1920, height: 1080 }],
  ["viewer", "viewer", { width: 430, height: 900 }],
]) {
  solo[name] = await browser.newPage({ viewport });
  await solo[name].goto(`${BASE}/${path}?session=${sid}`);
}
async function soloShot(screen, name) {
  await sleep(300);
  await solo[screen].screenshot({ path: `${OUT}/${name}.png` });
  console.log("captured", name);
}

const missing = [];
async function shot(name, waitText) {
  let note = "";
  if (waitText) {
    try {
      await page.getByText(waitText, { exact: false }).first().waitFor({ timeout: 20000 });
    } catch {
      missing.push(`${name}: "${waitText}"`);
      note = ` (MISSING "${waitText}")`;
    }
  }
  await sleep(600);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("captured", name + note);
}

await api("POST", S("/start"));
await shot("S02-start", "On air now");
await say(0); await sleep(1500);
await say(1); await sleep(1500);
await say(2); await shot("S02-points", "1 / 3 required points");

await api("POST", S("/feed/burst/B1"));
await sleep(11000); await shot("S03-price-questions", "AI answer");
await api("POST", S("/feed/burst/B2"));
await sleep(11000); await shot("S04-grouping", "SUGGESTED ANSWER");
await soloShot("host", "full-host-S04-questions");

await say(3); await shot("S05-posting", "Posting answer");
await sleep(2500); await shot("S05-host-answer", "Host answer");

await say(4); await shot("S06-fact-error", "Price correction");
await say(5); await sleep(2500); await shot("S06-corrected");

await say(6); await shot("S07-compliance", "Regulation");
await soloShot("host", "full-host-S07-compliance");
await sleep(5500); await shot("S07-not-corrected", "Not corrected");
await say(7); await shot("S07-corrected", "Corrected");
await sleep(2500);

await say(8); await sleep(2500); await shot("S08-negation");

await api("POST", S("/feed/burst/B3"));
await sleep(11000); await shot("S09-sensitive", "Needs review");
await soloShot("operator", "full-operator-S09-desk");

await say(9); await shot("S10-points", "3 / 3 required points");

await api("POST", S("/promos/promo_time_sale_10/start"));
await shot("S11-time-sale", "TIME SALE");
await soloShot("viewer", "full-viewer-S11-time-sale");
await api("POST", S("/feed/burst/B4"));
await sleep(6000); await shot("S11-promo-answers", "S$32.40");

await say(10); await sleep(2000);
await api("POST", S("/feed/burst/B5"));
await say(11); await sleep(2000); await shot("S12-cue-1", "switch cue 1/2");
await say(12); await shot("S12-switching", "Switching to Deep Hydration Ampoule");
await soloShot("host", "full-host-S12-switching");
await sleep(6000); await shot("S12-switched", "End of run sheet");
await sleep(16000); await shot("S12-b5");

await say(13); await shot("S13-fact-error", "Ingredient amount correction");
await say(14); await sleep(2500); await shot("S13-corrected");

await browser.close();
console.log(missing.length ? `MISSING:\n${missing.join("\n")}` : "all expected texts found");
process.exit(missing.length ? 1 : 0);
