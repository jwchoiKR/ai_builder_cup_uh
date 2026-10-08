// Live check of the post-broadcast comment analysis: comments in, End broadcast, the summary's "What viewers asked".
// Run from frontend/: node e2e/summary-live.mjs (server on :8010 with demo tools on)
import { chromium } from "playwright";
import fs from "node:fs";
const BASE = "http://127.0.0.1:8010";
const SHOTS = "../.eval_out/e2e-comments/";
fs.mkdirSync(SHOTS, { recursive: true });
const api = async (method, path, body) => (await fetch(`${BASE}/api${path}`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined })).json();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const s = await api("POST", "/demo/sessions", { show_mode: "team" });
const sid = s.session_id;
if (s.status !== "live") await api("POST", `/sessions/${sid}/start`);
await sleep(6000);
const SAY = [["Lee", "how much is the cream?"], ["Kumar", "price pls"], ["Mei", "can i use it while pregnant?"], ["Raj", "do you ship to malaysia"],
  ["Hana", "so pretty!! love it"], ["Tom", "you are all idiots"], ["Jin", "크림 용량이 얼마예요?"], ["Aisha", "is it ok for oily skin"],
  ["Nur", "can pay with paynow?"], ["Wei", "what is in it, got fragrance?"], ["Sara", "im breastfeeding, safe?"], ["Ben", "no sound leh"],
  ["Dan", "is there any discount now"], ["Yuki", "セットはいくらですか"]];
for (const [i, [author, text]] of SAY.entries()) { await api("POST", `/sessions/${sid}/demo/comments`, { author, text }); await sleep(i === 4 ? 65000 : 1500); } // one pause, so the timeline has more than one bar
for (let i = 0; i < 40; i++) {
  const st = await api("GET", `/sessions/${sid}/state?role=operator`);
  if (st.comments.every((c) => c.kind !== "pending") && !st.groups.some((g) => ["new", "composing"].includes(g.status))) break;
  await sleep(3000);
}
await api("POST", `/sessions/${sid}/end`);
let sum;
for (let i = 0; i < 40; i++) { sum = await api("GET", `/sessions/${sid}/summary`); if (sum.status !== "computing") break; await sleep(3000); }
const c = sum.comment_insights;
console.log("summary status:", sum.status, "| insights:", c ? `${c.topic_source} from ${c.source}` : c);
if (c) {
  console.log(JSON.stringify({ comments: c.comments, viewers: c.viewers, askers: c.askers, questions: c.questions, outcomes: c.outcomes, reply_time_sec: c.reply_time_sec, buying: c.buying, gaps: c.not_in_product_information, reasons: c.waited_for_a_person_by_reason, languages: c.question_languages }, null, 1));
  for (const t of c.topics) console.log(` - ${t.label}${t.buying ? " [buying]" : ""}: ${t.questions} q, ${t.askers} viewers, auto ${t.auto_answered} / person ${t.answered_by_person} / open ${t.unanswered} | ${t.examples.join(" · ")}`);
  console.log("notes:", c.notes);
}
const browser = await chromium.launch({ channel: "msedge" });
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage();
await page.goto(`${BASE}/summary?session=${sid}`);
const card = page.getByTestId("summary-insights");
await card.waitFor({ timeout: 30000 });
await card.scrollIntoViewIfNeeded();
await card.screenshot({ path: SHOTS + "summary-insights.png" });
await page.screenshot({ path: SHOTS + "summary-page.png", fullPage: true });
console.log("session", sid);
await browser.close();
