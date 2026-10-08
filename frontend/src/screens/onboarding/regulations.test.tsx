// D-359: the Regulations panel: each job status, approval (write-once), the active pack, and the no-match warning.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LawJob, Regulations } from "./onboardingApi";

const regs = (): Regulations => ({
  market: "SG", markets: ["MY", "SG"], categories: ["food_supplement", "kitchen_appliance"],
  market_law: { name: "Cosmetics", covers: ["cosmetic", "skincare"], files: ["guideline.pdf"] },
  packs: [
    { pack_id: "law_sg_a_v2", market: "SG", name: "Kelmar supplement code", regulator: "Kelmar authority",
      covers: ["food_supplement"], approved_at: Date.UTC(2026, 9, 8), job_id: "law_2", files: ["kelmar_code.pdf"],
      sections: ["kelmar_code.pdf · section 2.1"], active_for: ["food_supplement"] },
    { pack_id: "law_sg_a_v1", market: "SG", name: "Kelmar supplement code", regulator: "Kelmar authority",
      covers: ["food_supplement"], approved_at: Date.UTC(2026, 9, 1), job_id: "law_1", files: ["old_code.pdf"],
      sections: [], active_for: [] },
  ],
  releases: [
    { release_id: "rel_caps_v1", product_name: "Joint Caps", category: "food_supplement",
      originals: [{ name: "kelmar_code.pdf", source_id: "law_sg_a_v2", kind: "law" }], missing: [], warning: false },
    { release_id: "rel_kettle_v1", product_name: "Quick Kettle", category: "kitchen_appliance", originals: [],
      missing: [], warning: true },
  ],
});
const job = (status: LawJob["status"], extra: Partial<LawJob> = {}): LawJob => ({
  job_id: "law_9", status, files: ["kelmar_code.pdf"], error: null, result: null, ...extra });
const done = job("done", { result: { record: { name: "Kelmar supplement code", regulator: "Kelmar authority",
  covers: ["food_supplement"], rules: [{ evidence: [{ file: "kelmar_code.pdf", locator: "section 2.1", quote: "q" }] }] } } });

const api = vi.hoisted(() => ({ list: vi.fn(), upload: vi.fn(), job: vi.fn(), approve: vi.fn() }));
vi.mock("./onboardingApi", () => ({ regulationsApi: api }));

import { RegulationsPanel } from "./RegulationsPanel";

beforeEach(() => {
  api.list.mockReset().mockResolvedValue(regs());
  api.upload.mockReset().mockResolvedValue({ job_id: "law_9" });
  api.job.mockReset();
  api.approve.mockReset().mockResolvedValue({ pack_id: "law_sg_a_v3" });
});

async function startRead() {
  render(<RegulationsPanel />);
  await screen.findByTestId("reg-packs");
  fireEvent.change(screen.getByTestId("reg-files"), { target: { files: [new File(["x"], "kelmar_code.pdf")] } });
  fireEvent.click(screen.getByTestId("reg-read"));
  return screen.findByTestId("reg-job");
}

describe("RegulationsPanel (D-359)", () => {
  it("market and category come from pick-lists; the category list is the approved products' categories", async () => {
    render(<RegulationsPanel />);
    await screen.findByTestId("reg-packs");
    const cats = within(screen.getByTestId("reg-category")).getAllByRole("option").map((o) => o.textContent);
    expect(cats).toEqual(["food_supplement", "kitchen_appliance"]);
    expect((screen.getByTestId("reg-market") as HTMLSelectElement).value).toBe("SG");
    expect(screen.getByText(/lost if the server restarts/)).toBeInTheDocument();
  });

  it.each([
    ["queued", "Queued"],
    ["reading", "Reading the documents"],
    ["failed", "Failed: RuntimeError: bad file"],
  ] as const)("shows the %s status", async (status, text) => {
    api.job.mockResolvedValue(job(status, status === "failed" ? { error: "RuntimeError: bad file" } : {}));
    const box = await startRead();
    expect(api.upload).toHaveBeenCalledWith(expect.any(Array), "SG", "food_supplement");
    if (status !== "queued") await waitFor(() => expect(box).toHaveAttribute("data-status", status), { timeout: 3000 });
    expect(screen.getByTestId("reg-status")).toHaveTextContent(text);
  });

  it("a finished read shows its source files and sections, and approves once with the write-once note", async () => {
    api.job.mockResolvedValue(done);
    await startRead();
    await waitFor(() => expect(screen.getByTestId("reg-job")).toHaveAttribute("data-status", "done"), { timeout: 3000 });
    expect(screen.getByTestId("reg-job-sections")).toHaveTextContent("kelmar_code.pdf · section 2.1");
    expect(screen.getByText(/write-once/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("reg-approve"));
    expect(await screen.findByTestId("reg-approved")).toHaveTextContent("law_sg_a_v3");
    expect(api.approve).toHaveBeenCalledWith("law_9");
    expect(screen.getByTestId("reg-approve")).toBeDisabled();
    expect(api.list).toHaveBeenCalledTimes(2);  // the list reloads after approval
  });

  it("accepts PDF files only (D-367)", async () => {
    render(<RegulationsPanel />);
    await screen.findByTestId("reg-packs");
    expect(screen.getByTestId("reg-files")).toHaveAttribute("accept", ".pdf,application/pdf");
    fireEvent.change(screen.getByTestId("reg-files"), {
      target: { files: [new File(["x"], "code.pdf"), new File(["x"], "page.html"), new File(["x"], "notes.docx")] } });
    expect(screen.getByText("PDF files only. Not a PDF: page.html, notes.docx")).toBeInTheDocument();
    expect(screen.getByTestId("reg-read")).toBeDisabled();
    fireEvent.change(screen.getByTestId("reg-files"), { target: { files: [new File(["x"], "Code.PDF")] } });
    expect(screen.queryByText(/PDF files only/)).toBeNull();
    expect(screen.getByTestId("reg-read")).toBeEnabled();
  });

  it("marks the active pack, a replaced one, and warns for a product no regulation matches", async () => {
    render(<RegulationsPanel />);
    await screen.findByTestId("reg-packs");
    expect(screen.getByTestId("reg-pack-law_sg_a_v2")).toHaveTextContent("Active for food_supplement");
    expect(screen.getByTestId("reg-pack-law_sg_a_v1")).toHaveTextContent("Replaced by a newer pack");
    expect(screen.getByTestId("reg-release-rel_caps_v1")).toHaveTextContent("kelmar_code.pdf");
    expect(screen.queryByTestId("reg-warning-rel_caps_v1")).toBeNull();
    expect(screen.getByTestId("reg-warning-rel_kettle_v1")).toHaveTextContent("No regulation matches");
  });
});
