// The recorded demo, end to end on /studio (DEV_SPEC §14.4, data/demo/host_script.md S02-S14).
// Host lines are injected from the Demo Console (STT injection), bursts fired from it; operator actions
// go through the Operator pane. Every scene's "Expected" row is asserted as DOM state on the host,
// operator and viewer panes; the API is only read to look up ids (groups, comments, alerts).
import { expect, test, type APIRequestContext } from "@playwright/test";

type Step = { index: number; scene: string; who: string; action: string; text: string; arg: string | null };
type Group = {
  group_id: string; intent: string; status: string; product_id: string | null; route: string;
  condition_slots: Record<string, string | null>; unique_author_ids: string[]; member_comment_ids: string[];
  answer_id: string | null;
};
type State = {
  session: { status: string; switch: { status: string }; pre_covered: Record<string, string[]>; promo_started_at: number | null };
  groups: Group[];
  comments: { comment_id: string; author_id: string; author_name: string; text: string; visibility: string }[];
  analyses: Record<string, { product_id: string | null; product_basis: string }>;
  alerts: { alert_id: string; kind: string; status: string; transcript_id: string; rule_id: string | null; field: string | null }[];
  transcripts: { transcript_id: string; text: string }[];
  messages: { message_id: string; kind: string; text: string; group_id: string | null; created_at: number; state: string }[];
};

const CREAM = "cream_hydra_barrier";
const AMPOULE = "ampoule_deep_hydration";

let sid = "";

async function state(request: APIRequestContext): Promise<State> {
  const r = await request.get(`/api/sessions/${sid}/state?role=operator`);
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as State;
}

/** Poll the state until `pick` returns a value. */
async function waitFor<T>(request: APIRequestContext, pick: (s: State) => T | undefined | null | false, timeout = 25_000): Promise<T> {
  let found: T | undefined | null | false;
  await expect
    .poll(async () => {
      found = pick(await state(request));
      return Boolean(found);
    }, { timeout, intervals: [200, 300, 500] })
    .toBe(true);
  return found as T;
}

const groupOf = (s: State, pred: (g: Group) => boolean) => s.groups.find(pred);

test.describe.configure({ mode: "serial" });

test("demo script S02-S14 on /studio", async ({ page, request }) => {
  const steps: Step[] = (await (await request.get("/api/demo/script")).json()).steps;
  const lines = steps.filter((s) => s.action === "host_line");
  expect(lines).toHaveLength(15);

  await page.goto("/studio?layout=all");
  const host = page.locator('section[aria-label="Host screen"]');
  const op = page.locator('section[aria-label="Operator"]');
  const viewer = page.locator('section[aria-label="Viewer"]');
  const drawer = page.locator('section[aria-label="Demo console"]');
  const handle = drawer.locator("button[aria-expanded]").first();
  await expect(host).toHaveCount(1);
  await expect(op).toHaveCount(1);
  await expect(viewer).toHaveCount(1);

  const openConsole = async () => {
    if ((await handle.getAttribute("aria-expanded")) !== "true") await handle.click();
  };
  const closeConsole = async () => {
    if ((await handle.getAttribute("aria-expanded")) === "true") await handle.click();
  };
  const transcriptRow = (text: string) => op.locator('[data-testid^="op-transcript-"]').filter({ hasText: text });
  /** Inject host line i from the Demo Console and wait until the operator transcript shows it. */
  const say = async (i: number) => {
    await openConsole();
    await drawer.locator("li").filter({ hasText: lines[i].text }).getByRole("button", { name: "Inject" }).click();
    await expect(transcriptRow(lines[i].text)).toBeVisible();
  };
  const burst = async (label: string) => {
    await openConsole();
    await drawer.getByRole("button", { name: label }).click();
  };
  const point = (id: string) => host.getByTestId(`host-point-${id}`);
  const opGroup = (g: Group) => op.getByTestId(`op-group-${g.group_id}`);
  const reply = (kind: string, text?: string) => {
    const l = viewer.locator(`[data-testid^="viewer-reply-"][data-kind="${kind}"]`);
    return text ? l.filter({ hasText: text }) : l;
  };

  // ---- reset and S02 Start ---------------------------------------------------------------------------
  await openConsole();
  await drawer.getByRole("button", { name: "Reset demo" }).click();
  await page.waitForURL(/session=ses_/);
  sid = new URL(page.url()).searchParams.get("session")!;
  await closeConsole();
  await op.getByRole("button", { name: "Start broadcast" }).click();
  await expect(host.getByTestId("host-live")).toContainText("LIVE");
  await expect(host.getByTestId("host-now")).toHaveText("Hydra Barrier Cream");
  await expect(host.getByTestId("host-next")).toHaveText("Deep Hydration Ampoule");
  await expect(point("cr-p1")).toBeVisible();
  await expect(op.getByTestId("op-run-of-show")).toContainText("On air now");
  await page.waitForTimeout(2_500); // past STREAM_GRACE_SEC so comments have a context product

  await say(0); // welcome line: no alert
  await page.waitForTimeout(1_000);
  await expect(host.getByTestId("host-compliance-overlay")).toHaveCount(0);
  await say(1);
  await expect(point("cr-p1")).toHaveAttribute("data-state", "said");
  await say(2);
  await expect(point("cr-p2")).toHaveAttribute("data-state", "said");
  await expect(host.getByTestId("host-required-count")).toHaveText("1 / 3 required points");

  // ---- S03 B1: reactions without reply, one price group answered once, set price separate --------
  await burst("B1 Price questions");
  const s3 = await waitFor(request, (s) => {
    const price = groupOf(s, (g) => g.intent === "price" && g.status === "auto_answered" && g.unique_author_ids.length === 4
      && g.member_comment_ids.length === 5);
    const set = groupOf(s, (g) => g.intent === "set_price" && g.status === "auto_answered");
    return price && set && s.comments.length >= 9 ? { price, set, s } : null;
  });
  await expect(opGroup(s3.price)).toHaveAttribute("data-status", "auto_answered");
  await expect(opGroup(s3.price)).toContainText("AI answered");
  await expect(reply("ai_answer", "S$36.00").first()).toBeVisible();
  await expect(reply("ai_answer", "S$62.00").first()).toBeVisible();
  const reactions = s3.s.comments.filter((c) => ["So pretty! 💜", "love the packaging", "😍😍😍"].includes(c.text));
  expect(reactions).toHaveLength(3);
  for (const c of reactions) {
    await expect(viewer.getByTestId(`viewer-comment-${c.comment_id}`)).toBeVisible();
    await expect(viewer.getByTestId(`viewer-comment-${c.comment_id}`).locator('[data-testid^="viewer-reply-"]')).toHaveCount(0);
  }
  await expect(op.getByTestId("op-metrics")).toContainText(/Instant answers [1-9]\d*\//);

  // ---- S04 B2: grouping and host top 3 -------------------------------------------------------------
  await burst("B2 Oily skin & makeup");
  const s4 = await waitFor(request, (s) => {
    const oily = groupOf(s, (g) => g.intent === "skin_type_suitability" && g.condition_slots.skin_type === "oily");
    const dry = groupOf(s, (g) => g.intent === "skin_type_suitability" && g.condition_slots.skin_type === "dry");
    const makeup = groupOf(s, (g) => g.intent === "makeup_compatibility");
    const fragrance = groupOf(s, (g) => g.intent === "fragrance" && g.status === "auto_answered");
    return oily && dry && makeup && fragrance && oily.unique_author_ids.length === 7 && makeup.unique_author_ids.length === 4
      && oily.status === "ready" && makeup.status === "ready" ? { oily, dry, makeup } : null;
  });
  await closeConsole();
  for (const g of [s4.oily, s4.makeup]) {
    await expect(host.getByTestId(`host-question-${g.group_id}`)).toBeVisible();
  }
  // D-113: the top question is released on the AI PD card (question above, verified answer below)
  await expect(host.getByTestId(`host-question-${s4.oily.group_id}`)).toContainText("On your card");
  await expect(host.getByTestId("host-pd-card")).toHaveAttribute("data-kind", "answer_question");
  await expect(host.getByTestId("host-pd-question")).toContainText("oily skin");
  await expect(opGroup(s4.oily)).toContainText("7");
  await expect(opGroup(s4.makeup)).toContainText("4");
  await expect(opGroup(s4.dry)).toBeVisible();

  // ---- S05 host answers: "Posting answer…" for 2 s, then the card leaves; viewer gets "Host answer" --
  const raj = s4.oily.member_comment_ids[0];
  await say(3);
  await expect(host.getByTestId(`host-question-${s4.oily.group_id}`)).toContainText("Posting answer", { timeout: 2_500 });
  await expect(host.getByTestId(`host-question-${s4.oily.group_id}`)).toHaveCount(0, { timeout: 8_000 });
  await expect(viewer.getByTestId(`viewer-comment-${raj}`).locator('[data-kind="host_answer"]')).toBeVisible();
  await expect(viewer.getByTestId(`viewer-comment-${raj}`)).toContainText("Host answer");

  // ---- S06 fact error and correction -----------------------------------------------------------------
  await say(4);
  const fact = host.getByTestId("host-fact-note");
  await expect(fact).toBeVisible();
  await expect(fact).toContainText("PRICE CORRECTION");
  await expect(host.getByTestId("host-fact-wrong")).toContainText("S$32");
  await expect(host.getByTestId("host-fact-right")).toContainText("S$36.00");
  await expect(fact).toContainText("Source:");
  const fx = await waitFor(request, (s) => s.alerts.find((a) => a.kind === "fact" && a.field === "price" && a.status === "active"));
  const fxCard = op.getByTestId(`op-alert-${fx.alert_id}`);
  await expect(fxCard).toContainText("Price correction");
  await expect(fxCard.getByRole("button", { name: "Resend to host" })).toBeVisible();
  await expect(fxCard.getByRole("button", { name: "Post notice" })).toBeVisible();
  await say(5);
  await expect(fact).toHaveCount(0);
  await expect(fxCard).toHaveAttribute("data-state", "corrected");

  // ---- S07 compliance: full screen within 5 s, escalation after 5 s, correction ------------------------
  await say(6);
  const overlay = host.getByTestId("host-compliance-overlay");
  await expect(overlay).toBeVisible({ timeout: 5_000 });
  await expect(overlay).toContainText("HIGH-RISK CLAIM");
  await expect(overlay).toContainText("Say this instead.");
  await expect(overlay).toContainText("your wrinkles will disappear overnight");
  await expect(overlay).toContainText("Appendix III");
  const al = await waitFor(request, (s) => s.alerts.find((a) => a.kind === "compliance" && a.status === "active"
    && a.rule_id === "ASEAN-3-SKIN-AGEING"));
  const alCard = op.getByTestId(`op-alert-${al.alert_id}`);
  await expect(alCard).toContainText("Host correction required");
  await expect(alCard).toContainText("Not corrected", { timeout: 8_000 });
  await expect(alCard).toHaveAttribute("data-state", "escalated");
  await say(7);
  await expect(host.getByTestId("host-corrected")).toBeVisible({ timeout: 3_000 });
  await expect(overlay).toHaveCount(0);
  await expect(alCard).toContainText(/Corrected in \d+(\.\d)? s/);
  await expect(point("cr-p3")).toHaveAttribute("data-state", "said");

  // ---- S08 negation: no full-screen alert --------------------------------------------------------------
  await say(8);
  await page.waitForTimeout(3_000);
  await expect(overlay).toHaveCount(0);
  await expect(host.getByTestId("host-checking-chip")).toHaveCount(0);

  // ---- S09 sensitive burst, hidden abuse, operator Edit reply + Post ------------------------------------
  await burst("B3 Sensitive & spam");
  const s9 = await waitFor(request, (s) => {
    // D-113: sensitive questions go to the host's waiting list (no operator routing by sensitivity)
    const preg = groupOf(s, (g) => g.intent === "pregnancy_breastfeeding" && g.route === "HOST" && g.status === "ready" && g.unique_author_ids.length === 3);
    const eczema = groupOf(s, (g) => g.intent === "medical_condition" && g.status === "needs_review");
    const ship = groupOf(s, (g) => g.intent === "shipping" && g.status === "needs_review");
    const hidden = s.comments.filter((c) => c.visibility === "hidden");
    return preg && eczema && ship && hidden.length >= 3 ? { preg, eczema, ship, hidden, s } : null;
  });
  await closeConsole();
  await expect(host.getByTestId(`host-question-${s9.preg.group_id}`)).toBeVisible();
  for (const g of [s9.eczema, s9.ship]) {
    await expect(opGroup(g)).toContainText("Needs review");
    await expect(host.getByTestId(`host-question-${g.group_id}`)).toHaveCount(0);
  }
  for (const c of s9.hidden) {
    await expect(viewer.getByTestId(`viewer-comment-${c.comment_id}`)).toHaveCount(0);
    await expect(host.getByTestId("host-chat")).not.toContainText(c.text);
  }
  await expect(op.getByRole("button", { name: /Show filtered \(\d+\)/ })).toBeVisible();
  // The desk expands one row at a time.
  await opGroup(s9.ship).locator("button[aria-expanded]").first().click();
  await expect(opGroup(s9.ship)).toContainText("No AI draft for this question.");
  await opGroup(s9.preg).locator("button[aria-expanded]").first().click();
  await expect(opGroup(s9.preg)).toContainText("Verified against the product sheet");
  await opGroup(s9.preg).getByRole("button", { name: "Edit reply" }).click();
  const editor = opGroup(s9.preg).getByRole("textbox", { name: "Edit reply" });
  const draft = await editor.inputValue();
  expect(draft.length).toBeGreaterThan(20);
  await editor.fill(`${draft} Thank you for asking.`);
  await opGroup(s9.preg).getByRole("button", { name: "Post", exact: true }).click();
  await expect(opGroup(s9.preg)).toHaveAttribute("data-status", "answered");
  await expect(reply("brand_answer", "Thank you for asking.")).toBeVisible();
  await expect(reply("brand_answer", "Thank you for asking.")).toContainText("DAON LAB");

  // ---- S10 points 3/3 ----------------------------------------------------------------------------------
  await say(9);
  await expect(point("cr-p4")).toHaveAttribute("data-state", "said");
  await expect(host.getByTestId("host-required-count")).toHaveText("3 / 3 required points");
  await expect(op.getByTestId("op-run-of-show")).toContainText("3 / 3 required points covered");

  // ---- S11 time sale from Banners & notices, then B4 -----------------------------------------------------
  await closeConsole();
  await op.getByTestId("op-promo-promo_time_sale_10").getByRole("button", { name: "Start" }).click();
  await expect(viewer.getByTestId("viewer-timesale-popup")).toBeVisible({ timeout: 3_000 });
  await expect(viewer.getByTestId("viewer-timesale-popup")).toContainText(/(10:00|09:5\d)/);
  await expect(host.getByTestId("host-promo-chip")).toContainText("TIME SALE");
  await expect(viewer.getByTestId("viewer-price")).toContainText("S$32.40");
  await expect(viewer.getByTestId("viewer-set-price")).toContainText("S$55.80");
  await expect(host.getByTestId("host-prompter")).toContainText("S$32.40");
  await burst("B4 Time sale questions");
  const s11 = await waitFor(request, (s) => {
    const since = s.session.promo_started_at ?? Infinity;
    const after = s.messages.filter((m) => m.kind === "ai_answer" && m.created_at >= since);
    return after.some((m) => m.text.includes("S$32.40")) && after.some((m) => m.text.includes("S$55.80")) ? after : null;
  });
  expect(s11.some((m) => m.text.includes("S$36.00"))).toBe(false); // no stale price re-posted
  await expect(reply("ai_answer", "S$32.40").first()).toBeVisible();
  await expect(reply("ai_answer", "S$55.80").first()).toBeVisible();

  // ---- S12 switch ------------------------------------------------------------------------------------
  await say(10); // mention of the ampoule while answering: no switch
  await page.waitForTimeout(1_000);
  await expect(host.getByTestId("host-switch-banner")).toHaveCount(0);
  await burst("Arm B5 Switch boundary");
  await expect(handle).toContainText("B5 armed");
  await say(11); // first cue
  await expect(transcriptRow(lines[11].text)).toContainText("switch cue 1/2");
  await expect(host.getByTestId("host-switch-banner")).toHaveCount(0);
  await waitFor(request, (s) => (s.session.pre_covered[AMPOULE] ?? []).includes("am-p1"));
  await say(12); // second cue: countdown
  const banner = host.getByTestId("host-switch-banner");
  await expect(banner).toContainText("Switching to Deep Hydration Ampoule");
  await expect(banner.getByRole("button", { name: "Cancel switch (Esc)" })).toBeVisible();
  await expect(op.getByTestId("op-run-of-show")).toContainText(/Switching in \ds/);
  await expect(host.getByTestId("host-now")).toHaveText("Deep Hydration Ampoule", { timeout: 9_000 });
  await expect(host.getByTestId("host-next")).toHaveText("End of run sheet");
  await expect(point("am-p1")).toHaveAttribute("data-state", "said");
  await expect(point("am-p2")).toHaveAttribute("data-state", "said");
  await expect(host.getByTestId("host-fact-note")).toHaveCount(0); // no fact correction for the continuation
  const s12 = await state(request);
  for (const g of s12.groups.filter((x) => x.product_id === CREAM)) {
    await expect(host.getByTestId(`host-question-${g.group_id}`)).toHaveCount(0);
  }
  const run = op.getByTestId("op-run-of-show");
  await expect(run.locator("li").nth(0)).toContainText("Done");
  await expect(run.locator("li").nth(1)).toContainText("On air now");
  await expect(handle).not.toContainText("B5 armed");

  // B5 fires at the ampoule segment start (System row)
  const b5 = await waitFor(request, (s) => {
    const by = (t: string) => s.comments.find((c) => c.text === t);
    const howMuch = by("how much?");
    const fragrance = by("is the cream fragrance free?");
    const sting = by("Does the ampoule sting?");
    const stingGroup = sting && groupOf(s, (g) => g.member_comment_ids.includes(sting.comment_id));
    return howMuch && fragrance && stingGroup && s.analyses[howMuch.comment_id] && s.analyses[fragrance.comment_id]
      && stingGroup.route === "HOST" && stingGroup.status === "ready" ? { s, howMuch, fragrance, stingGroup } : null;  // D-113
  }, 30_000);
  expect(b5.s.analyses[b5.howMuch.comment_id]).toMatchObject({ product_id: CREAM, product_basis: "context" });
  expect(b5.s.analyses[b5.fragrance.comment_id].product_id).toBe(CREAM);
  expect(b5.stingGroup.product_id).toBe(AMPOULE);
  await expect(host.getByTestId(`host-question-${b5.stingGroup.group_id}`)).toBeVisible();  // D-113: to the host
  const later = await waitFor(request, (s) => {
    const t = s.comments.find((c) => c.text === "how much is the ampoule?");
    return t && s.analyses[t.comment_id] ? s.analyses[t.comment_id] : null;
  });
  expect(later.product_id).toBe(AMPOULE);

  // ---- S13 fact error on the ampoule ---------------------------------------------------------------------
  await say(13);
  await expect(host.getByTestId("host-fact-wrong")).toContainText("10% niacinamide");
  await expect(host.getByTestId("host-fact-right")).toContainText("4% niacinamide");
  await say(14);
  await expect(host.getByTestId("host-fact-note")).toHaveCount(0);

  // ---- S14 End broadcast (confirm dialog) and the summary page -------------------------------------------
  await closeConsole();
  await op.getByRole("button", { name: "End broadcast" }).click();
  const dialog = page.getByRole("dialog", { name: "End broadcast" });
  await expect(dialog).toContainText("End the broadcast? This stops the feed and creates the summary.");
  await dialog.getByRole("button", { name: "End broadcast" }).click();
  await expect(op.getByTestId("op-header")).toContainText("ENDED");
  await op.getByRole("link", { name: "Open summary" }).click();
  await page.waitForURL(/\/summary\?session=/);
  const summary = page.getByTestId("summary");
  await expect(summary.getByTestId(`summary-product-${CREAM}`)).toBeVisible();
  await expect(summary.getByTestId(`summary-product-${AMPOULE}`)).toBeVisible();
  await expect(summary.getByTestId(`summary-product-${CREAM}`)).toContainText("Hydra Barrier Cream");
  const log = summary.getByTestId("summary-compliance");
  await expect(log).toContainText("your wrinkles will disappear overnight");
  await expect(log).toContainText("Prevents, reduces or reverses physiological changes of ageing");
  await expect(log).toContainText("Let me correct that.");
  await expect(summary.getByTestId("summary-facts")).toContainText("niacinamide");
  await expect(summary.getByTestId("summary-recap")).toContainText("AI-written recap based on the numbers below", { timeout: 30_000 });
});
