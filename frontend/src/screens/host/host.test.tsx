import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { cloneElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { setLang, translate } from "../../app/i18n";
import { RED_BLOCK_MS, uncheckedStrip } from "../../app/selectors";
import { reduceEvent, reduceSnapshot } from "../../app/state";
import type { Catalog, StateSnapshot } from "../../app/types";
import { alert, AMPOULE, answer, catalog, comment, CREAM, creamItems, group, message, pdCard, segment, session, snapshot, T0 } from "../../test/fixtures";
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
  return { rendered: vi.fn(), undoSwitch: vi.fn(), dismissPd: vi.fn() };
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

  it("D-426: before the start the host shows the first product's items from the server", () => {
    render(view({ session: session({ status: "ready", started_at: null }), segments: [],
      prompter: { product_id: null as unknown as string, segment_id: null, covered_point_ids: [], required_total: 0,
        required_covered: 0, items: creamItems() } }));
    expect(screen.getByTestId("host-price-current")).toHaveTextContent("S$36.00");
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
    expect(screen.getByTestId("host-points-status")).not.toHaveTextContent(/required/);
  });

  it("D-107: status line with points and time left; the lead point is emphasised once from 80% of the time", () => {
    const at = (share: number) => view({ segments: [segment({ started_at: now() - 900_000 * share, covered_point_ids: ["cr-p2"] })] });
    const { rerender } = render(at(0.5));
    expect(screen.getByTestId("host-points-status")).toHaveTextContent(/^7:(29|30)$/);
    expect(screen.getByTestId("host-point-cr-p3")).not.toHaveAttribute("data-late");
    rerender(at(0.85));
    expect(screen.getByTestId("host-point-cr-p3")).toHaveAttribute("data-late", "true");
    expect(screen.getByTestId("host-point-cr-p3").className).toMatch(/leadLate/);
    rerender(at(1.1));
    expect(screen.getByTestId("host-points-status")).toHaveTextContent(/^\+1:(29|30) over$/);
  });

  it("user 10/10: the prompter shows no ingredients, cautions or wording to avoid", () => {
    render(view({}));
    expect(screen.queryByTestId("host-ing-panthenol")).toBeNull();
    expect(screen.queryByTestId("host-cautions")).toBeNull();
    expect(screen.queryByTestId("host-avoid")).toBeNull();
    expect(screen.getByTestId("host-price-current")).toHaveTextContent("S$36.00");
  });

  it("D-372: price lines are ticked by their ids only", () => {
    const { rerender } = render(view({}));
    for (const id of ["host-price-current", "host-price-struck", "host-price-set"]) {
      expect(screen.getByTestId(id)).toHaveAttribute("data-state", "todo");
    }
    rerender(view({ segments: [segment({ ticked_item_ids: [
      "DL-CR-01#prompter#live-price", "DL-CR-01#prompter#set-set_cream_ampoule", "DL-CR-01#prompter#caution-1",
      "DL-AM-01#prompter#list-price"] })] }));  // another product's id ticks nothing here
    expect(screen.getByTestId("host-price-current")).toHaveAttribute("data-state", "said");
    expect(within(screen.getByTestId("host-price-current")).getByLabelText("Said")).toBeInTheDocument();
    expect(screen.getByTestId("host-price-set")).toHaveAttribute("data-state", "said");
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
        // D-423: the server's items during the sale
        prompter: { product_id: CREAM, segment_id: "seg_000001", covered_point_ids: [], required_total: 2,
          required_covered: 0, items: creamItems(true) },
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
    // D-396: with no `say` from the model, the note shows its correct value
    expect(screen.getByTestId("host-fact-right")).toHaveTextContent("○ Cream: S$36.00");
    expect(wrong.closest("s, del, strike")).toBeNull();
    expect(wrong.querySelector("s, del, strike")).toBeNull();
    expect(wrong.style.textDecoration).not.toContain("line-through");
    expect(wrong.className).not.toMatch(/strike/i);
  });

  it("D-396: the say line is the product and the model's `say`, as it wrote it", async () => {
    const { factSayLine } = await import("./hostSelectors");
    const promo = { ...fx, passage_id: null, correct_value: "S$32.40",
      say: "The live price is S$32.40 during the time sale" };
    expect(factSayLine(catalog, promo)).toBe("Cream: The live price is S$32.40 during the time sale");
    expect(factSayLine(catalog, { ...fx, product_id: "set_cream_ampoule", say: "The set is S$62.00." }))
      .toBe("Cream + Ampoule set: The set is S$62.00.");
    const ing = { ...fx, field: "ingredient_amount", correct_value: "5%", quote: "Claims not approved: Treats eczema" };
    expect(factSayLine(catalog, { ...ing, say: "Panthenol is 5%" })).toBe("Cream: Panthenol is 5%");
    expect(factSayLine(catalog, ing)).toBe("Cream: 5%");  // no `say`: the correct value, never a code-built line
    // D-424: a blank say falls back to the value; with both blank there is no line at all
    expect(factSayLine(catalog, { ...ing, say: "  " })).toBe("Cream: 5%");
    expect(factSayLine(catalog, { ...ing, say: "", correct_value: " " })).toBe("");
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
    const { rerender } = render(view({ alerts: [medium, { ...fx, transcript_id: "tr_fact" }, high] }));
    const box = screen.getByTestId("host-prompter-alerts");
    // D-402: at most two boxes; the second carries "+N", the active alerts not shown
    expect([...box.children].map((c) => c.getAttribute("data-testid"))).toEqual([
      "host-compliance-overlay", "host-fact-note"]);
    expect(screen.getAllByTestId("host-alert-more")).toHaveLength(1);
    expect(within(screen.getByTestId("host-fact-note")).getByTestId("host-alert-more")).toHaveTextContent("+1");
    rerender(view({ alerts: [medium, { ...fx, transcript_id: "tr_fact" }] }));
    expect([...screen.getByTestId("host-prompter-alerts").children].map((c) => c.getAttribute("data-testid")))
      .toEqual(["host-fact-note", "host-medium-banner"]);
    expect(screen.queryByTestId("host-alert-more")).toBeNull();
  });

  it("D-407: two reds take the two boxes, the ring on the newest only; the rest is in +N (D-404, by id)", () => {
    const red1 = alert({ alert_id: "al_r1", span: "erases wrinkles", transcript_id: "tr_r1", created_at: now() - 1000,
      shown_at: now() - 1000 });
    const red2 = alert({ alert_id: "al_r2", span: "cures acne", transcript_id: "tr_r2", created_at: now() - 5000,
      shown_at: now() - 5000 });
    const note = { ...fx, transcript_id: "tr_fact" };
    const { rerender } = render(view({ alerts: [red1, red2, note] }));
    const reds = screen.getAllByTestId("host-compliance-overlay");
    expect(reds.map((r) => r.getAttribute("data-fresh"))).toEqual(["true", "false"]);
    expect(reds[0]).toHaveTextContent("erases wrinkles");
    expect(screen.queryByTestId("host-fact-note")).toBeNull();
    expect(within(reds[1]).getByTestId("host-alert-more")).toHaveTextContent("+1");
    // a MEDIUM on the red's own line is held back by D-342: counted too
    const held = alert({ alert_id: "al_held", rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM", span: "the best",
      transcript_id: "tr_r1" });
    rerender(view({ alerts: [red1, red2, note, held] }));
    expect(screen.getByTestId("host-alert-more")).toHaveTextContent("+2");
  });

  it("D-433: a red box from a cited regulation shows the document and section, never the rule-id slug", () => {
    const cited = alert({ alert_id: "al_cite", span: "cures arthritis", transcript_id: "tr_cite",
      rule_id: "kelmar-code#2-1", citation: "kelmar_code.pdf#2.1", cited_title: "Kelmar Code 2.1" });
    const { rerender } = render(view({ alerts: [cited] }));
    const box = screen.getByTestId("host-compliance-overlay");
    expect(box).toHaveTextContent("Kelmar Code 2.1");
    expect(box).not.toHaveTextContent("kelmar-code#2-1");
    // an alert stored before D-433 (no cited_title): the citation's file name without the extension and the section
    rerender(view({ alerts: [{ ...cited, cited_title: null }] }));
    expect(screen.getByTestId("host-compliance-overlay")).toHaveTextContent("kelmar_code 2.1");
    expect(screen.getByTestId("host-compliance-overlay")).not.toHaveTextContent("kelmar-code#2-1");
  });

  it("D-402: red says Regulation, orange says Product info, in the host's language", () => {
    const high = alert({ alert_id: "al_000010", span: "erases wrinkles", transcript_id: "tr_high" });
    const medium = alert({ alert_id: "al_000011", rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM", span: "the best",
      transcript_id: "tr_medium" });
    const { rerender } = render(view({ alerts: [high, { ...fx, transcript_id: "tr_fact" }] }));
    expect(within(screen.getByTestId("host-compliance-overlay")).getByTestId("host-alert-kind")).toHaveTextContent("Regulation");
    expect(within(screen.getByTestId("host-fact-note")).getByTestId("host-alert-kind")).toHaveTextContent("Product info");
    rerender(view({ alerts: [medium] }));
    expect(within(screen.getByTestId("host-medium-banner")).getByTestId("host-alert-kind")).toHaveTextContent("Product info");
    expect(translate("ko", "Regulation")).toBe("법규");
    expect(translate("ko", "Product info")).toBe("제품 정보");
  });

  it("D-426: a note with a blank say and a blank value shows no say line", () => {
    render(view({ alerts: [{ ...fx, say: " ", correct_value: "" }] }));
    expect(screen.getByTestId("host-fact-note")).toBeInTheDocument();
    expect(screen.queryByTestId("host-fact-right")).toBeNull();
  });

  it("stays until corrected (D-402: no hide timer)", () => {
    const { rerender } = render(view({ alerts: [{ ...fx, created_at: now() - 600_000, shown_at: now() - 600_000 }] }));
    expect(screen.getByTestId("host-fact-note")).toBeInTheDocument();
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
  it("HIGH: the newest alert takes the prompter box, 1 of N, render ack (D-106)", () => {
    const acts = actions();
    const older = alert({ alert_id: "al_000001", span: "older claim", shown_at: now() - 5000, transcript_id: "tr_older" });
    const newer = alert({ alert_id: "al_000002", span: "your wrinkles will disappear overnight", shown_at: now() - 1000 });
    render(view({ alerts: [older, newer] }, acts));
    // D-407: both reds have a box, the newest first
    const overlay = within(screen.getByTestId("host-prompter")).getAllByTestId("host-compliance-overlay")[0];
    expect(screen.queryByTestId("host-point-cr-p1")).toBeNull(); // the product info gives way, nothing else moves
    expect(overlay).toHaveTextContent("Regulation");
    expect(overlay).toHaveTextContent("Take it back, then say:");
    expect(overlay).toHaveTextContent("Helps keep skin hydrated for up to 24 hours in our in-house test.");
    expect(overlay).toHaveTextContent('Heard: "your wrinkles will disappear overnight"');
    expect(overlay).toHaveTextContent("Prevents, reduces or reverses physiological changes of ageing · Appendix III §3");
    expect(overlay).toHaveTextContent("Waiting for your correction");
    expect(screen.getAllByTestId("host-overlay-count").map((c) => c.textContent)).toEqual(["1 of 2", "2 of 2"]);
    expect(acts.rendered).toHaveBeenCalledWith("al_000002");
  });

  it("D-436: the red box puts the language pack's retraction phrase before say_instead", () => {
    const market = { market: "SG", name: "Singapore", lang: "en", tier: "live" as const,
      retraction_phrase: "Sorry, I take that back." };
    const { rerender } = render(view({ market, alerts: [alert({ say_instead: "Helps relieve the feeling of dryness." })] }));
    expect(screen.getByTestId("host-compliance-overlay")).toHaveTextContent(
      "Take it back, then say:“Sorry, I take that back. Helps relieve the feeling of dryness.”");
    rerender(view({ market, alerts: [alert({ say_instead: "" })] }));  // no say_instead: the phrase alone
    expect(screen.getByTestId("host-compliance-overlay")).toHaveTextContent(
      "Take it back, then say:“Sorry, I take that back.”");
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

  // D-427: a MEDIUM alert (a market rule) and a fact note on the same sentence: two cards, nothing merged
  const medium = alert({
    alert_id: "al_000002",
    transcript_id: "tr_000007",
    rule_id: "BRAND-SUPERLATIVE",
    severity: "MEDIUM",
    span: "the best cream in Singapore",
    say_instead: "It helps keep skin hydrated.",
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

  it("D-427: a MEDIUM card and a fact note on the same sentence are two cards", () => {
    render(view({ alerts: [medium, wrongNumber] }));
    const banner = screen.getByTestId("host-medium-banner");
    expect(banner).toHaveTextContent("CHECK WORDING");
    expect(banner).toHaveTextContent("“It helps keep skin hydrated.”");
    expect(banner).not.toHaveTextContent("+45%");
    expect(screen.getByTestId("host-fact-note")).toHaveTextContent("+45%");
  });

  it("D-399: two unresolved alerts of one MEDIUM rule show as one card with ×2, the newest", () => {
    const older = { ...medium, alert_id: "al_q_old", transcript_id: "tr_old", span: "the older claim",
      created_at: medium.created_at - 5000, shown_at: (medium.shown_at ?? medium.created_at) - 5000 };
    render(view({ alerts: [older, medium] }));
    const [card] = screen.getAllByTestId("host-medium-banner");
    expect(screen.getAllByTestId("host-medium-banner")).toHaveLength(1);
    expect(within(card).getByTestId("host-alert-count")).toHaveTextContent("×2");
    expect(card).toHaveTextContent("the best cream in Singapore");
  });

  it("a MEDIUM alert without a say_instead shows no line to say", () => {
    render(view({ alerts: [{ ...medium, say_instead: null }] }));
    expect(screen.getByTestId("host-medium-banner")).not.toHaveTextContent("Say this instead.");
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
    expect(within(card).queryByTestId("host-questions-hint")).toBeNull();  // D-429: no Q key hint
    const items = within(card).getAllByRole("article");
    expect(items.map((i) => i.getAttribute("data-testid"))).toEqual([
      "host-question-grp_000002",
      "host-question-grp_000001",
      "host-question-grp_000003",
    ]);
    expect(items[0]).toHaveTextContent(/^Q1/);  // D-469: Q and A labels carry the row number
    expect(items[0]).toHaveTextContent("A1Yes. Apply sunscreen");
    expect(items[0]).toHaveTextContent("From your PD");
    expect(within(items[0]).getByTestId("host-question-state")).toHaveTextContent("Ready to answer");
    // the first line of the suggested reply, in quiet text under the question, so the host can prepare
    expect(within(items[0]).getByTestId("host-question-preview")).toHaveTextContent("Yes. Apply sunscreen after the cream, then makeup.");
    // D-431: a read-out question shows its verified answer too (no AI PD card carries it since D-429)
    expect(within(items[2]).getByTestId("host-question-preview")).toHaveTextContent("The set is S$62.00.");
    expect(items[1]).toHaveTextContent("3");
    expect(items[1]).not.toHaveTextContent("For you");
    expect(items[2]).toHaveTextContent("Read out");
  });

  it("the waiting list previews only the first line of a verified reply, and nothing for an unverified draft", () => {
    const long = group({ group_id: "grp_000007", canonical_question: "Is it vegan?", answer_id: "ans_long" });
    const unverified = group({ group_id: "grp_000008", canonical_question: "Is it halal?", answer_id: "ans_unv" });
    render(
      view({
        groups: [long, unverified],
        answers: {
          ans_long: answer({ answer_id: "ans_long", group_id: "grp_000007", text: "First line to say.\nSecond line stays off the list." }),
          ans_unv: answer({ answer_id: "ans_unv", group_id: "grp_000008", verified: false, text: "Unchecked draft text." }),
        },
        host_slots: [long, unverified].map((g) => ({ group_id: g.group_id, pinned: false, on_host_since: now() })),
      }),
    );
    const previews = screen.getAllByTestId("host-question-preview");
    expect(previews).toHaveLength(1);
    expect(previews[0]).toHaveTextContent(/^First line to say\.$/);
    expect(screen.queryByText(/Unchecked draft text/)).toBeNull();
    expect(screen.getByTestId("host-question-grp_000008")).toHaveTextContent("No answer yet");
    expect(screen.getByTestId("host-question-grp_000008")).not.toHaveTextContent("A2");  // D-469: a dash, no chip
  });

  it("D-113: drafting and which product states; D-429: no question card, so no on-your-card state", () => {
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
    expect(states).toEqual(["Drafting…", "Which product?", "Ready to answer"]);
    expect(within(screen.getByTestId("host-question-grp_000006")).queryByTestId("host-pd-card")).toBeNull();
  });

  it("D-429: the host keys Q, N, E and Esc do nothing (the host is hands-free)", () => {
    const acts = actions();
    render(view({ session: session({ pd_card: pdCard({ card_id: "card_k", status: "active" }) }) }, acts));
    for (const key of ["q", "n", "e", "Escape"]) fireEvent.keyDown(window, { key });
    expect(acts.dismissPd).not.toHaveBeenCalled();
    expect(acts.undoSwitch).not.toHaveBeenCalled();
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

  it("D-127: a non-question card goes on top of the list", () => {
    const a = group({ group_id: "grp_a" });
    const card = pdCard({ card_id: "card_p", kind: "promo", ref_id: "promo_time_sale_10", say: "Time sale now!", status: "active" });
    render(view({ session: session({ pd_card: card }), groups: [a], host_slots: [{ group_id: "grp_a", pinned: false, on_host_since: now() }] }));
    const list = screen.getByTestId("host-questions");
    const slot = within(list).getByTestId("host-pd-slot");
    expect(slot.compareDocumentPosition(screen.getByTestId("host-question-grp_a")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("D-469: a re-render keeps the list where the host scrolled it; a new card is scrolled into view", () => {
    // jsdom has no layout: the list is 100-300 px, the card box sits below it at 350-400 px
    const tops = new WeakMap<Element, number>();
    const spies = [
      vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(100),
      vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(100),
      vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(100),
      vi.spyOn(Element.prototype, "scrollTop", "get").mockImplementation(function (this: Element) {
        return tops.get(this) ?? 0;
      }),
      vi.spyOn(Element.prototype, "scrollTop", "set").mockImplementation(function (this: Element, v: number) {
        tops.set(this, v);
      }),
      vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
        const slot = this.getAttribute("data-testid") === "host-pd-slot";
        return { top: slot ? 350 : 100, bottom: slot ? 400 : 300 } as DOMRect;
      }),
    ];
    try {
      const a = group({ group_id: "grp_a" });
      const slots = [{ group_id: a.group_id, pinned: false, on_host_since: now() }];
      const shown = (id: string) =>
        view({ session: session({ pd_card: pdCard({ card_id: id, kind: "promo", status: "active" }) }), groups: [a], host_slots: slots });
      const { rerender } = render(shown("card_1"));
      const list = screen.getByTestId("host-pd-slot").parentElement!;
      expect(list.scrollTop).toBe(100);
      list.scrollTop = 7;  // the host scrolls the list
      rerender(shown("card_1"));  // the 250 ms clock tick
      expect(list.scrollTop).toBe(7);
      rerender(shown("card_2"));
      expect(list.scrollTop).toBe(107);
    } finally {
      spies.forEach((s) => s.mockRestore());
    }
  });
});

describe("chat and switch", () => {
  it("D-477: the viewer count sits in the live chat header, not in the questions panel", () => {
    render(cloneElement(view(), { audience: 5 }));
    expect(within(screen.getByTestId("host-chat")).getByTestId("audience-count")).toHaveTextContent("5 watching");
    expect(within(screen.getByTestId("host-questions")).queryByTestId("audience-count")).toBeNull();
    cleanup();
    render(view());  // unknown: nothing
    expect(screen.queryByTestId("audience-count")).toBeNull();
  });

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
  it("clicking dismiss calls dismissPd with card_id (D-429: no N key)", () => {
    const acts = actions();
    const card = pdCard({ card_id: "card_ai_2", status: "active" });
    render(view({ session: session({ pd_card: card }) }, acts));
    fireEvent.click(screen.getByTestId("host-pd-dismiss"));
    expect(acts.dismissPd).toHaveBeenCalledWith("card_ai_2");
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
    // one instruction at a time: the cards wait for the correction
    expect(screen.getByTestId("host-questions-hint")).toHaveTextContent("Questions resume after the correction");

    // When alert is corrected or dismissed, card comes back
    rerender(view({ session: session({ pd_card: card }), alerts: [{ ...high, status: "corrected", resolved_at: now() }] }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.queryByTestId("host-questions-hint")).toBeNull();  // D-429: no Q key hint
  });

  it("D-177: a red not corrected within 20 s stays full size and the card shows below it", () => {
    const card = pdCard({ card_id: "card_ai_5", status: "active" });
    const old = alert({ alert_id: "al_old", span: "erases wrinkles", created_at: T0 - RED_BLOCK_MS - 1000,
      shown_at: T0 - RED_BLOCK_MS - 1000, escalated_at: T0 - RED_BLOCK_MS + 4000 });
    render(view({ session: session({ pd_card: card }), alerts: [old] }));
    expect(screen.getByTestId("host-compliance-overlay")).toHaveAttribute("data-fresh", "false");
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.queryByTestId("host-questions-hint")).toBeNull();  // D-429: no Q key hint
    cleanup();
    // the same claim said again is a new alert: highlighted, and cards wait 20 s again
    const again = alert({ alert_id: "al_again", span: "erases wrinkles", created_at: T0 - 1000, shown_at: T0 - 1000,
      transcript_id: "tr_again" });  // said again: another line (D-442 groups only one line's alerts)
    render(view({ session: session({ pd_card: card }), alerts: [old, again] }));
    // D-407: the ring only on the newest red
    expect(screen.getAllByTestId("host-compliance-overlay").map((o) => o.getAttribute("data-fresh"))).toEqual(["true", "false"]);
    expect(screen.queryByTestId("host-pd-card")).toBeNull();
  });

  it("D-402: an orange alert blocks the card for 20 s like a red, and stays after", () => {
    const card = pdCard({ card_id: "card_ai_6", status: "active" });
    const note = alert({ alert_id: "fx_new", kind: "fact", rule_id: null, severity: null, field: "price",
      stated_value: "S$32", correct_value: "S$36", created_at: T0 - 1000 });
    const { rerender } = render(view({ session: session({ pd_card: card }), alerts: [note] }));
    expect(screen.queryByTestId("host-pd-card")).toBeNull();
    expect(screen.getByTestId("host-questions-hint")).toHaveTextContent("Questions resume after the correction");
    const old = { ...note, created_at: T0 - RED_BLOCK_MS - 1000, shown_at: T0 - RED_BLOCK_MS - 1000 };
    rerender(view({ session: session({ pd_card: card }), alerts: [old] }));
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getByTestId("host-fact-note")).toBeInTheDocument();
    const medium = alert({ alert_id: "al_med", rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM", span: "the best",
      created_at: T0 - 1000 });
    rerender(view({ session: session({ pd_card: card }), alerts: [medium] }));
    expect(screen.queryByTestId("host-pd-card")).toBeNull();
  });

  it("renders below CueStrip in team mode when both operator cue and AI PD card are active", () => {
    const cue = { cue_id: "cue_op_1", text: "Operator direction here", preset_id: null, created_at: now(), status: "active" as const, done_by_transcript_id: null };
    const card = pdCard({ card_id: "card_ai_4", kind: "shout_out", say: "Ceramide NP 1%, panthenol 5%, squalane 3%." });
    render(view({ session: session({ cue, pd_card: card }) }));
    expect(screen.getByTestId("host-cue")).toHaveTextContent("Operator direction here");
    expect(screen.getByTestId("host-pd-card")).toBeInTheDocument();
    expect(screen.getByTestId("host-pd-kind")).toHaveTextContent("Shout-out");
    expect(screen.getByTestId("host-pd-say")).toHaveTextContent("Ceramide NP 1%, panthenol 5%, squalane 3%.");
  });

  it("shows done indicator when status is done, on top of the list", () => {
    const a = group({ group_id: "grp_a" });
    const slots = [{ group_id: a.group_id, pinned: false, on_host_since: now() }];
    const active = pdCard({ card_id: "card_ai_5", status: "active" });
    const { rerender } = render(view({ session: session({ pd_card: active }), groups: [a], host_slots: slots }));
    rerender(view({ session: session({ pd_card: { ...active, status: "done", done_at: now() } }), groups: [a], host_slots: slots }));
    expect(screen.getByTestId("host-pd-done")).toHaveTextContent("Done");
    expect(screen.queryByTestId("host-pd-dismiss")).toBeNull();
    const slot = screen.getByTestId("host-pd-slot");
    expect(slot.compareDocumentPosition(screen.getByTestId("host-question-grp_a")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("host chat: AI answers", () => {
  it("shows the reply and its AI answer label, never the source behind it", () => {
    render(
      view({
        comments: [comment({ comment_id: "cm_1", group_id: null, text: "how much is it?", author_name: "Lee" })],
        messages: [
          message({
            message_id: "m_ai",
            reply_to_comment_ids: ["cm_1"],
            text: "It is S$36.00 during the live.",
            citations: [{ passage_id: "DL-CR-01#key-facts#live-broadcast-price", quote: "Live broadcast price: S$36.00", section: "Key facts" }],
          }),
        ],
      }),
    );
    const chat = screen.getByTestId("host-chat");
    expect(within(chat).getByText("It is S$36.00 during the live.")).toBeInTheDocument();
    expect(within(chat).getByText("AI answer")).toBeInTheDocument();
    expect(within(chat).queryByTestId("host-citation")).toBeNull();
    expect(chat).not.toHaveTextContent("Key facts");
    expect(chat).not.toHaveTextContent("Live broadcast price");
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
      expect(overlay).toHaveTextContent("먼저 철회하고, 이렇게 말하세요:");
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

  it("an immediate switch shows one prompter and a Switched to … · Undo bar for 8 s; its button undoes", () => {
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
    fireEvent.keyDown(window, { key: "Escape" });  // D-429: no Esc key
    expect(acts.undoSwitch).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByTestId("host-switched-bar")).getByRole("button", { name: "Undo" }));
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

describe("unchecked lines (D-412)", () => {
  const ev = (seq: number, id: string, cause: string, agent = "compliance_judge", at = T0 + seq, n = seq) =>
    ({ seq, type: "judge.failed", payload: { transcript_id: id, agent, cause, at, n } });
  const strip = (s: ReturnType<typeof reduceSnapshot>) => uncheckedStrip(s);
  const show = (s: ReturnType<typeof reduceSnapshot>) =>
    render(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={actions()} />);

  it("collapses every unchecked line into one strip, named by the latest cause, never an alert box", () => {
    let s = reduceSnapshot(snapshot(), "host");
    s = reduceEvent(s, ev(11, "tr_1", "busy"));
    s = reduceEvent(s, ev(12, "tr_1", "busy", "fact_checker"));  // the other judge of the same line: one line
    s = reduceEvent(s, ev(13, "tr_2", "timeout"));
    const { rerender } = show(s);
    expect(screen.getByTestId("host-unchecked")).toHaveTextContent("AI slow: 2 lines unchecked");
    expect(screen.queryByTestId("host-prompter-alerts")).toBeNull();
    s = reduceEvent(s, { seq: 14, type: "checks.recovered", payload: { transcript_id: "tr_3", cleared: ["tr_1", "tr_2"], at: 1 } });
    rerender(<HostView state={{ ...s, serverOffsetMs: 0 }} catalog={cat} connection="connected" theme="dark" actions={actions()} />);
    expect(screen.queryByTestId("host-unchecked")).toBeNull();
  });

  it("D-416: a recovery clears only the lines the server names; counts and cause match a refresh", () => {
    let s = reduceSnapshot(snapshot(), "host");
    s = reduceEvent(s, ev(11, "tr_b", "busy"));
    s = reduceEvent(s, ev(12, "tr_b", "timeout", "fact_checker"));
    s = reduceEvent(s, { seq: 13, type: "checks.recovered", payload: { transcript_id: "tr_a", cleared: [], at: 1 } });
    expect(strip(s)).toEqual({ count: 1, cause: "timeout" });  // A's late success leaves B
    expect(s.judgeFailures.map((j) => [j.agent, j.cause])).toEqual([["compliance_judge", "busy"], ["fact_checker", "timeout"]]);
    const events = [{ transcript_id: "tr_b", agent: "compliance_judge", cause: "busy", at: T0 + 11, n: 11 },
      { transcript_id: "tr_b", agent: "fact_checker", cause: "timeout", at: T0 + 12, n: 12 }];
    const refreshed = reduceSnapshot(snapshot({ check_failures: { recent: events, unchecked: events } }), "host");
    expect(strip(refreshed)).toEqual(strip(s));
    expect(refreshed.judgeFailures.map((j) => [j.agent, j.cause])).toEqual(s.judgeFailures.map((j) => [j.agent, j.cause]));
  });

  it("D-420: after a partial recovery the strip names the latest cause of the lines still unchecked; ties by n", () => {
    let s = reduceSnapshot(snapshot(), "host");
    s = reduceEvent(s, ev(11, "tr_1", "busy"));
    s = reduceEvent(s, ev(12, "tr_2", "timeout"));
    s = reduceEvent(s, { seq: 13, type: "checks.recovered", payload: { transcript_id: "tr_x", cleared: ["tr_2"], at: 1 } });
    expect(strip(s)).toEqual({ count: 1, cause: "busy" });  // not tr_2's "timeout"
    let t = reduceSnapshot(snapshot(), "host");
    t = reduceEvent(t, ev(21, "tr_3", "timeout", "compliance_judge", T0, 7));
    t = reduceEvent(t, ev(22, "tr_4", "busy", "compliance_judge", T0, 6));  // same at, an earlier n
    expect(strip(t).cause).toBe("timeout");
  });

  it("is kept on refresh from the snapshot, and reads in Korean", () => {
    const s = reduceSnapshot(snapshot({ check_failures: { recent: [],
      unchecked: [{ transcript_id: "tr_1", agent: "compliance_judge", cause: "busy", at: T0, n: 1 }] } }), "host");
    show(s);
    expect(screen.getByTestId("host-unchecked")).toHaveTextContent("AI busy: 1 line unchecked");
    expect(translate("ko", "{cause}: {n} lines unchecked", { cause: translate("ko", "AI busy"), n: 3 }))
      .toBe("AI 혼잡: 확인 못 한 문장 3개");
  });
});

describe("fact note (D-435: no heard-check variant)", () => {
  it("marks the wrong value it heard", () => {
    const base = { alert_id: "fx_000009", kind: "fact" as const, rule_id: null, severity: null, field: "price",
      stated_value: "S$15", correct_value: "S$50.00", passage_id: "DL-CR-01#key-facts#live-broadcast-price",
      quote: "Live broadcast price: S$50.00" };
    render(view({ alerts: [alert(base)] }));
    expect(screen.getByTestId("host-fact-wrong")).toHaveTextContent("✕ S$15");
  });
});

describe("D-332: UI QA", () => {
  it("D-426: a verdict that cites an item id ticks it: the sale price", () => {
    const s = snapshot({
      session: session({ active_promo_id: "promo_time_sale_10", promo_started_at: T0,
        active_promos: [{ promo_id: "promo_time_sale_10", started_at: T0, ends_at: T0 + 600_000 }] }),
      segments: [segment({ ticked_item_ids: ["DL-CR-01#prompter#sale-price-promo_time_sale_10"] })],
      prompter: { product_id: CREAM, segment_id: "seg_000001", covered_point_ids: [], required_total: 2,
        required_covered: 0, items: creamItems(true) } });
    render(<HostView state={{ ...reduceSnapshot(s, "host", Date.now()), serverOffsetMs: 0 }} catalog={cat}
      connection="connected" theme="dark" actions={actions()} />);
    expect(screen.getByTestId("host-price-current")).toHaveAttribute("data-state", "said");
  });

  it("D-423: shows every set the server lists", () => {
    const items = [...creamItems(),
      { id: "DL-CR-01#prompter#set-trio", key: "set-trio", product_id: CREAM, section: "Price & offers", kind: "set" as const,
        text: "Set Trio: S$80.00", label: "Trio", value: "S$80.00" }];
    const s = snapshot({ prompter: { product_id: CREAM, segment_id: "seg_000001", covered_point_ids: [], required_total: 2,
      required_covered: 0, items } });
    render(<HostView state={{ ...reduceSnapshot(s, "host", Date.now()), serverOffsetMs: 0 }} catalog={cat}
      connection="connected" theme="dark" actions={actions()} />);
    expect(screen.getAllByTestId("host-price-set").map((x) => x.textContent)).toEqual(
      ["Set Cream + Ampoule set S$62.00", "Set Trio S$80.00"]);
  });
});

describe("D-439: shown and cleared times on the host's boxes", () => {
  const tr = (id: string, end: number, source: "mic" | "injected" = "mic") => ({
    transcript_id: id, text: "x", is_final: true, speech_start_at: null, speech_end_at: end, received_at: end,
    source, segment_id: "seg_000001" });
  const red = alert({ transcript_id: "tr_1", shown_at: T0 + 4200 });
  const fact = alert({ alert_id: "fx_1", kind: "fact", rule_id: null, severity: null, field: "price", stated_value: "S$32",
    correct_value: "S$36.00", passage_id: "DL-CR-01#key-facts#live-broadcast-price", quote: "Live broadcast price: S$36.00",
    transcript_id: "tr_2", shown_at: T0 + 2500 });

  it("the red box and the orange note say how fast they were shown, grey, at the end of the bottom row", () => {
    render(view({ alerts: [red, fact], transcripts: [tr("tr_1", T0), tr("tr_2", T0)] }));
    const red_ = screen.getByTestId("host-compliance-overlay");
    expect(within(red_).getByTestId("host-alert-timing")).toHaveTextContent(/^Shown in 4\.2 s$/);
    expect(within(screen.getByTestId("host-fact-note")).getByTestId("host-alert-timing")).toHaveTextContent(/^Shown in 2\.5 s$/);
  });

  it("a typed line is marked, and nothing shows without the line", () => {
    render(view({ alerts: [red], transcripts: [tr("tr_1", T0, "injected")] }));
    expect(screen.getByTestId("host-alert-timing")).toHaveTextContent(/^Shown in 4\.2 s \(typed\)$/);
    cleanup();
    render(view({ alerts: [red] }));
    expect(screen.queryByTestId("host-alert-timing")).toBeNull();
  });

  it("the green cleared bar says how fast the correcting line cleared it", () => {
    const ts = [tr("tr_1", T0), tr("tr_3", T0 + 10_000)];
    const { rerender } = render(view({ alerts: [red], transcripts: ts }));
    rerender(view({ alerts: [{ ...red, status: "corrected", corrected_by_transcript_id: "tr_3", resolved_at: T0 + 13_100 }],
      transcripts: ts }));
    expect(screen.getByTestId("host-corrected")).toHaveTextContent("Corrected");
    expect(within(screen.getByTestId("host-corrected")).getByTestId("host-alert-timing")).toHaveTextContent(/^Cleared in 3\.1 s$/);
  });
});

describe("D-442: a line's red and orange in one box", () => {
  const tr = (id: string, end: number) => ({ transcript_id: id, text: "x", is_final: true, speech_start_at: null,
    speech_end_at: end, received_at: end, source: "mic" as const, segment_id: "seg_000001" });
  const red = alert({ alert_id: "al_g", transcript_id: "tr_g", shown_at: T0 + 4200, say_instead: "Helps relieve the feeling of dryness." });
  const note = alert({ alert_id: "fx_g", kind: "fact", transcript_id: "tr_g", rule_id: null, severity: null, field: "price",
    stated_value: "S$32", correct_value: "S$36.00", passage_id: "DL-CR-01#key-facts#live-broadcast-price",
    quote: "Live broadcast price: S$36.00", say: "The live price is S$36.00.", shown_at: T0 + 4500 });
  const ts = [tr("tr_g", T0), tr("tr_fix", T0 + 10_000)];
  const done = (a: typeof red) => ({ ...a, status: "corrected" as const, corrected_by_transcript_id: "tr_fix",
    resolved_at: T0 + 12_000 });

  it("one box: the count and kinds, the red's line big, the orange's line below as 'Then:', each with its timing", () => {
    render(view({ alerts: [red, note], transcripts: ts }));
    const box = screen.getByTestId("host-compliance-overlay");
    expect(screen.queryByTestId("host-fact-note")).toBeNull();
    expect(within(box).getByTestId("host-alert-group")).toHaveTextContent("2 issues: Regulation + Product info");
    const then = within(box).getByTestId("host-alert-then");
    expect(then).toHaveTextContent("Then:");
    expect(then).toHaveTextContent("The live price is S$36.00.");
    expect(within(box).getAllByTestId("host-alert-timing").map((x) => x.textContent)).toEqual(["Shown in 4.5 s", "Shown in 4.2 s"]);
    expect(translate("ko", "{n} issues: {kinds}", { n: 2, kinds: "법규 + 제품 정보" })).toBe("2개 문제: 법규 + 제품 정보");
    expect(translate("ko", "Then:")).toBe("그리고:");
  });

  it("the orange cleared first: '1 left' and only the red's line; no green 'Corrected' yet", () => {
    const { rerender } = render(view({ alerts: [red, note], transcripts: ts }));
    rerender(view({ alerts: [red, done(note)], transcripts: ts }));
    const box = screen.getByTestId("host-compliance-overlay");
    expect(within(box).getByTestId("host-alert-group")).toHaveTextContent("1 left");
    expect(within(box).queryByTestId("host-alert-then")).toBeNull();
    expect(screen.queryByTestId("host-corrected")).toBeNull();
  });

  it("the red cleared first: a normal orange note, and no 'Corrected' while the orange is active", () => {
    const { rerender } = render(view({ alerts: [red, note], transcripts: ts }));
    rerender(view({ alerts: [done(red), note], transcripts: ts }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.getByTestId("host-fact-note")).toBeInTheDocument();
    expect(screen.queryByTestId("host-corrected")).toBeNull();
  });

  it("all cleared: the box goes and the green 'Corrected' shows", () => {
    const { rerender } = render(view({ alerts: [red, note], transcripts: ts }));
    rerender(view({ alerts: [done(red), done(note)], transcripts: ts }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.queryByTestId("host-fact-note")).toBeNull();
    expect(screen.getByTestId("host-corrected")).toHaveTextContent("Corrected");
  });
});
