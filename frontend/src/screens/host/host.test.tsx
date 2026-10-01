import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { reduceSnapshot } from "../../app/state";
import type { Catalog, StateSnapshot } from "../../app/types";
import { alert, AMPOULE, answer, catalog, comment, CREAM, group, message, segment, session, snapshot } from "../../test/fixtures";
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
  return { rendered: vi.fn(), cancelSwitch: vi.fn() };
}

function view(over: Partial<StateSnapshot> = {}, acts: HostActions = actions()) {
  const state = reduceSnapshot(snapshot(over), "host", Date.now());
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
    expect(screen.getByTestId("host-point-cr-p1")).toHaveAttribute("data-state", "focus");
  });

  it("shows LIVE and End of run sheet on the last product", () => {
    render(view({ session: session({ started_at: now() - 5000 }), segments: [segment({ product_id: AMPOULE, started_at: now() - 1000 })] }));
    expect(within(screen.getByTestId("host-topbar")).getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("host-now")).toHaveTextContent("Deep Hydration Ampoule");
    expect(screen.getByTestId("host-next")).toHaveTextContent("End of run sheet");
  });
});

describe("prompter", () => {
  it("renders said, focus and todo points with required labels", () => {
    render(view({ segments: [segment({ covered_point_ids: ["cr-p1"] })] }));
    expect(screen.getByTestId("host-point-cr-p1")).toHaveAttribute("data-state", "said");
    expect(screen.getByTestId("host-point-cr-p2")).toHaveAttribute("data-state", "focus");
    expect(screen.getByTestId("host-point-cr-p3")).toHaveAttribute("data-state", "todo");
    expect(screen.getAllByText("REQUIRED POINT")).toHaveLength(2);
    expect(screen.getByTestId("host-required-count")).toHaveTextContent("0 / 2 required points");
    expect(screen.getByText("YOUR PROMPTER")).toBeInTheDocument();
    expect(screen.getByText("LIVE PRICE")).toBeInTheDocument();
    expect(screen.getByText("S$36.00")).toBeInTheDocument();
    expect(screen.getByText("Keep it natural.")).toBeInTheDocument();
  });

  it("counts covered required points and drops the label", () => {
    render(view({ segments: [segment({ covered_point_ids: ["cr-p1", "cr-p2"] })] }));
    expect(screen.getByTestId("host-required-count")).toHaveTextContent("1 / 2 required points");
    expect(screen.getAllByText("REQUIRED POINT")).toHaveLength(1);
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

  it("shows wrong -> right with source, and never strikes through the wrong value", () => {
    render(view({ alerts: [fx] }));
    const note = screen.getByTestId("host-fact-note");
    expect(note).toHaveTextContent("Price correction");
    expect(note).toHaveTextContent("Live broadcast price · Source: product sheet, Key facts");
    expect(note).toHaveTextContent("SAY THE UPDATED PRICE");
    const wrong = screen.getByTestId("host-fact-wrong");
    expect(wrong).toHaveTextContent("✕ S$32");
    expect(screen.getByTestId("host-fact-right")).toHaveTextContent("○ S$36.00");
    expect(wrong.closest("s, del, strike")).toBeNull();
    expect(wrong.querySelector("s, del, strike")).toBeNull();
    expect(wrong.style.textDecoration).not.toContain("line-through");
    expect(wrong.className).not.toMatch(/strike/i);
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
});

describe("compliance", () => {
  it("provisional: only the amber chip, no overlay", () => {
    render(view({ alerts: [alert({ status: "provisional", shown_at: null, provisional_at: now() })] }));
    expect(screen.getByTestId("host-checking-chip")).toHaveTextContent("Checking a phrase…");
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
  });

  it("HIGH: full-screen overlay for the newest alert, 1 of N, render ack", () => {
    const acts = actions();
    const older = alert({ alert_id: "al_000001", span: "older claim", shown_at: now() - 5000 });
    const newer = alert({ alert_id: "al_000002", span: "your wrinkles will disappear overnight", shown_at: now() - 1000 });
    render(view({ alerts: [older, newer] }, acts));
    const overlay = screen.getByTestId("host-compliance-overlay");
    expect(overlay).toHaveTextContent("HIGH-RISK CLAIM");
    expect(overlay).toHaveTextContent("PAUSE. CORRECT YOUR LAST STATEMENT.");
    expect(overlay).toHaveTextContent("Say this instead.");
    expect(overlay).toHaveTextContent("Helps keep skin hydrated for up to 24 hours in our in-house test.");
    expect(overlay).toHaveTextContent('"your wrinkles will disappear overnight"');
    expect(overlay).toHaveTextContent("Prevents, reduces or reverses physiological changes of ageing · Appendix III §3");
    expect(overlay).toHaveTextContent("Waiting for your correction");
    expect(overlay).toHaveTextContent("This screen clears when your correction is confirmed.");
    expect(screen.getByTestId("host-overlay-count")).toHaveTextContent("1 of 2");
    expect(screen.queryByTestId("host-unverified")).toBeNull();
    expect(acts.rendered).toHaveBeenCalledWith("al_000002");
  });

  it("unverified alert shows the AI check unavailable badge", () => {
    render(view({ alerts: [alert({ unverified: true })] }));
    expect(screen.getByTestId("host-unverified")).toHaveTextContent("AI check unavailable");
  });

  it("correction replaces the overlay with the green Corrected bar", () => {
    const a = alert();
    const { rerender } = render(view({ alerts: [a] }));
    expect(screen.getByTestId("host-compliance-overlay")).toBeInTheDocument();
    rerender(view({ alerts: [{ ...a, status: "corrected", resolved_at: now() }] }));
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    expect(screen.getByTestId("host-corrected")).toHaveTextContent("Corrected");
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

  it("MEDIUM: red banner in the prompter area, not full screen", () => {
    render(
      view({
        alerts: [alert({ rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM", span: "the best moisturiser in Singapore", say_instead: "It helps keep skin hydrated." })],
      }),
    );
    expect(screen.queryByTestId("host-compliance-overlay")).toBeNull();
    const banner = screen.getByTestId("host-medium-banner");
    expect(banner).toHaveTextContent("Avoid this claim");
    expect(banner).toHaveTextContent('"the best moisturiser in Singapore"');
    expect(banner).toHaveTextContent("Say: 'It helps keep skin hydrated.'");
    expect(banner).toHaveTextContent("Comparative or superlative claims");
  });
});

describe("audience questions", () => {
  it("orders host slots as given (pinned first) with tags and the suggested answer under 01", () => {
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
    expect(within(card).getByText("TOP 3")).toBeInTheDocument();
    const items = within(card).getAllByRole("article");
    expect(items.map((i) => i.getAttribute("data-testid"))).toEqual([
      "host-question-grp_000002",
      "host-question-grp_000001",
      "host-question-grp_000003",
    ]);
    expect(items[0]).toHaveTextContent("01");
    expect(items[0]).toHaveTextContent("From your PD");
    expect(items[0]).toHaveTextContent("SUGGESTED ANSWER");
    expect(items[0]).toHaveTextContent("Product sheet · Frequently asked questions");
    expect(items[1]).toHaveTextContent("3 asking");
    expect(items[1]).toHaveTextContent("For you");
    expect(items[1]).not.toHaveTextContent("SUGGESTED ANSWER");
    expect(items[2]).toHaveTextContent("AI answered");
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

  it("empty state", () => {
    render(view());
    expect(screen.getByText("You have the floor.")).toBeInTheDocument();
    expect(screen.getByText("Your next audience question will appear here.")).toBeInTheDocument();
    expect(screen.getByText("TOP 0")).toBeInTheDocument();
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
