import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Job, ProductRecord } from "./onboardingApi";

const ev = [{ file: "spec.docx", locator: "paragraph 3", quote: "Patch test before first use." }];
const record: ProductRecord = {
  brand: "Lumen & Co.", product_name: "Night Serum", category: "cosmetic", category_evidence: ev, language: "en",
  generic_word: "serum", short_names: [],
  variants: [{ variant_id: "LMN-30", name: "Night Serum 30 ml", size_value: "30", size_unit: "ml", market: "SG",
    prices: [{ currency: "SGD", minor: 4400, kind: "live", market: "SG", evidence: ev }], evidence: ev }],
  offers: [], ingredients: [], ingredient_list_complete: false, approved_claims: [], not_approved_claims: [],
  avoid_saying: [], qualified_results: [], cautions: [{ text: "Patch test before first use.", evidence: ev }],
  how_to_use: [], key_facts: [], missing: ["origin"],
  conflicts: [{ field: "live price", values: ["S$46.00", "S$44.00"], effective_dates: ["2026-09-01", "2026-10-01"],
    note: "", evidence: ev }],
};
const done: Job = { job_id: "onb_1", status: "done", files: ["spec.docx"], error: null,
  result: { record, method: "gemini_whole", models: {}, seconds: 61, notes: [], files: [] } };

vi.mock("./onboardingApi", () => ({
  onboardingApi: {
    upload: vi.fn(async () => ({ job_id: "onb_1" })),
    job: vi.fn(async () => done),
    approve: vi.fn(async () => ({ release_id: "rel_lumen_v1", warnings: [] })),
    startShow: vi.fn(),
  },
}));

import { OnboardingView } from "./OnboardingView";

describe("OnboardingView (D-224)", () => {
  it("reads, shows every field with its evidence and conflicts, and approves a release", async () => {
    render(<OnboardingView />);
    const input = screen.getByTestId("onb-files") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "spec.docx")] } });
    fireEvent.click(screen.getByTestId("onb-read"));
    expect(await screen.findByTestId("onb-summary", {}, { timeout: 4000 })).toHaveTextContent("Night Serum");
    expect(screen.getByTestId("onb-conflicts")).toHaveTextContent("S$46.00 (2026-09-01) vs S$44.00 (2026-10-01)");
    expect(screen.getByTestId("onb-cautions")).toHaveTextContent("spec.docx · paragraph 3");
    expect(screen.getByTestId("onb-variants-and-prices")).toHaveTextContent("live price SGD 44.00");
    fireEvent.click(screen.getByTestId("onb-approve"));
    await waitFor(() => expect(screen.getByTestId("onb-release")).toHaveTextContent("rel_lumen_v1"));
  });
});
