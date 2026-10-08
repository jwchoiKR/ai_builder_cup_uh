import { describe, expect, it } from "vitest";

import { translate } from "../app/i18n";
import { ownDocFirst } from "../app/selectors";
import type { Catalog } from "../app/types";
import { pointsStatus } from "./host/Prompter";
import { impactChips } from "./operator/Header";

const t = (en: string, vars?: Record<string, string | number>) => translate("en", en, vars);

describe("D-332: UI QA", () => {
  it("says nothing about required points when a product has none", () => {
    expect(pointsStatus(t, 0, null, 0)).toBe("");
    expect(pointsStatus(t, 0, { elapsedMs: 0, plannedMs: 60_000 }, 0)).toBe("1:00");
    expect(pointsStatus(t, 0, null, 3)).toBe("All required points said");
  });

  it("hides the token chip until there is a number", () => {
    const impact = (tokens: number | null) => ({ impact: {
      risky_lines: { alerted: 1, of_lines: 2 }, questions: { ai: 0, host: 0, operator: 0, of_askers: 0 },
      operator_actions: 0, llm: { calls: 0, tokens: 0, tokens_per_hour: tokens } } });
    expect(impactChips(impact(null) as never).some((x) => x.includes("tokens/h"))).toBe(false);
    expect(impactChips(impact(12_000) as never)).toContain("LLM 12k tokens/h");
    // D-348: the denominator is every line, so the chip says so (no "risky lines" reading of "missed 1 of 2")
    expect(impactChips(impact(null) as never)[0]).toBe("Lines with alerts 1 / 2 lines");
  });

  it("D-348: a rule source naming two products' files lists the alert product's file first", () => {
    const passage = (pid: string, doc: string) => ({ product_id: pid, doc, section: "s", text: "x" });
    const catalog = { passages: { a: passage("cream", "Velmora_Cream.pdf"), b: passage("serum", "Velmora_Serum.pdf") } } as unknown as Catalog;
    const ref = "Velmora_Cream.pdf Page 2 §7; Velmora_Serum.pdf Page 2";
    expect(ownDocFirst(catalog, ref, "serum")).toBe("Velmora_Serum.pdf Page 2; Velmora_Cream.pdf Page 2 §7");
    expect(ownDocFirst(catalog, ref, "cream")).toBe(ref);
    expect(ownDocFirst(catalog, "Appendix III, Section 3", "serum")).toBe("Appendix III, Section 3");
  });
});
