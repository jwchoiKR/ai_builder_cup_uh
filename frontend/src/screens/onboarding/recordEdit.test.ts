import { describe, expect, it } from "vitest";

import type { ProductRecord } from "./onboardingApi";
import { conflictValue, newestIndex, plainField, setAt } from "./recordEdit";

const rec = {
  variants: [{ variant_id: "A-30", name: "Night Serum 30 ml", size_value: "30", size_unit: "ml", market: "SG", evidence: [],
    prices: [{ currency: "SGD", minor: 5800, kind: "list", market: "SG", evidence: [] },
      { currency: "SGD", minor: 4600, kind: "live", market: "SG", evidence: [] }] }],
} as unknown as ProductRecord;

describe("recordEdit (D-231)", () => {
  it("names record paths in plain words", () => {
    expect(plainField(rec, "variants[0].prices[1].minor")).toBe("Night Serum 30 ml · live price SG");
    expect(plainField(rec, "variants[A-30].size_value")).toBe("Night Serum 30 ml · size");
    expect(plainField(rec, "short_names")).toBe("Short names viewers use");
    expect(plainField(rec, "30 ml SG live price")).toBe("30 ml SG live price");
  });
  it("applies a chosen value by path, money as minor units", () => {
    expect(setAt(rec, "variants[0].prices[1].minor", "S$44.00")!.variants[0].prices[1].minor).toBe(4400);
    expect(setAt(rec, "variants[0].prices[1].minor", "4400")!.variants[0].prices[1].minor).toBe(4400);
    expect(setAt(rec, "variants[0].size_value", "50")!.variants[0].size_value).toBe("50");
    expect(setAt(rec, "30 ml SG live price", "S$44.00")).toBeNull();
    expect(rec.variants[0].prices[1].minor).toBe(4600); // never mutated
  });
  it("shows a money conflict as an amount", () => {
    expect(conflictValue(rec, "variants[0].prices[1].minor", "4600")).toBe("SGD 46.00");
    expect(conflictValue(rec, "variants[0].prices[1].minor", "S$46.00")).toBe("S$46.00");
  });
  it("preselects the newest dated value", () => {
    expect(newestIndex(["2026-09-01", "2026-10-01"])).toBe(1);
    expect(newestIndex([null, null])).toBe(0);
  });
});
