// Show replay (proof-plan §1, synthetic arm, D-139): a scripted show replayed on the real path, with the
// assistant on and off, scored side by side.
//
//   node e2e/show-replay.mjs <file> [--assistant on|off]      (both when the flag is left out)
//
// <file>: one show (a JSON object), a JSON array of shows, or JSONL (one show per line):
//   {"seed","duration_s","events":[{"t_s","type":"host","text"} | {"t_s","type":"comment","author","text","qg"?}
//     | {"t_s","type":"promo_start","promo_id"} | {"t_s","type":"switch","to"}],
//    "planted_errors":[{"t_s","kind":"compliance|fact|qualifier","text"}], "safe_lookalikes":[{"t_s","why"}],
//    "question_groups":[{"id","asked_at":[t_s...],"intent","answerable":bool}]}
// Host lines are spoken by TTS through the mic WebSocket at their t_s; comments go through the scripted-comment
// demo API, promos and switches through the operator API. BASE and IAP_TOKEN as for rehearsal-voice.mjs.
// Writes ../docs/show-replay.json and .md (DOCS overrides the folder).
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

import { sleep, voiceTools } from "./voice.mjs";

const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
const AUTH = process.env.IAP_TOKEN ? { Authorization: `Bearer ${process.env.IAP_TOKEN}` } : {};
const DOCS = resolve(process.env.DOCS ?? "../docs");
const FILE = process.argv[2];
const flag = process.argv.indexOf("--assistant");
const MODES = flag > 0 ? [process.argv[flag + 1]] : ["on", "off"];
const WITHIN_MS = 3000; // planted error: alert on screen within 3 s of the end of speech
const LATE_MS = 60_000; // question: first handling later than this is late
const SETTLE_MS = 20_000; // after the last event, for answers and cards still in flight
const POLL_MS = 2000;
const QUALIFIER = "BRAND-TEST-QUALIFIER";

const { api, synth, Mic, newSession } = voiceTools({ base: BASE, auth: AUTH });

function loadShows(path) {
  const raw = readFileSync(path, "utf-8").trim();
  if (raw.startsWith("[")) return JSON.parse(raw);
  if (raw.startsWith("{") && !raw.includes("\n{")) return [JSON.parse(raw)];
  return raw.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
}

const words = (s) => new Set((s.toLowerCase().match(/[a-z0-9]+/g) ?? []));
function overlap(a, b) {
  const A = words(a), B = words(b);
  if (!A.size || !B.size) return 0;
  let n = 0;
  for (const w of A) if (B.has(w)) n++;
  return n / Math.min(A.size, B.size);
}

/** Replay one show; returns what the scorer needs (state history, finals, timings). */
async function replay(page, show, assistant) {
  const { session_id: sid } = await newSession({ assistant: assistant === "on", show_mode: "solo" });
  await page.goto(`${BASE}/host?session=${sid}`);
  await api("POST", `/sessions/${sid}/start`);
  const mic = new Mic(sid);
  await mic.ready;
  await sleep(1000);
  const t0 = Date.now();
  const at = (ts) => t0 + ts * 1000;

  // state history: first time each group was on the host list, on a card, answered; all transcripts and alerts
  const seen = { onList: {}, onCard: {}, cardKind: {}, posted: {}, transcripts: {}, alerts: {}, groups: {}, messages: {}, answers: {},
    promoStarts: {}, comments: {}, analyses: {} };
  const catalog = await api("GET", "/catalog");
  const priceChanging = new Set((catalog.promos ?? []).filter((p) => p.changes_prices).map((p) => p.promo_id));
  let polling = true;
  const poll = (async () => {
    while (polling) {
      try {
        const st = await api("GET", `/sessions/${sid}/state?role=operator`);
        const now = Date.now();
        for (const t of st.transcripts ?? []) seen.transcripts[t.transcript_id] = t;
        for (const a of st.alerts ?? []) seen.alerts[a.alert_id] = a;
        for (const g of st.groups ?? []) seen.groups[g.group_id] = g;
        for (const m of st.messages ?? []) seen.messages[m.message_id] = m;
        for (const c of st.comments ?? []) seen.comments[c.comment_id] = c;
        Object.assign(seen.analyses, st.analyses ?? {});
        Object.assign(seen.answers, st.answers ?? {});
        for (const sl of st.host_slots ?? []) seen.onList[sl.group_id] ??= now;
        const card = st.session?.pd_card;
        if (card && card.status === "active" && card.ref_id) {
          seen.onCard[card.ref_id] ??= now;
          seen.cardKind[card.ref_id] ??= card.kind;
        }
        for (const m of st.messages ?? []) {
          if (m.group_id && m.state === "published") seen.posted[m.group_id] ??= now;
        }
        for (const ap of st.session?.active_promos ?? []) {
          if (priceChanging.has(ap.promo_id)) seen.promoStarts[ap.promo_id] ??= ap.started_at;
        }
      } catch (e) {
        console.log(`poll: ${e.message}`);
      }
      await sleep(POLL_MS);
    }
  })();

  // host lines one after another on the mic; everything else at its own time
  const hostEvents = show.events.filter((e) => e.type === "host").sort((a, b) => a.t_s - b.t_s);
  const spoken = [];
  const voice = (async () => {
    for (const e of hostEvents) {
      const wait = at(e.t_s) - Date.now();
      if (wait > 0) await sleep(wait);
      spoken.push({ t_s: e.t_s, text: e.text, started: Date.now() });
      await mic.say(synth(e.text));
      spoken.at(-1).ended = Date.now();
    }
  })();
  const comments = [];
  const others = Promise.all(show.events.filter((e) => e.type !== "host").map(async (e) => {
    const wait = at(e.t_s) - Date.now();
    if (wait > 0) await sleep(wait);
    try {
      if (e.type === "comment") {
        const c = await api("POST", `/sessions/${sid}/demo/comments`, { author: e.author, text: e.text });
        comments.push({ ...e, comment_id: c.comment_id, posted_at: Date.now() });
      } else if (e.type === "promo_start") {
        await api("POST", `/sessions/${sid}/promos/${e.promo_id}/start`);
      } else if (e.type === "switch") {
        await api("POST", `/sessions/${sid}/segments/switch`, { product_id: e.to });
      }
    } catch (err) {
      console.log(`event at ${e.t_s}s (${e.type}): ${err.message}`);
    }
  }));
  await Promise.all([voice, others]);
  await sleep(Math.max(0, at(show.duration_s) - Date.now()) + SETTLE_MS);
  polling = false;
  await poll;
  const finals = mic.finals.slice();
  mic.close();
  await api("POST", `/sessions/${sid}/end`).catch(() => undefined);
  return { sid, assistant, t0, spoken, comments, finals, seen, promoStarts: Object.values(seen.promoStarts) };
}

/** Why a question group ended unanswered (the first that applies), with its route, draft and triage product.
 *  The largest group of the question's comments speaks for it. */
function groupDetail(run, qg, mine, gs, list) {
  const triage = mine.map((c) => {
    const cm = run.seen.comments[c.comment_id];
    const an = run.seen.analyses[c.comment_id];
    return { text: c.text, kind: cm?.kind ?? null, intent: an?.output?.intent ?? null, product_id: an?.product_id ?? null,
      basis: an?.product_basis ?? null, context_product_id: an?.context_product_id ?? null };
  });
  const g = [...gs].sort((a, b) => b.member_comment_ids.length - a.member_comment_ids.length)[0];
  const ans = g?.answer_id ? run.seen.answers[g.answer_id] : null;
  const draft = !g ? "no_group" : ans ? (ans.verified ? "verified" : "blocked") : g.status === "composing" ? "composing" : "none";
  const base = { route: g?.route ?? null, route_reason: g?.route_reason ?? null, status: g?.status ?? null, draft,
    draft_errors: ans && !ans.verified ? ans.verify_errors : [], needs_human: ans?.needs_human ?? null,
    product_id: g?.product_id ?? null, question: g?.canonical_question ?? null, triage };
  let reason;
  if (!g) {
    reason = `not_triaged_as_question (${[...new Set(triage.map((t) => t.kind ?? "unseen"))].join("/")})`;
  } else if (g.host_verbal_answer_transcript_id) {
    reason = "host_answered_unmatched";
  } else if (!ans) {
    reason = g.route_reason === "unresolved_product" ? "no_draft (product unresolved)" : g.route_reason === "general"
      ? (qg.answerable ? "no_draft (general intent)" : "unanswerable_no_card") : "no_draft";
  } else if (!ans.verified) {
    reason = `draft_blocked: ${(ans.verify_errors ?? []).join("; ")}`;
  } else if (ans.needs_human && g.route !== "HOST") {
    reason = `needs_human_waiting (${g.route}, ${g.unique_author_ids.length} asking)`;
  } else if (list !== Infinity && !run.seen.onCard[g.group_id]) {
    reason = "card_not_due";
  } else if (!qg.answerable) {
    reason = "unanswerable_no_card";
  } else {
    reason = `not_on_host_list (${g.route}/${g.status})`;
  }
  return { ...base, reason };
}

/** The spoken line each final belongs to: the most overlapping line that had started before it. */
function finalsByLine(run) {
  const byLine = new Map(run.spoken.map((s) => [s.t_s, []]));
  for (const f of run.finals) {
    if (!f.transcript_id) continue;
    const t = run.seen.transcripts[f.transcript_id];
    let best = null, bestScore = 0;
    for (const s of run.spoken) {
      const score = overlap(f.text, s.text);
      if (score > bestScore) { best = s; bestScore = score; }
    }
    if (best && bestScore >= 0.3) byLine.get(best.t_s).push({ ...f, transcript: t ?? null });
  }
  return byLine;
}

function alertsOn(run, finalsOfLine) {
  const ids = new Set(finalsOfLine.map((f) => f.transcript_id));
  return Object.values(run.seen.alerts).filter((a) => ids.has(a.transcript_id) && a.shown_at);
}

function lineFor(byLine, ts) {
  if (byLine.has(ts)) return byLine.get(ts);
  const near = [...byLine.keys()].sort((a, b) => Math.abs(a - ts) - Math.abs(b - ts))[0];
  return near !== undefined && Math.abs(near - ts) <= 2 ? byLine.get(near) : [];
}

const kindOf = (a) => (a.kind === "fact" ? "fact" : a.rule_id === QUALIFIER ? "qualifier" : "compliance");

function score(show, run) {
  const byLine = finalsByLine(run);
  // (a) planted errors alerted within 3 s of the end of speech, by kind
  const errors = (show.planted_errors ?? []).map((pe) => {
    const fl = lineFor(byLine, pe.t_s);
    const hits = alertsOn(run, fl).filter((a) => kindOf(a) === pe.kind);
    const times = hits.map((a) => {
      const t = run.seen.transcripts[a.transcript_id];
      const shown = a.host_rendered_at ?? a.shown_at;
      return t?.speech_end_at ? shown - t.speech_end_at : null;
    }).filter((x) => x !== null);
    const ms = times.length ? Math.min(...times) : null;
    return { t_s: pe.t_s, kind: pe.kind, alerted: hits.length > 0, ms, within_3s: ms !== null && ms <= WITHIN_MS,
      heard: fl.map((f) => f.text) };
  });
  // (b) alerts on safe lookalikes, red vs yellow
  const lookalikes = (show.safe_lookalikes ?? []).map((sl) => {
    const al = alertsOn(run, lineFor(byLine, sl.t_s));
    return { t_s: sl.t_s, why: sl.why,
      red: al.some((a) => a.kind === "compliance" && a.severity === "HIGH"),
      yellow: al.some((a) => !(a.kind === "compliance" && a.severity === "HIGH")),
      // which rule or fact note fired, so a false alert can be traced without another run
      alerts: al.map((a) => ({ kind: a.kind, rule_id: a.rule_id ?? null, severity: a.severity ?? null, status: a.status,
        field: a.field ?? null, said: a.stated_value ?? null, correct: a.correct_value ?? null })) };
  });
  // (c) question groups: how each was handled first, and when
  const groups = Object.values(run.seen.groups);
  const questions = (show.question_groups ?? []).map((qg) => {
    const mine = run.comments.filter((c) => c.qg === qg.id);
    const cids = new Set(mine.map((c) => c.comment_id));
    const firstAsk = Math.min(...mine.map((c) => c.posted_at));
    const gs = groups.filter((g) => g.member_comment_ids.some((c) => cids.has(c)));
    const firstOf = (table) => Math.min(...gs.map((g) => table[g.group_id] ?? Infinity));
    const posted = firstOf(run.seen.posted), card = firstOf(run.seen.onCard), list = firstOf(run.seen.onList);
    const deferral = gs.some((g) => run.seen.onCard[g.group_id] && ["no_verified_answer", "general"].includes(g.route_reason));
    let handling = "never", at = Infinity;
    if (posted !== Infinity && gs.some((g) => g.status === "auto_answered")) { handling = "auto_answered"; at = posted; }
    else if (card !== Infinity) { handling = deferral ? "deferred_honestly" : "host_card"; at = card; }
    else if (posted !== Infinity) { handling = "posted"; at = posted; }
    else if (gs.some((g) => g.host_verbal_answer_transcript_id)) {
      // the host answered it aloud (not posted): viewers heard the answer, no operator action needed
      handling = "answered_on_air";
      at = Math.min(...gs.map((g) => run.seen.transcripts[g.host_verbal_answer_transcript_id]?.received_at ?? Infinity));
    }
    const ms = at === Infinity || !mine.length ? null : at - firstAsk;
    const detail = groupDetail(run, qg, mine, gs, list);
    return { id: qg.id, intent: qg.intent, answerable: qg.answerable, asks: mine.length, groups: gs.length,
      handling, ms, late: ms !== null && ms > LATE_MS, on_list_only: handling === "never" && list !== Infinity,
      ...detail, reason: handling === "never" || handling === "deferred_honestly" ? detail.reason : null };
  });
  // (e) wrong or stale posts: an AI post for a question the script marks unanswerable; a post made after a
  // promo started with an answer written before it, for a price question
  // price promotions only (a gift-pouch promo changes no price), at the server's own start time
  const promoAt = run.promoStarts;
  const wrong = [], stale = [];
  for (const m of Object.values(run.seen.messages)) {
    if (m.kind !== "ai_answer" || m.state !== "published") continue;
    const g = run.seen.groups[m.group_id];
    const q = questions.find((x) => g && g.member_comment_ids.some((c) => run.comments.find((k) => k.comment_id === c && k.qg === x.id)));
    if (q && q.answerable === false) wrong.push({ qg: q.id, text: m.text });
    const ans = g?.answer_id ? run.seen.answers[g.answer_id] : null;
    if (g && ["price", "set_price", "promo"].includes(g.intent) && ans
        && promoAt.some((p) => ans.created_at < p && (m.published_at ?? m.created_at) >= p)) stale.push({ group: g.group_id, text: m.text });
  }
  // (d) operator actions needed: every planted error or question group the assistant did not handle
  const unhandled = errors.filter((e) => !e.alerted).length + questions.filter((q) => q.handling === "never").length;
  const byKind = {};
  for (const e of errors) {
    const k = (byKind[e.kind] ??= { planted: 0, alerted: 0, within_3s: 0 });
    k.planted++; k.alerted += e.alerted; k.within_3s += e.within_3s;
  }
  const handled = (h) => questions.filter((q) => q.handling === h).length;
  return {
    seed: show.seed, assistant: run.assistant, sid: run.sid,
    summary: {
      errors_by_kind: byKind,
      lookalikes: { total: lookalikes.length, red: lookalikes.filter((l) => l.red).length, yellow: lookalikes.filter((l) => l.yellow).length },
      questions: { total: questions.length, auto_answered: handled("auto_answered"), host_card: handled("host_card"),
        deferred_honestly: handled("deferred_honestly"), posted: handled("posted"),
        answered_on_air: handled("answered_on_air"), never: handled("never"),
        late: questions.filter((q) => q.late).length },
      operator_actions: unhandled, wrong_posts: wrong.length, stale_posts: stale.length,
    },
    errors, lookalikes, questions, wrong, stale,
  };
}

function markdown(results) {
  const lines = ["# Show replay (proof-plan §1, synthetic arm)", "",
    `${new Date().toISOString().slice(0, 10)} · \`${FILE}\` · ${BASE}`, ""];
  for (const seed of [...new Set(results.map((r) => r.seed))]) {
    const runs = results.filter((r) => r.seed === seed);
    const col = (r) => r.summary;
    lines.push(`## ${seed}`, "", `| | ${runs.map((r) => `assistant ${r.assistant}`).join(" | ")} |`,
      `|---|${runs.map(() => "---").join("|")}|`);
    const kinds = [...new Set(runs.flatMap((r) => Object.keys(col(r).errors_by_kind)))];
    for (const k of kinds) {
      lines.push(`| ${k} errors alerted within 3 s | ${runs.map((r) => {
        const x = col(r).errors_by_kind[k] ?? { planted: 0, within_3s: 0, alerted: 0 };
        return `${x.within_3s}/${x.planted} (alerted ${x.alerted})`;
      }).join(" | ")} |`);
    }
    const row = (label, f) => lines.push(`| ${label} | ${runs.map((r) => f(col(r))).join(" | ")} |`);
    row("safe lookalikes: red / yellow", (s) => `${s.lookalikes.red} / ${s.lookalikes.yellow} of ${s.lookalikes.total}`);
    row("questions auto-answered", (s) => `${s.questions.auto_answered}/${s.questions.total}`);
    row("questions on a host card", (s) => `${s.questions.host_card}/${s.questions.total}`);
    row("questions deferred honestly", (s) => `${s.questions.deferred_honestly}/${s.questions.total}`);
    row("questions answered on air (not posted)", (s) => `${s.questions.answered_on_air}/${s.questions.total}`);
    row("questions never handled", (s) => `${s.questions.never}/${s.questions.total}`);
    row("questions handled late (> 60 s)", (s) => `${s.questions.late}`);
    row("operator actions needed", (s) => `${s.operator_actions}`);
    row("wrong / stale posts", (s) => `${s.wrong_posts} / ${s.stale_posts}`);
    lines.push("");
    for (const r of runs) {
      const open = r.questions.filter((q) => q.reason);
      if (!open.length) continue;
      lines.push(`### ${seed}, assistant ${r.assistant}: why questions were not answered`, "",
        "| group | intent | answerable | asks | reason | route | draft | triage product (basis) |", "|---|---|---|---|---|---|---|---|");
      for (const q of open) {
        const tp = [...new Set(q.triage.map((t) => `${t.product_id ?? "none"} (${t.basis ?? "-"})`))].join(", ");
        lines.push(`| ${q.id} | ${q.intent} | ${q.answerable} | ${q.asks} | ${q.reason} | ${q.route ?? "-"}/${q.route_reason ?? "-"} | ${q.draft} | ${tp} |`);
      }
      const counts = {};
      for (const q of open) counts[q.reason.split(/[ :(]/)[0]] = (counts[q.reason.split(/[ :(]/)[0]] ?? 0) + 1;
      lines.push("", `Reasons: ${Object.entries(counts).map(([k, n]) => `${k} ${n}`).join(", ")}`, "");
    }
  }
  return lines.join("\n") + "\n";
}

const shows = loadShows(FILE);
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "msedge" });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, extraHTTPHeaders: AUTH });
const results = [];
for (const show of shows) {
  for (const mode of MODES) {
    console.log(`== ${show.seed}: assistant ${mode} (${show.duration_s} s)`);
    const run = await replay(page, show, mode);
    const scored = score(show, run);
    console.log(JSON.stringify(scored.summary));
    results.push(scored);
    writeFileSync(join(DOCS, "show-replay.json"), JSON.stringify(results, null, 1));
  }
}
await browser.close();
writeFileSync(join(DOCS, "show-replay.md"), markdown(results));
console.log(`report: ${join(DOCS, "show-replay.md")}`);
