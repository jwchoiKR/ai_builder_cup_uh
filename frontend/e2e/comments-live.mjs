// Browser end-to-end check of the comment path on the running server (real models): a viewer types, the reply
// appears; the operator approves a waiting question and answers a no-source one; the viewer sees both.
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = "http://127.0.0.1:8010";
const SHOTS = "../.eval_out/e2e-comments/"; // run from frontend/: node e2e/comments-live.mjs (server on :8010, VIEWER_INPUT_ENABLED=true)
fs.mkdirSync(SHOTS, { recursive: true });
const api = async (method, path, body) => {
  const r = await fetch(`${BASE}/api${path}`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  return r.json();
};
const results = [];
const step = async (name, fn) => {
  const t0 = Date.now();
  try { const info = await fn(); results.push({ name, ok: true, sec: ((Date.now() - t0) / 1000).toFixed(1), info }); console.log("PASS", name, ((Date.now() - t0) / 1000).toFixed(1) + "s", info ?? ""); }
  catch (e) { results.push({ name, ok: false, error: String(e).split("\n")[0] }); console.log("FAIL", name, String(e).split("\n")[0]); }
};
const s = await api("POST", "/demo/sessions", { show_mode: "team" });
const sid = s.session_id;
if (s.status !== "live") await api("POST", `/sessions/${sid}/start`);
await new Promise((r) => setTimeout(r, 6000));
console.log("session", sid);

const browser = await chromium.launch({ channel: "msedge" });
const viewer = await (await browser.newContext({ viewport: { width: 480, height: 900 } })).newPage();
const operator = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
await viewer.goto(`${BASE}/viewer?session=${sid}`);
await operator.goto(`${BASE}/operator?session=${sid}`);
const input = viewer.getByTestId("viewer-input");
const say = async (text) => { await input.fill(text); await input.press("Enter"); await viewer.locator('[data-testid^="viewer-comment-"]', { hasText: text }).first().waitFor({ timeout: 15000 }); };
const reply = (text) => viewer.locator('[data-testid^="viewer-reply-"]', { hasText: text });
const row = (text) => operator.locator('[data-testid^="op-group-"]', { hasText: text });

await step("viewer joins the chat", async () => { await input.waitFor({ timeout: 20000 }); await input.fill("Mina"); await input.press("Enter"); });

await step("plain fact: answered by itself (price)", async () => {
  await say("how much is the cream?");
  const r = reply("S$36"); await r.first().waitFor({ timeout: 60000 });
  const kind = await r.first().getAttribute("data-kind");
  if (kind !== "ai_answer") throw new Error("kind " + kind);
  if (await viewer.getByTestId("viewer-source").count()) throw new Error("sources shown to the viewer");
  return (await r.first().innerText()).replace(/\s+/g, " ").slice(0, 140);
});

await step("health question: no automatic reply, waits for a person with a suggested reply", async () => {
  await say("can i use it while pregnant?");
  const g = row("pregnan"); await g.first().waitFor({ timeout: 60000 });
  await g.first().click();
  const box = operator.locator('[data-testid^="op-reply-"] textarea').first(); await box.waitFor({ timeout: 60000 });
  await operator.waitForFunction(() => { const t = document.querySelector('[data-testid^="op-reply-"] textarea'); return t && t.value.trim().length > 0; }, null, { timeout: 60000 });
  const suggestion = await box.inputValue();
  if (await viewer.locator('[data-testid^="viewer-reply-"]', { hasText: /pregnan|doctor/i }).count()) throw new Error("posted without approval");
  await operator.screenshot({ path: SHOTS + "operator-approval.png" });
  return "suggested: " + suggestion.slice(0, 120);
});

await step("operator posts the suggested reply; the viewer sees it", async () => {
  await operator.locator('[data-testid^="op-reply-"]').first().getByRole("button", { name: "Post", exact: true }).click();
  const r = viewer.locator('[data-testid^="viewer-reply-"]', { hasText: /doctor|pregnan/i }); await r.first().waitFor({ timeout: 30000 });
  return (await r.first().getAttribute("data-kind")) + ": " + (await r.first().innerText()).replace(/\s+/g, " ").slice(0, 120);
});

await step("outside the product: no source, standard reply offered and posted", async () => {
  await say("do you ship to malaysia?");
  const g = row("Malaysia"); await g.first().waitFor({ timeout: 60000 });
  await g.first().click();
  const note = operator.locator('[data-testid^="op-no-source-"]'); await note.first().waitFor({ timeout: 60000 });
  const box = operator.locator('[data-testid^="op-reply-"] textarea').first();
  const text = await box.inputValue();
  if (!text.startsWith("That isn't covered in our product information")) throw new Error("box: " + text.slice(0, 60));
  await operator.screenshot({ path: SHOTS + "operator-no-source.png" });
  await operator.locator('[data-testid^="op-reply-"]').first().getByRole("button", { name: "Post", exact: true }).click();
  const r = reply("That isn't covered in our product information"); await r.first().waitFor({ timeout: 30000 });
  if (await viewer.getByText("No source:").count()) throw new Error("internal note visible to the viewer");
  return await r.first().getAttribute("data-kind");
});

await step("reaction: no reply; insult: hidden from other viewers", async () => {
  await say("so pretty!! love it");
  await say("you are all idiots");
  await new Promise((r) => setTimeout(r, 15000));
  const st = await api("GET", `/sessions/${sid}/state?role=viewer`);
  const texts = st.comments.map((c) => c.text ?? "");
  if (texts.some((t) => t.includes("idiots"))) throw new Error("hidden comment in the viewer state");
  const op = await api("GET", `/sessions/${sid}/state?role=operator`);
  const k = Object.fromEntries(op.comments.map((c) => [c.text, c.kind + "/" + c.visibility]));
  return JSON.stringify({ pretty: k["so pretty!! love it"], idiots: k["you are all idiots"] });
});

await step("other language: answered, with the reply in the asker's language", async () => {
  await say("크림 용량이 얼마예요?");
  const r = viewer.locator('[data-testid^="viewer-reply-"]', { hasText: /50\s?mL/i }); await r.first().waitFor({ timeout: 60000 });
  const tr = viewer.locator('[data-testid^="viewer-reply-translation-"]'); await tr.first().waitFor({ timeout: 30000 });
  return (await tr.first().innerText()).slice(0, 80);
});

await step("no category strip on the operator desk", async () => {
  if (await operator.getByTestId("op-desk-categories").count()) throw new Error("strip visible");
});

await viewer.screenshot({ path: SHOTS + "viewer.png", fullPage: true });
await operator.screenshot({ path: SHOTS + "operator-end.png" });
const health = await api("GET", "/health");
console.log("firestore:", JSON.stringify(Object.values(health).map((v) => v?.store_status?.comments).find(Boolean)));
console.log(`RESULT ${results.filter((r) => r.ok).length}/${results.length} passed | session ${sid}`);
fs.writeFileSync(SHOTS + "result.json", JSON.stringify({ sid, results }, null, 2));
await browser.close();
