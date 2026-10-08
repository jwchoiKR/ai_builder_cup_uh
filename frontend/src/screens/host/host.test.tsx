import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLang } from "../../app/i18n";
import { activeLineCheck, LINE_CHECK_MS, RED_BLOCK_MS } from "../../app/selectors";
import { reduceEvent, reduceSnapshot } from "../../app/state";
import type { Catalog, StateSnapshot } from "../../app/types";
import { alert, AMPOULE, answer, catalog, comment, CREAM, group, message, pdCard, segment, session, snapshot, T0 } from "../../test/fixtures";
import { factContext, fieldLabel, shortRef } from "./hostSelectors";
import { HostView, type HostActions } from "./HostScreen";

const cat: Catalog = {
  ...catalog,
  rules: [
    { rule_id: "ASEAN-3-SKIN-AGEING", title: "Prevents, reduces or reverses physiological changes of ageing", severity: "HIGH", source_ref: "Appendix III, Section 3, Skin products" },
    { rule_id: "BRAND-SUPERLATIVE", title: "Comparative or superlative claims", severity: "MEDIUM", source_ref: "Product sheet, section 7, Claims not approved" },
  ],
  passages: {
    "DL-CR-01#key-facts#live-broadcast-price": { doc: "DAON_LAB_Hydra_Barrier_Cream.pdf", section: "Key facts", product_id: CREAM, text: "Live broadcast price: S$36.00" },
  },
  notices: {
    host_cue_presets: [],
    operator_quick_replies: [],
    correction_notices: [],
    field_labels: { price: "price", ingredient_amount: "ingredient amount" },
  },
};

function actions(): HostActions {
  return { rendered: vi.fn(), cancelSwitch: vi.fn(), undoSwitch: vi.fn(), dismissPd: vi.fn(), pullQuestion: vi.fn(), extendSegment: vi.fn() };
}

function view(over: Partial<StateSnapshot> = {}, acts: HostActions = actions()) {
  // D-161: a red alert blocks cards only while fresh, so alerts are dated near "now" (spacing kept)
  const shift = Date.now() - T0;
  const alerts = over.alerts?.map((a) => ({ ...a, created_at: a.created_at + shift }));
  const state = reduceSnapshot(snapshot(alerts ? { ...over, alerts } : over), "host", Date.now());
  // keep server time = client time so timers are near "now"
  const s = { ...state, serverOffsetMs: 0 };
  return <HostView state={s} catalog={cat} connection="connected" theme="dark" actions={acts} />;
}

const now = () => Date.now();

describe("host selectors", () => {
  it("shortens policy references and labels fields", () => {
    expect(shortRef("Appendix III, Section 3, Skin products")).toBe("Appendix III §3");
    expect(shortRef("Appendix III, Section 2.d (Product presentation of cosmetics)")).toBe("Appendix III §2.d");
    expect(shortRef("Product sheet, section 7, Claims not approved")).toBe("Product sheet §7");
    expect(fieldLabel(cat, "ingredient_amount")).toBe("Ingredient amount");
    expect(fieldLabel(cat, "shelf_life")).toBe("Shelf life");
    expect(factContext(cat, alert({ kind: "fact", quote: "Niacinamide: 4%", field: "ingredient_amount" }))).toBe("Niacinamide");
  });
});

describe("top bar", () => {
  it("shows READY before the start and NOW/NEXT names", () => {
    render(view({ session: session({ status: "ready", started_at: null }), segments: [] }));
    const bar = screen.getByTestId("host-topbar");
    expect(within(bar).getByText("READY")).toBeInTheDocument();
    expect(screen.getByTestId("host-now")).toHaveTextContent("Hydra Barrier Cream");
    expect(screen.getByTestId("host-next")).toHaveTextContent("Deep Hydration Ampoule");
    // the first product's prompter page is readable before the start
    expect(screen.getByTestId("host-point-cr-p1")).toHaveAttribute("data-state", "todo");
  });

  it("shows LIVE and End of run sheet on the last product", () => {
    render(view({ session: session({ started_at: now() - 5000 }), segments: [segment({ product_id: AMPOULE, started_at: now() - 1000 })] }));
    expect(within(screen.getByTestId("host-topbar")).getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("host-now")).toHaveTextContent("Deep Hydration Ampoule");
    expect(screen.getByTestId("host-next")).toHaveTextContent("End of run sheet");
  });
});

describe("prompter", () => {
  it("renders a plain list of said and unsaid points with required labels, no next-point cue (D-091)", () => {
    render(view({ segments: [segment({ covered_point_ids: ["cr-p1"] })] }));
    expect(screen.getByTestId("host-point-cr-p1")).toHaveAttribute("data-state", "said");
    expect(screen.getByTestId("host-point-cr-p2")).toHaveAttribute("data-state", "todo");
    expect(screen.getByTestId("host-point-cr-p3")).toHaveAttribute("data-state", "todo");
    expect(screen.getByTestId("host-point-cr-p2")).not.toHaveAttribute("aria-current");
    expect(screen.queryByText("REQUIRED")).toBeNull(); // D-115: the counter and checkmarks carry it
    expect(screen.getByTestId("host-required-count")).toHaveTextContent("0 / 2 required points");
    expect(screen.getByText("YOUR PROMPTER")).toBeInTheDocument();
    expect(screen.getByText("LIVE PRICE")).toBeInTheDocument();
    expect(screen.getByText("S$36.00")).toBeInTheDocument();
    expect(screen.queryByText("Keep it natural.")).toBeNull();
    expect(screen.queryByText(/Focus on your next point/)).toBeNull();
  });

  it("counts covered required points and drops the label", () => {
    render(view({ segments: [segment({ covered_point_ids: ["cr-p1", "cr-p2"] })] }));
    expect(screen.getByTestId("host-required-count")).toHaveTextContent("1 / 2 required points");
    expect(screen.getByTestId("host-points-status")).toHaveTextContent("1 required point left");
  });

  it("D-115: the switch countdown takes the reserved status line inside the prompter", () => {
    render(view({ session: session({ switch: { status: "pending", target_product_id: AMPOULE, cue_count: 2, cue_transcript_ids: [], first_cue_at: null, commit_at: now() + 4000, last_commit: null } }) }));
    const status = screen.getByTestId("host-prompter-status");
    expect(within(status).getByTestId("host-switch-banner")).toHaveTextContent("Cancel switch (Esc)");
    expect(screen.queryByTestId("host-points-status")).toBeNull();
  });

  it("D-107: status line with points and time left; the lead point is emphasised once from 80% of the time", () => {
    const at = (share: number) => view({ segments: [segment({ started_at: now() - 900_000 * share, covered_point_ids: ["cr-p2"] })] });
    const { rerender } = render(at(0.5));
    expect(screen.getByTestId("host-points-status")).toHaveTextContent(/^1 required point left · 7:(29|30)$/);
    expect(screen.getByTestId("host-point-cr-p3")).not.toHaveAttribute("data-late");
    rerender(at(0.85));
    expect(screen.getByTestId("host-point-cr-p3")).toHaveAttribute("data-late", "true");
    expect(screen.getByTestId("host-point-cr-p3").className).toMatch(/leadLate/);
    rerender(at(1.1));
    expect(screen.getByTestId("host-points-status")).toHaveTextContent(/^1 required point left · \+1:(29|30) over$/);
  });

  it("D-106: price, ingredient numbers, cautions and wording to avoid; said ingredients turn grey", () => {
    const { rerender } = render(view({}));
    expect(screen.getByTestId("host-ing-panthenol")).toHaveTextContent("5%Panthenol");
    expect(screen.getByTestId("host-ing-ceramide_np")).toHaveTextContent("1%Ceramide NP");
    expect(screen.queryByTestId("host-ing-volume")).toBeNull(); // not an ingredient amount
    expect(screen.getByTestId("host-cautions")).toHaveTextContent("Do not apply to broken or damaged skin.");
    expect(screen.getByTestId("host-avoid")).toHaveTextContent("✕ Heals eczema→Helps relieve the feeling of dryness.");
    expect(screen.getByTestId("host-ing-panthenol").className).not.toMatch(/said/);
    expect(within(screen.getByTestId("host-ing-panthenol")).queryByLabelText("Said")).toBeNull();
    // D-372: a covered point that names the ingredient no longer ticks it; only its id from the fact checker does
    rerender(view({ segments: [segment({ covered_point_ids: ["cr-p2"] })] }));
    expect(screen.getByTestId("host-ing-panthenol").className).not.toMatch(/said/);
    rerender(view({ segments: [segment({ ticked_item_ids: ["DL-CR-01#prompter#ingredient-panthenol"] })] }));
    expect(screen.getByTestId("host-ing-panthenol").className).toMatch(/said/);
    expect(within(screen.getByTestId("host-ing-panthenol")).getByLabelText("Said")).toBeInTheDocument(); // D-348
  });

  it("D-372: price lines, ingredients and cautions are ticked by their ids only", () => {
    const { rerender } = render(view({}));
    for (const id of ["host-price-current", "host-price-struck", "host-price-set", "host-caution-1"]) {
      expect(screen.getByTestId(id)).toHaveAttribute("data-state", "todo");
    }
    rerender(view({ segments: [segment({ ticked_item_ids: [
      "DL-CR-01#prompter#live-price", "DL-CR-01#prompter#set-set_cream_ampoule", "DL-CR-01#prompter#caution-1",
      "DL-AM-01#prompter#list-price"] })] }));  // another product's id ticks nothing here
    expect(screen.getByTestId("host-price-current")).toHaveAttribute("data-state", "said");
    expect(within(screen.getByTestId("host-price-current")).getByLabelText("Said")).toBeInTheDocument();
    expect(screen.getByTestId("host-price-set")).toHaveAttribute("data-state", "said");
    expect(screen.getByTestId("host-caution-1")).toHaveAttribute("data-state", "said");
    expect(screen.getByTestId("host-price-struck")).toHaveAttribute("data-state", "todo");
  });

  it("D-388: a point with a price is listed too (the screen and the fact checker's snapshot match)", () => {
    const priced: Catalog = { ...cat, products: cat.products.map((p, i) => i ? p : { ...p, prompter_points: [
      ...p.prompter_points, { point_id: "cr-p9", text: "Only S$36.00 live today.", required: false }] }) };
    const s = { ...reduceSnapshot(snapshot(), "host", Date.now()), serverOffsetMs: 0 };
    render(<HostView state={s} catalog={priced} connection="connected" theme="dark" actions={actions()} />);
    expect(screen.getByTestId("host-point-cr-p9")).toHaveTextContent("Only S$36.00 live today.");
  });

  it("D-348: no AVOID SAYING heading when the product has no wording to avoid", () => {
    const bare: Catalog = { ...cat, products: cat.products.map((p) => ({ ...p, avoid_saying: [] })) };
    const s = { ...reduceSnapshot(snapshot(), "host", Date.now()), serverOffsetMs: 0 };
    render(<HostView state={s} catalog={bare} connection="connected" theme="dark" actions={actions()} />);
    expect(screen.queryByTestId("host-avoid")).toBeNull();
    expect(screen.queryByText("Avoid saying")).toBeNull();
  });

  it("D-348: a covered point is highlighted with a check and keeps its full text; an open point keeps its bullet", () => {
    render(view({ segments: [segment({ covered_point_ids: ["cr-p1"] })] }));
    const said = screen.getByTestId("host-point-cr-p1");
    const todo = screen.getByTestId("host-point-cr-p2");
    expect(said.className).toMatch(/said/);
    expect(within(said).getByLabelText("Said").querySelector("svg")).not.toBeNull();
    expect(todo.className).not.toMatch(/said/);
    expect(within(todo).queryByLabelText("Said")).toBeNull();
    expect(said).toHaveTextContent("Lightweight gel-cream. Absorbs quickly."); // the text stays whole
  });

  it("shows TIME SALE prices during a price promo", () => {
    render(
      view({
        session: session({
          active_promo_id: "promo_time_sale_10",
          promo_started_at: now(),
          active_promos: [{ promo_id: "promo_time_sale_10", started_at: now(), ends_at: now() + 600_000 }],
        }),
      }),
    );
    const prompter = screen.getByTestId("host-prompter");
    expect(within(prompter).getByText("TIME SALE")).toBeInTheDocument();
    expect(within(prompter).getByText("S$32.40")).toBeInTheDocument();
    expect(screen.getByTestId("host-promo-chip")).toHaveTextContent("TIME SALE");
  });
});

describe("fact note", () => {
  const fx = alert({
    alert_id: "fx_000001",
    kind: "fact",
    rule_id: null,
    severity: null,
    field: "price",
    stated_value: "S$32",
    correct_value: "S$36.00",
    passage_id: "DL-CR-01#key-facts#live-broadcast-price",
    quote: "Live broadcast price: S$36.00",
  });

  it("takes the prompter box: heard small, right value biggest, source; never struck through (D-107)", () => {
    render(view({ alerts: [fx] }));
    const note = within(screen.getByTestId("host-prompter")).getByTestId("host-fact-note");
    expect(screen.queryByTestId("host-point-cr-p1")).toBeNull(); // the product info gives way
    expect(note).toHaveTextContent("PRICE CORRECTION");
    expect(note).toHaveTextContent("Live broadcast price · Source: product sheet, Key facts");
    const wrong = screen.getByTestId("host-fact-wrong");
    expect(wrong).toHaveTextContent("Heard: ✕ S$32");
    // D-136: one line the host can read out, with the product
    // D-386: the line names what the value is, from the source's label
    expect(screen.getByTestId("host-fact-right")).toHaveTextContent("○ Cream: Live broadcast price is S$36.00");
    expect(wrong.closest("s, del, strike")).toBeNull();
    expect(wrong.querySelector("s, del, strike")).toBeNull();
    expect(wrong.style.textDecoration).not.toContain("line-through");
    expect(wrong.className).not.toMatch(/strike/i);
  });

  it("D-136: a promo price note names the product and the time sale", async () => {
    const { factSayLine } = await import("./hostSelectors");
    const promo = { ...fx, passage_id: null, correct_value: "S$32.40" };
    expect(factSayLine(catalog, { ...promo, quote: null }, "Time sale: extra 10% off"))
      .toBe("Cream: S$32.40 during the time sale");  // D-386: no source label: the value as the model wrote it
    expect(factSayLine(catalog, { ...fx, product_id: "set_cream_ampoule", quote: "Set price: S$62.00",
      correct_value: "S$62.00" }, null)).toBe("Cream + Ampoule set: Set price is S$62.00");
  });

  it("D-386: the say line names the ingredient, or keeps the model's sentence as it is", async () => {
    const { factSayLine } = await import("./hostSelectors");
    const ing = { ...fx, field: "ingredient_amount", stated_value: "45%", correct_value: "5%",
      passage_id: "DL-CR-01#prompter#ingredient-panthenol", quote: "Panthenol: 5%" };
    expect(factSayLine(catalog, ing, null)).toBe("Cream: Panthenol is 5%");
    expect(factSayLine(catalog, { ...ing, quote: "Claims not approved: Treats eczema",
      correct_value: "It does not treat eczema." }, null)).toBe("Cream: It does not treat eczema.");
    expect(factSayLine(catalog, { ...ing, quote: null }, null)).toBe("Cream: 5%");
  });

  it("a corrected fact shows the green Corrected in the box (D-107)", () => {
    const { rerender } = render(view({ alerts: [fx] }));
    rerender(view({ alerts: [{ ...fx, status: "corrected", resolved_at: now() }] }));
    expect(screen.queryByTestId("host-fact-note")).toBeNull();
    expect(within(screen.getByTestId("host-prompter")).getByTestId("host-corrected")).toHaveTextContent("Corrected");
  });

  it("stacks HIGH, then fact notes, then MEDIUM in the box (D-107), each from its own sentence (D-342)", () => {
    const high = alert({ alert_id: "al_000010", span: "erases wrinkles", transcript_id: "tr_high" });
    const medium = alert({ alert_id: "al_000011", rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM", span: "the best",
      transcript_id: "tr_medium" });
    render(view({ alerts: [medium, { ...fx, transcript_id: "tr_fact" }, high] }));
    const box = screen.getByTestId("host-prompter-alerts");
    expect([...box.children].map((c) => c.getAttribute("data-testid"))).toEqual([
      "host-compliance-overlay", "host-fact-note", "host-medium-banner"]);
  });

  it("is hidden after host_hidden_at and when corrected", () => {
    const { rerender } = render(view({ alerts: [{ ...fx, host_hidden_at: now() }] }));
    expect(screen.queryByTestId("host-fact-note")).toBeNull();
    rerender(view({ alerts: [{ ...fx, status: "corrected" }] }));
    expect(screen.queryByTestId("host-fact-note")).toBeNull();
  });

  it("names the active promotion as the source when there is no passage", () => {
    render(view({ alerts: [{ ...fx, field: "promo", passage_id: null, quote: null, correct_value: "S$32.40" }] }));
    expect(screen.getByTestId("host-fact-note")).toHaveTextContent("Source: active promotion");
  });

  it("D-376: an evidence-less ingredient note gets a neutral source and no promo condition", () => {
    const sale = session({ active_promo_id: "promo_time_sale_10", promo_started_at: now(),
      active_promos: [{ promo_id: "promo_time_sale_10", started_at: now(), ends_at: now() + 600_000 }] });
    render(view({ session: sale, alerts: [{ ...fx, field: "ingredient_amount", passage_id: null, quote: null,
      correct_value: "5%" }] }));
    const note = screen.getByTestId("host-fact-note");
    expect(note).toHaveTextContent("Source: AI fact check");
    expect(note).not.toHaveTextContent("active promotion");
    expect(screen.getByTestId("host-fact-right")).not.toHaveTextContent("during the");
  });
});

describe("compliance", () => {
  it("provisional: only the amber chip, no overlay", () => {
    render(view({ alerts: [alert({ status: "provisional", shown_at: null, provisional_at: now() })] }));
    expect(screen.getByTestId("host-checking-chip")).toHaveTextContent("Checking a phrase…");
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
  });

  it("HIGH: the newest alert takes the prompter box, 1 of N, render ack (D-106)", () => {
    const acts = actions();
    const older = alert({ alert_id: "al_000001", span: "older claim", shown_at: now() - 5000 });
    const newer = alert({ alert_id: "al_000002", span: "your wrinkles will disappear overnight", shown_at: now() - 1000 });
    render(view({ alerts: [older, newer] }, acts));
    const overlay = within(screen.getByTestId("host-prompter")).getByTestId("host-compliance-overlay");
    expect(screen.queryByTestId("host-point-cr-p1")).toBeNull(); // the product info gives way, nothing else moves
    expect(overlay).toHaveTextContent("HIGH-RISK CLAIM");
    expect(overlay).toHaveTextContent("Say this instead.");
    expect(overlay).toHaveTextContent("Helps keep skin hydrated for up to 24 hours in our in-house test.");
    expect(overlay).toHaveTextContent('Heard: "your wrinkles will disappear overnight"');
    expect(overlay).toHaveTextContent("Prevents, reduces or reverses physiological changes of ageing · Appendix III §3");
    expect(overlay).toHaveTextContent("Waiting for your correction");
    expect(screen.getByTestId("host-overlay-count")).toHaveTextContent("1 of 2");
    expect(screen.queryByTestId("host-unverified")).toBeNull();
    expect(acts.rendered).toHaveBeenCalledWith("al_000002");
  });

  it("unverified alert shows the AI check unavailable badge", () => {
    render(view({ alerts: [alert({ unverified: true })] }));
    expect(screen.getByTestId("host-unverified")).toHaveTextContent("AI check unavailable");
  });

  it("correction: a compact green Corrected line, with the product info at once below (D-115)", () => {
    const a = alert();
    const { rerender } = render(view({ alerts: [a] }));
    expect(screen.getByTestId("host-compliance-overlay")).toBeInTheDocument();
    rerender(view({ alerts: [{ ...a, status: "corrected", resolved_at: now() }] }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.getByTestId("host-point-cr-p1")).toBeInTheDocument();
    expect(within(screen.getByTestId("host-prompter")).getByTestId("host-corrected")).toHaveTextContent("Corrected");
  });

  it("the Corrected bar disappears after CORRECTED_TOAST_MS", () => {
    vi.useFakeTimers();
    try {
      const a = alert();
      const snap = { alerts: [a], session: session({ settings_snapshot: { CORRECTED_TOAST_MS: 1500 } }) };
      const { rerender } = render(view(snap));
      rerender(view({ ...snap, alerts: [{ ...a, status: "corrected", resolved_at: now() }] }));
      expect(screen.getByTestId("host-corrected")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(1600);
      });
      expect(screen.queryByTestId("host-corrected")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("dismiss closes the overlay without the green bar", () => {
    const a = alert();
    const { rerender } = render(view({ alerts: [a] }));
    rerender(view({ alerts: [{ ...a, status: "dismissed", dismissed_reason: "false_alarm" }] }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.queryByTestId("host-corrected")).toBeNull();
  });

  it("MEDIUM: a yellow block in the prompter box", () => {
    render(
      view({
        alerts: [alert({ rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM", span: "the best moisturiser in Singapore", say_instead: "It helps keep skin hydrated." })],
      }),
    );
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    const banner = within(screen.getByTestId("host-prompter")).getByTestId("host-medium-banner");
    expect(banner).toHaveTextContent("CHECK WORDING");
    expect(banner).toHaveTextContent('"the best moisturiser in Singapore"');
    expect(banner).toHaveTextContent("Say this instead.“It helps keep skin hydrated.”");
    expect(banner).toHaveTextContent("Comparative or superlative claims");
  });

  // D-105: a test number without "in our in-house test", with a wrong number on the same sentence
  const qualifier = alert({
    alert_id: "al_000002",
    transcript_id: "tr_000007",
    rule_id: "TEST-QUALIFIER",
    severity: "MEDIUM",
    span: "increased by seventy percent",
    say_instead: "In our in-house test, skin hydration went up 45% right after one use.",
  });
  const wrongNumber = alert({
    alert_id: "fx_000002",
    kind: "fact",
    transcript_id: "tr_000007",
    rule_id: null,
    severity: null,
    field: "test_result",
    stated_value: "+70%",
    correct_value: "+45%",
  });

  it("D-341: after 10 s the qualifier banner asks for the result again, with the qualifier", () => {
    render(view({ alerts: [{ ...qualifier, created_at: T0 - 11_000 }] }));
    expect(screen.getByTestId("host-medium-banner")).toHaveTextContent("Say the result again with where it comes from (e.g. 'in our in-house test')");
  });

  it("MEDIUM test qualifier: one card with the right number when the fact note is on the same sentence", () => {
    const { rerender } = render(view({ alerts: [qualifier] }));
    let banner = screen.getByTestId("host-medium-banner");
    expect(banner).toHaveTextContent("Say where the result comes from (e.g. 'in our in-house test')");
    expect(banner).toHaveTextContent("“In our in-house test, skin hydration went up 45% right after one use.”");
    expect(screen.queryByTestId("host-medium-fact")).toBeNull();

    // the fact checker finishes later: the same card gains the number, no second banner
    rerender(view({ alerts: [qualifier, wrongNumber] }));
    banner = screen.getByTestId("host-medium-banner");
    expect(within(banner).getByTestId("host-medium-fact")).toHaveTextContent("○ +45%(not +70%)");
    expect(screen.queryByTestId("host-fact-note")).toBeNull();

    // a fact note on another sentence keeps its own card
    rerender(view({ alerts: [qualifier, { ...wrongNumber, transcript_id: "tr_000008" }] }));
    expect(screen.queryByTestId("host-medium-fact")).toBeNull();
    expect(screen.getByTestId("host-fact-note")).toBeInTheDocument();
  });

  it("MEDIUM test qualifier without an approved sentence asks for the qualifier", () => {
    render(view({ alerts: [{ ...qualifier, say_instead: null }] }));
    expect(screen.getByTestId("host-medium-banner")).toHaveTextContent("Say the result with where it comes from (e.g. 'in our in-house test').");
  });
});

describe("audience questions", () => {
  it("D-113: a compact waiting list in slot order with each question's state and (D-384) its answer", () => {
    const g1 = group({ group_id: "grp_000001", canonical_question: "Is it suitable for oily skin?", answer_id: "ans_000001", unique_author_ids: ["a", "b", "c"] });
    const g2 = group({ group_id: "grp_000002", canonical_question: "Can I use it under makeup?", answer_id: "ans_000002" });
    const g3 = group({ group_id: "grp_000003", canonical_question: "How much is the set?", status: "auto_answered", route: "AUTO", answer_id: "ans_000003" });
    render(
      view({
        groups: [g1, g2, g3],
        answers: {
          ans_000001: answer(),
          ans_000002: answer({ answer_id: "ans_000002", group_id: "grp_000002", text: "Yes. Apply sunscreen after the cream, then makeup." }),
          ans_000003: answer({ answer_id: "ans_000003", group_id: "grp_000003", text: "The set is S$62.00." }),
        },
        host_slots: [
          { group_id: "grp_000002", pinned: true, on_host_since: now() },
          { group_id: "grp_000001", pinned: false, on_host_since: now() },
          { group_id: "grp_000003", pinned: false, on_host_since: now() },
        ],
      }),
    );
    const card = screen.getByTestId("host-questions");
    expect(card).toHaveTextContent("take the top one now");
    const items = within(card).getAllByRole("article");
    expect(items.map((i) => i.getAttribute("data-testid"))).toEqual([
      "host-question-grp_000002",
      "host-question-grp_000001",
      "host-question-grp_000003",
    ]);
    expect(items[0]).toHaveTextContent("01");
    expect(items[0]).toHaveTextContent("From your PD");
    expect(items[0]).toHaveTextContent("Ready");
    // D-384 (user): each question shows its suggested answer at once, no Q needed
    expect(within(items[0]).getByTestId("host-question-answer")).toHaveTextContent(
      "Yes. Apply sunscreen after the cream, then makeup.");
    expect(within(items[2]).getByTestId("host-question-answer")).toHaveTextContent("The set is S$62.00.");
    expect(items[1]).toHaveTextContent("3");
    expect(items[1]).not.toHaveTextContent("For you");
    expect(items[2]).toHaveTextContent("Read out");
  });

  it("D-113: drafting, which product and on-your-card states", () => {
    const drafting = group({ group_id: "grp_000004", status: "composing", answer_id: null });
    const which = group({ group_id: "grp_000005", status: "needs_review", route_reason: "unresolved_product", answer_id: null });
    const onCard = group({ group_id: "grp_000006", answer_id: "ans_000001" });
    render(
      view({
        session: session({ pd_card: pdCard({ ref_id: "grp_000006", status: "active" }) }),
        groups: [drafting, which, onCard],
        answers: { ans_000001: answer({ group_id: "grp_000006" }) },
        host_slots: [drafting, which, onCard].map((g) => ({ group_id: g.group_id, pinned: false, on_host_since: now() })),
      }),
    );
    const states = screen.getAllByTestId("host-question-state").map((e) => e.textContent);
    // D-127: the question on the card is no row any more; the card opened in its place
    expect(states).toEqual(["Drafting…", "Which product?"]);
    expect(within(screen.getByTestId("host-question-grp_000006")).getByTestId("host-pd-card")).toBeInTheDocument();
  });

  it("D-113: Q pulls the top waiting question", () => {
    const acts = actions();
    render(view({}, acts));
    fireEvent.keyDown(window, { key: "q" });
    fireEvent.keyDown(window, { key: "e" }); // D-138: +2 min on the on-air product
    expect(acts.extendSegment).toHaveBeenCalledTimes(1);
    expect(acts.pullQuestion).toHaveBeenCalledTimes(1);
  });

  it("shows the Posting answer chip while a host answer is pending", () => {
    const g = group({ answer_id: "ans_000001" });
    render(
      view({
        groups: [g],
        answers: { ans_000001: answer() },
        host_slots: [{ group_id: g.group_id, pinned: false, on_host_since: now() }],
        messages: [message({ kind: "host_answer", state: "pending", publish_at: now() + 2000, created_at: now(), published_at: null })],
      }),
    );
    expect(screen.getByTestId(`host-question-${g.group_id}`)).toHaveTextContent("Posting answer…");
  });

  it("D-178: a solo host sees only how many questions wait for the operator; a team host sees nothing", () => {
    const groups = [
      group({ group_id: "grp_ship", product_id: null, intent: "shipping", route: "OPERATOR", status: "needs_review" }),
      group({ group_id: "grp_prev", route: "OPERATOR", route_reason: "previous_product", status: "ready" }),
      group({ group_id: "grp_done", route: "OPERATOR", status: "answered" }),
      group({ group_id: "grp_host", route: "HOST", status: "ready" }),
    ];
    render(view({ session: session({ show_mode: "solo" }), groups }));
    expect(screen.getByTestId("host-unanswered")).toHaveTextContent("2 unanswered questions");
    expect(screen.queryByTestId("host-question-grp_ship")).toBeNull();
    cleanup();
    render(view({ session: session({ show_mode: "team" }), groups }));
    expect(screen.queryByTestId("host-unanswered")).toBeNull();
  });

  it("D-127: empty state is one dim line, not a block", () => {
    render(view());
    expect(screen.getByText("No questions waiting.")).toBeInTheDocument();
    expect(screen.queryByTestId("host-pd-slot")).toBeNull();
  });

  it("D-127: a question card opens in place of its own row; the question shows once", () => {
    const a = group({ group_id: "grp_a", canonical_question: "Can I use it under makeup?" });
    const b = group({ group_id: "grp_b", canonical_question: "Is it okay for oily skin?" });
    const card = pdCard({ card_id: "card_q", kind: "answer_question", ref_id: "grp_b", say: "Yes.", detail: "Is it okay for oily skin?", status: "active" });
    render(
      view({
        session: session({ pd_card: card }),
        groups: [a, b],
        host_slots: [
          { group_id: "grp_a", pinned: false, on_host_since: now() },
          { group_id: "grp_b", pinned: false, on_host_since: now() },
        ],
      }),
    );
    const rows = screen.getByTestId("host-questions").querySelectorAll('[data-testid^="host-question-grp_"]');
    expect([...rows].map((r) => r.getAttribute("data-testid"))).toEqual(["host-question-grp_a", "host-question-grp_b"]);
    expect(within(screen.getByTestId("host-question-grp_b")).getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getAllByText("Is it okay for oily skin?")).toHaveLength(1);
  });

  it("D-127: a non-question card goes on top of the list", () => {
    const a = group({ group_id: "grp_a" });
    const card = pdCard({ card_id: "card_p", kind: "promo", ref_id: "promo_time_sale_10", say: "Time sale now!", status: "active" });
    render(view({ session: session({ pd_card: card }), groups: [a], host_slots: [{ group_id: "grp_a", pinned: false, on_host_since: now() }] }));
    const list = screen.getByTestId("host-questions");
    const slot = within(list).getByTestId("host-pd-slot");
    expect(slot.compareDocumentPosition(screen.getByTestId("host-question-grp_a")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("chat and switch", () => {
  it("shows visible comments with replies and the pinned notice", () => {
    render(
      view({
        session: session({ pinned_notice: "Free pouch over S$60" }),
        comments: [comment(), comment({ comment_id: "cm_000002", author_name: "Amy", text: "So pretty!", group_id: null, kind: "reaction" })],
        messages: [message({ kind: "ai_answer", text: "It is S$36.00." })],
      }),
    );
    const chat = screen.getByTestId("host-chat");
    expect(within(chat).getByText("LIVE CHAT")).toBeInTheDocument();
    expect(within(chat).getByText("Connected")).toBeInTheDocument();
    expect(chat).toHaveTextContent("Free pouch over S$60");
    expect(chat).toHaveTextContent("Raj");
    expect(chat).toHaveTextContent("So pretty!");
    expect(within(chat).getByText("AI answer")).toBeInTheDocument();
  });

  it("switch banner counts down and Esc cancels", () => {
    const acts = actions();
    render(
      view(
        {
          session: session({
            switch: { status: "pending", target_product_id: AMPOULE, cue_count: 2, cue_transcript_ids: [], first_cue_at: now(), commit_at: now() + 3000, last_commit: null },
          }),
        },
        acts,
      ),
    );
    const banner = screen.getByTestId("host-switch-banner");
    expect(banner).toHaveTextContent("Switching to Deep Hydration Ampoule");
    expect(banner).toHaveTextContent("3");
    expect(banner).toHaveTextContent("Cancel switch (Esc)");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(acts.cancelSwitch).toHaveBeenCalledTimes(1);
  });

  it("cue strip shows the PD cue", () => {
    render(view({ session: session({ cue: { cue_id: "cue_000001", text: "Mention the patch test results.", preset_id: null, created_at: now(), status: "active", done_by_transcript_id: null } }) }));
    expect(screen.getByTestId("host-cue")).toHaveTextContent("FROM YOUR PD");
    expect(screen.getByTestId("host-cue")).toHaveTextContent("Mention the patch test results.");
  });
});

describe("judge health (D-137)", () => {
  it("is a neutral dot while the judges answer and amber when one failed on the last finals", () => {
    const { rerender } = render(view());
    expect(screen.getByTestId("host-judge-health")).toHaveAttribute("data-state", "ok");
    expect(screen.getByTestId("host-judge-health")).not.toHaveTextContent("AI check slow");
    rerender(view({ judge_health: { degraded: ["compliance_judge"] } }));
    expect(screen.getByTestId("host-judge-health")).toHaveAttribute("data-state", "degraded");
    expect(screen.getByTestId("host-judge-health")).toHaveTextContent("AI check slow");
  });
});

describe("AI PD card", () => {
  it("D-113: a question card shows the question and askers above the answer, in the fixed slot", () => {
    const card = pdCard({
      card_id: "card_ai_1",
      kind: "answer_question",
      say: "Yes. Apply sunscreen after the cream, then makeup.",
      detail: "Raj: Can I use it under makeup?",
      source: "ai",
      status: "active",
      askers: 4,
    });
    render(view({ session: session({ pd_card: card }) }));
    expect(within(screen.getByTestId("host-pd-slot")).getByTestId("host-pd-card")).toBeInTheDocument();
    const el = screen.getByTestId("host-pd-card");
    expect(el).toBeInTheDocument();
    expect(screen.getByTestId("host-pd-kind")).toHaveTextContent("Answer");
    expect(screen.getByTestId("host-pd-say")).toHaveTextContent("Yes. Apply sunscreen after the cream, then makeup.");
    expect(screen.getByTestId("host-pd-question")).toHaveTextContent("Raj: Can I use it under makeup?4 asking");
    expect(screen.getByText("AI PD")).toBeInTheDocument();
  });

  it("pressing N or clicking dismiss calls dismissPd with card_id", () => {
    const acts = actions();
    const card = pdCard({ card_id: "card_ai_2", status: "active" });
    render(view({ session: session({ pd_card: card }) }, acts));
    fireEvent.keyDown(window, { key: "n" });
    expect(acts.dismissPd).toHaveBeenCalledWith("card_ai_2");

    fireEvent.click(screen.getByTestId("host-pd-dismiss"));
    expect(acts.dismissPd).toHaveBeenCalledTimes(2);
  });

  it("sits below the prompter, so the prompter box never moves (D-107)", () => {
    render(view({ session: session({ pd_card: pdCard({ status: "active" }) }) }));
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getByTestId("host-prompter").previousElementSibling).toBeNull();
  });

  it("hidden while HIGH compliance overlay is active, returns after", () => {
    const card = pdCard({ card_id: "card_ai_3", status: "active" });
    const high = alert({ status: "active", severity: "HIGH", rule_id: "ASEAN-3-SKIN-AGEING", span: "erases wrinkles" });
    const { rerender } = render(view({ session: session({ pd_card: card }), alerts: [high] }));
    expect(screen.queryByTestId("host-pd-card")).toBeNull();
    expect(screen.getByTestId("host-compliance-overlay")).toBeInTheDocument();
    // one instruction at a time: the Q hint gives way to the correction
    expect(screen.getByTestId("host-questions-hint")).toHaveTextContent("Questions resume after the correction");

    // When alert is corrected or dismissed, card comes back
    rerender(view({ session: session({ pd_card: card }), alerts: [{ ...high, status: "corrected", resolved_at: now() }] }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getByTestId("host-questions-hint")).toHaveTextContent("take the top one now");
  });

  it("D-177: a red not corrected within 20 s stays full size and the card shows below it", () => {
    const card = pdCard({ card_id: "card_ai_5", status: "active" });
    const old = alert({ alert_id: "al_old", span: "erases wrinkles", created_at: T0 - RED_BLOCK_MS - 1000,
      escalated_at: T0 - RED_BLOCK_MS + 4000 });
    render(view({ session: session({ pd_card: card }), alerts: [old] }));
    expect(screen.getByTestId("host-compliance-overlay")).toHaveAttribute("data-fresh", "false");
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getByTestId("host-questions-hint")).toHaveTextContent("take the top one now");
    cleanup();
    // the same claim said again is a new alert: highlighted, and cards wait 20 s again
    const again = alert({ alert_id: "al_again", span: "erases wrinkles", created_at: T0 - 1000 });
    render(view({ session: session({ pd_card: card }), alerts: [old, again] }));
    expect(screen.getByTestId("host-compliance-overlay")).toHaveAttribute("data-fresh", "true");
    expect(screen.queryByTestId("host-pd-card")).toBeNull();
  });

  it("renders below CueStrip in team mode when both operator cue and AI PD card are active", () => {
    const cue = { cue_id: "cue_op_1", text: "Operator direction here", preset_id: null, created_at: now(), status: "active" as const, done_by_transcript_id: null };
    const card = pdCard({ card_id: "card_ai_4", kind: "cover_point", say: "Ceramide NP 1%, panthenol 5%, squalane 3%." });
    render(view({ session: session({ cue, pd_card: card }) }));
    expect(screen.getByTestId("host-cue")).toHaveTextContent("Operator direction here");
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getByTestId("host-pd-kind")).toHaveTextContent("Say this point");
    expect(screen.getByTestId("host-pd-say")).toHaveTextContent("Ceramide NP 1%, panthenol 5%, squalane 3%.");
  });

  it("shows done indicator when status is done, in the place of the answered question's row", () => {
    const a = group({ group_id: "grp_a" });
    const b = group({ group_id: "grp_000001" });
    const slots = [a, b].map((g) => ({ group_id: g.group_id, pinned: false, on_host_since: now() }));
    const active = pdCard({ card_id: "card_ai_5", status: "active" });
    const { rerender } = render(view({ session: session({ pd_card: active }), groups: [a, b], host_slots: slots }));
    // answered: the row leaves and the card turns done at the same moment
    rerender(view({ session: session({ pd_card: { ...active, status: "done", done_at: now() } }), groups: [a], host_slots: slots.slice(0, 1) }));
    expect(screen.getByTestId("host-pd-done")).toHaveTextContent("Done");
    expect(screen.queryByTestId("host-pd-dismiss")).toBeNull();
    const slot = screen.getByTestId("host-pd-slot");
    expect(screen.getByTestId("host-question-grp_a").compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("host chat: coalesced replies", () => {
  it("later askers get 'Also answered' (consistent with the viewer)", async () => {
    const { alsoAnsweredIds } = await import("./Chat");
    const m = message({ message_id: "msg_c", reply_to_comment_ids: ["cm_a", "cm_b"], reply_to_author_names: ["Lee", "Daniel"] });
    const items = [
      { kind: "comment" as const, at: 1, comment: comment({ comment_id: "cm_a", author_name: "Lee" }), replies: [m] },
      { kind: "comment" as const, at: 2, comment: comment({ comment_id: "cm_b", author_name: "Daniel" }), replies: [] },
    ];
    expect([...alsoAnsweredIds(items)]).toEqual(["cm_b"]);
  });
});

describe("settings and screen language (D-109)", () => {
  it("Korean labels; on-air text stays in the broadcast language", () => {
    setLang("ko");
    try {
      render(view({ alerts: [alert()] }));
      expect(screen.getByText("프롬프터")).toBeInTheDocument();
      const overlay = screen.getByTestId("host-compliance-overlay");
      expect(overlay).toHaveTextContent("이렇게 말하세요.");
      expect(overlay).toHaveTextContent("“Helps keep skin hydrated for up to 24 hours in our in-house test.”");
    } finally {
      act(() => setLang("en"));
    }
  });

  it("the gear switches the language and the theme", () => {
    const setTheme = vi.fn();
    try {
      render(<HostView state={{ ...reduceSnapshot(snapshot(), "host", now()), serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark"
        themePref="system" onSetTheme={setTheme} actions={actions()} />);
      fireEvent.click(screen.getByTestId("settings-button"));
      fireEvent.click(screen.getByLabelText("한국어"));
      expect(screen.getByText("프롬프터")).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText("다크"));
      expect(setTheme).toHaveBeenCalledWith("dark");
    } finally {
      act(() => setLang("en"));
    }
  });
});

describe("chat folding (D-115)", () => {
  it("later askers of one reply become a single note under the first asker", async () => {
    const { alsoAnsweredNames } = await import("./Chat");
    const reply = message({ message_id: "msg_9", reply_to_comment_ids: ["cm_a", "cm_b", "cm_c"] });
    const items = [
      { kind: "comment" as const, at: 1, comment: comment({ comment_id: "cm_a", author_name: "Ann" }), replies: [reply] },
      { kind: "comment" as const, at: 2, comment: comment({ comment_id: "cm_b", author_name: "Ben" }), replies: [] },
      { kind: "comment" as const, at: 3, comment: comment({ comment_id: "cm_c", author_name: "Cy" }), replies: [] },
    ];
    expect(alsoAnsweredNames(items as never).get("cm_a")).toEqual(["Ben", "Cy"]);
  });
});

describe("host panel sizes (D-181)", () => {
  it("two splitters resize the columns and rows by keyboard; double-click and the gear reset them", async () => {
    const { resetHostLayout } = await import("../../app/prefs");
    try {
      const { container } = render(<HostView state={{ ...reduceSnapshot(snapshot(), "host", now()), serverOffsetMs: 0 }}
        catalog={cat} connection="connected" theme="dark" themePref="system" onSetTheme={vi.fn()} actions={actions()} />);
      const cols = screen.getByTestId("host-split-cols");
      const rows = screen.getByTestId("host-split-rows");
      expect(cols).toHaveAttribute("role", "separator");
      expect(cols).toHaveAttribute("aria-orientation", "vertical");
      expect(rows).toHaveAttribute("aria-orientation", "horizontal");
      expect(cols).toHaveAttribute("aria-valuenow", "58");
      const main = cols.parentElement as HTMLElement;
      fireEvent.keyDown(cols, { key: "ArrowRight" });
      expect(cols).toHaveAttribute("aria-valuenow", "63");
      expect(main.style.gridTemplateColumns).toBe("minmax(0, 63fr) var(--split-gap) minmax(0, 37fr)");
      fireEvent.keyDown(rows, { key: "Home" });
      expect(rows).toHaveAttribute("aria-valuenow", "25");
      expect(JSON.parse(window.localStorage.getItem("ls.layout.host")!)).toEqual({ cols: 0.63, rows: 0.25 });
      fireEvent.keyDown(cols, { key: "End" });
      expect(cols).toHaveAttribute("aria-valuenow", "70"); // D-182: the chat keeps 30%
      expect(cols).toHaveAttribute("aria-valuemax", "70");
      fireEvent.doubleClick(cols);
      expect(cols).toHaveAttribute("aria-valuenow", "58");
      fireEvent.click(screen.getByTestId("settings-button"));
      fireEvent.click(screen.getByTestId("settings-reset-layout"));
      expect(rows).toHaveAttribute("aria-valuenow", "50");
      expect(container.querySelector('[data-screen="host"]')).not.toBeNull();
    } finally {
      act(() => resetHostLayout());
    }
  });
});

describe("back to the hub", () => {
  it("the brand links to the hub with the session; while live it asks once, Ctrl-click and a ready show do not", () => {
    window.history.pushState(null, "", "/host?session=ses_000001");
    const { unmount } = render(view({ session: session({ status: "live" }) }));
    const link = screen.getByTestId("hub-link");
    expect(link).toHaveAttribute("href", "/?session=ses_000001");
    expect(link).toHaveAccessibleName("Back to hub");
    fireEvent.click(link, { ctrlKey: true }); // a new tab: no question
    expect(screen.queryByTestId("hub-link-confirm")).toBeNull();
    fireEvent.click(link);
    expect(screen.getByTestId("hub-link-confirm")).toHaveTextContent("Leave this screen? The show keeps running.");
    fireEvent.click(screen.getByText("Stay"));
    expect(screen.queryByTestId("hub-link-confirm")).toBeNull();
    expect(window.location.pathname).toBe("/host");
    fireEvent.click(link);
    fireEvent.click(screen.getByText("Leave"));
    expect(window.location.pathname + window.location.search).toBe("/?session=ses_000001");
    unmount();
    window.history.pushState(null, "", "/host?session=ses_000001");
    render(view({ session: session({ status: "ready", started_at: null }) }));
    fireEvent.click(screen.getByTestId("hub-link"));
    expect(screen.queryByTestId("hub-link-confirm")).toBeNull();
    expect(window.location.pathname).toBe("/");
  });
});

describe("host settings: reading size and microphone (D-119)", () => {
  it("reading size scales the host screen and is remembered", async () => {
    const { setReadingSize } = await import("../../app/prefs");
    try {
      const { container } = render(view({}));
      const root = container.querySelector('[data-screen="host"]') as HTMLElement;
      const base = Number(root.style.getPropertyValue("--hs"));
      act(() => setReadingSize(1.5));
      expect(Number(root.style.getPropertyValue("--hs"))).toBeCloseTo(base * 1.5);
      expect(window.localStorage.getItem("ls.host.size")).toBe("1.5");
    } finally {
      act(() => setReadingSize(1));
    }
  });

  it("the gear lists microphones and remembers the choice", async () => {
    const devices = [{ kind: "audioinput", deviceId: "mic-usb", label: "USB mic" }];
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { enumerateDevices: async () => devices } });
    const { getMicDevice, setMicDevice } = await import("../../app/prefs");
    try {
      render(<HostView state={{ ...reduceSnapshot(snapshot(), "host", now()), serverOffsetMs: 0 }} catalog={cat}
        connection="connected" theme="dark" themePref="system" onSetTheme={vi.fn()} actions={actions()} />);
      fireEvent.click(screen.getByTestId("settings-button"));
      const select = screen.getByTestId("settings-mic") as HTMLSelectElement;
      await screen.findByText("USB mic");
      fireEvent.change(select, { target: { value: "mic-usb" } });
      expect(getMicDevice()).toBe("mic-usb");
    } finally {
      act(() => setMicDevice(null));
      vi.unstubAllGlobals();
    }
  });
});

describe("preview market (D-150)", () => {
  it("labels a preview market on the host top bar", () => {
    const { rerender } = render(view());
    expect(screen.queryByTestId("host-preview")).toBeNull();
    rerender(view({ market: { market: "MY", name: "Malaysia", lang: "en", tier: "preview" } }));
    expect(screen.getByTestId("host-preview")).toHaveTextContent("PREVIEW · Malaysia");
  });
});

describe("immediate switch (D-349)", () => {
  const started = (seq: number, at: number) => ({ seq, type: "segment.started", payload: segment({
    segment_id: "seg_000002", product_id: AMPOULE, order: 2, started_at: at, start_reason: "auto_speech" }) });

  it("an immediate switch shows one prompter and a Switched to … · Undo bar for 8 s; Esc undoes", () => {
    const at = Date.now();
    let s = reduceSnapshot(snapshot(), "host", at);
    s = reduceEvent(s, { seq: 11, type: "segment.switch_decided", payload: { transcript_id: "tr_000009", switch: true,
      target_product_id: AMPOULE, confidence: "high", reason: "moves on to the ampoule" } }, at);
    s = reduceEvent(s, started(12, at), at);
    expect(s.session?.switch.last_commit?.immediate).toBe(true);
    const acts = actions();
    const { rerender } = render(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={acts} />);
    expect(screen.getByTestId("host-switched-bar")).toHaveTextContent("Switched to Deep Hydration Ampoule");
    expect(screen.getByTestId("host-now")).toHaveTextContent("Deep Hydration Ampoule");
    expect(screen.queryByTestId("host-preview")).toBeNull(); // one prompter, no preview card
    fireEvent.keyDown(window, { key: "Escape" });
    expect(acts.undoSwitch).toHaveBeenCalledTimes(1);
    const old = { ...s, session: { ...s.session!, switch: { ...s.session!.switch,
      last_commit: { ...s.session!.switch.last_commit!, at: at - 8001 } } } };
    rerender(<HostView state={{ ...old, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={acts} />);
    expect(screen.queryByTestId("host-switched-bar")).toBeNull();
  });

  it("a two-step commit (no immediate verdict) shows no Undo bar", () => {
    const at = Date.now();
    const s = reduceEvent(reduceSnapshot(snapshot(), "host", at), started(11, at), at);
    expect(s.session?.switch.last_commit?.immediate).toBeUndefined();
    render(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={actions()} />);
    expect(screen.queryByTestId("host-switched-bar")).toBeNull();
  });
});

describe("line check (D-288)", () => {
  const ev = { seq: 11, type: "line.check", payload: { transcript_id: "tr_000009", text: "It suits eczema-prone skin.",
    rule_ids: ["ASEAN-2D-VULNERABLE"], phrases: ["eczema"] } };

  it("shows a neutral card below the alerts for 15 s, once per line", () => {
    const at = Date.now();
    const base = reduceSnapshot(snapshot(), "host", at);
    const s = reduceEvent(reduceEvent(base, ev, at), { ...ev, seq: 12 }, at);
    expect(s.lineChecks).toHaveLength(1);
    expect(activeLineCheck(s, at + LINE_CHECK_MS - 1)?.transcript_id).toBe("tr_000009");
    expect(activeLineCheck(s, at + LINE_CHECK_MS)).toBeNull();
    render(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={actions()} />);
    const card = within(screen.getByTestId("host-prompter-alerts")).getByTestId("host-line-check");
    expect(card).toHaveTextContent("It suits eczema-prone skin.");
    expect(card).toHaveTextContent("(eczema)");
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
  });
});

describe("check what was said (D-303)", () => {
  it("shows a possibly misheard number as heard, without the wrong mark", () => {
    const base = { alert_id: "fx_000009", kind: "fact" as const, rule_id: null, severity: null, field: "price",
      stated_value: "S$15", correct_value: "S$50.00", passage_id: "DL-CR-01#key-facts#live-broadcast-price",
      quote: "Live broadcast price: S$50.00" };
    render(view({ alerts: [alert({ ...base, heard_check: true })] }));
    const note = screen.getByTestId("host-fact-note");
    expect(note).toHaveTextContent("CHECK WHAT WAS SAID");
    expect(screen.getByTestId("host-fact-wrong")).toHaveTextContent("Heard: S$15");
    expect(screen.getByTestId("host-fact-wrong")).not.toHaveTextContent("✕");
    cleanup();
    render(view({ alerts: [alert(base)] }));
    expect(screen.getByTestId("host-fact-wrong")).toHaveTextContent("✕ S$15");
  });
});

describe("verifier wait (D-306)", () => {
  it("shows the grey checking chip while the verifier works, and no alert yet", () => {
    const at = Date.now();
    let s = reduceSnapshot(snapshot(), "host", at);
    s = reduceEvent(s, { seq: 11, type: "verify.started", payload: { transcript_id: "tr_000009", kind: "compliance" } }, at);
    render(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={actions()} />);
    expect(screen.getByTestId("host-checking-chip")).toBeInTheDocument();
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    cleanup();
    s = reduceEvent(s, { seq: 12, type: "verify.done", payload: { transcript_id: "tr_000009", kind: "compliance" } }, at);
    render(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={actions()} />);
    expect(screen.queryByTestId("host-checking-chip")).toBeNull();
  });

  it("labels an alert the verifier never answered", () => {
    const base = { alert_id: "fx_000010", kind: "fact" as const, rule_id: null, severity: null, field: "price",
      stated_value: "S$32", correct_value: "S$36.00", passage_id: "DL-CR-01#key-facts#live-broadcast-price",
      quote: "Live broadcast price: S$36.00", unverified: true, unverified_reason: "http_504" };
    render(view({ alerts: [alert(base)] }));
    expect(screen.getByTestId("host-unverified")).toHaveTextContent("Unverified (AI response delayed)");
  });
});

describe("D-332: UI QA", () => {
  it("shows the first 4 cautions and the rest behind +N more", () => {
    const many = Array.from({ length: 7 }, (_, i) => `Caution number ${i + 1}.`);
    const c7: Catalog = { ...cat, products: cat.products.map((p) => (p.product_id === CREAM ? { ...p, cautions: many } : p)) };
    const state = { ...reduceSnapshot(snapshot(), "host", Date.now()), serverOffsetMs: 0 };
    render(<HostView state={state} catalog={c7} connection="connected" theme="dark" actions={actions()} />);
    const box = screen.getByTestId("host-cautions");
    expect(within(box).getAllByText(/^Caution number/)).toHaveLength(4);
    fireEvent.click(screen.getByTestId("host-cautions-more"));
    expect(within(box).getAllByText(/^Caution number/)).toHaveLength(7);
    expect(screen.getByTestId("host-cautions-more")).toHaveTextContent("Show fewer");
  });
});
