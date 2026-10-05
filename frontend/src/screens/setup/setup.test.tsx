import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Product } from "../../app/types";
import type { BriefRecord, GlossaryState, SetupClient, UploadJob, UploadStage } from "./setupApi";
import { SetupView } from "./SetupView";

const cream = {
  product_id: "cream_hydra_barrier",
  code: "DL-CR-01",
  name: "Hydra Barrier Cream",
  prompter_points: [
    { point_id: "cr-p1", text: "Lightweight gel-cream. Absorbs quickly.", required: false },
    { point_id: "cr-p2", text: "Ceramide NP 1%, panthenol 5%, squalane 3%.", required: true },
  ],
} as unknown as Product;

const record: BriefRecord = {
  product_id: "cream_hydra_barrier",
  status: "ok",
  output: {
    product_id: "cream_hydra_barrier",
    glossary: [
      { term: "DAON LAB", kind: "brand", spoken_forms: ["day-on lab"], source_section: "Product overview" },
      { term: "Squalane", kind: "ingredient", spoken_forms: ["squa-lane"], source_section: "Key ingredients" },
    ],
    prompter_points: [
      { text: "5% panthenol, 3% squalane, and 1% ceramide NP.", required: true, source_section: "Key ingredients" },
      { text: "Airless pump tube.", required: false, source_section: "Key facts" },
    ],
    reason: "",
  },
  error: null,
  latency_ms: 1200,
  ran_at: Date.UTC(2026, 9, 1, 9, 0, 0),
};

const version0: GlossaryState = { version: 0, terms: [], confirmed_at: null, confirmed_products: [] };

const STAGES: [string, string][] = [
  ["receive", "Upload received"],
  ["check", "Check the file"],
  ["read", "Read the PDF text"],
  ["match", "Match the product code"],
  ["split", "Split into sheet passages"],
  ["index", "Rebuild the local index"],
  ["ready", "Ready for the Brief Agent"],
];

function job(status: UploadJob["status"], states: UploadStage["status"][], result: UploadJob["result"] = null, error: string | null = null): UploadJob {
  return {
    job_id: "up_1",
    name: "cream_v2.pdf",
    status,
    stages: STAGES.map(([stage_id, label], i) => ({
      stage_id,
      label,
      status: states[i] ?? "pending",
      detail: states[i] === "done" ? `${label} detail` : null,
      started_at: 0,
      ended_at: states[i] === "done" ? 100 : null,
    })),
    result,
    error,
    created_at: 0,
    updated_at: 0,
  };
}

const alreadyIndexed = job("done", ["done", "done", "skipped", "skipped", "skipped", "skipped", "skipped"], {
  status: "already_indexed",
  message: "Already indexed",
});

function client(over: Partial<SetupClient> = {}): SetupClient {
  return {
    documents: vi.fn().mockResolvedValue({
      documents: [
        { name: "DAON_LAB_Hydra_Barrier_Cream.pdf", product_id: "cream_hydra_barrier", pages: 3, sha256: "x", size: 1, source: "shipped", status: "Indexed locally" },
      ],
      doc_version: 0,
    }),
    upload: vi.fn().mockResolvedValue(alreadyIndexed),
    uploadJob: vi.fn().mockResolvedValue(alreadyIndexed),
    runBrief: vi.fn().mockResolvedValue(record),
    getBrief: vi.fn().mockResolvedValue(null),
    confirmAll: vi.fn().mockResolvedValue({ ...version0, version: 1, confirmed_products: ["cream_hydra_barrier"] }),
    glossary: vi.fn().mockResolvedValue(version0),
    market: vi.fn().mockResolvedValue({ market: "SG", name: "Singapore", regulator: "Health Sciences Authority (HSA)", lang: "en",
      lang_name: "English", stt_language: "en-US", tier: "live", offered: ["en"] }),
    ...over,
  } as SetupClient;
}

const renderView = (c: SetupClient) => render(<SetupView products={[cream]} brand="DAON LAB" client={c} theme="light" />);

describe("Setup page: back to the hub", () => {
  it("links to the hub with the session and offers the Settings gear", () => {
    render(<SetupView products={[cream]} brand="DAON LAB" client={client()} theme="light" sessionId="ses_9"
      themePref="system" onSetTheme={vi.fn()} />);
    expect(screen.getByTestId("hub-link")).toHaveAttribute("href", "/?session=ses_9");
    expect(screen.getByTestId("settings-button")).toBeInTheDocument();
  });
});

describe("Setup page", () => {
  it("lists the shipped documents as indexed locally", async () => {
    renderView(client());
    const table = await screen.findByTestId("setup-documents");
    expect(within(table).getByText("DAON_LAB_Hydra_Barrier_Cream.pdf")).toBeInTheDocument();
    expect(within(table).getByText("Indexed locally")).toBeInTheDocument();
    expect(screen.getByText("Default glossary (version 0)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm glossary" })).toBeDisabled();
  });

  it("runs the Brief Agent, then confirms the selected terms and point choices", async () => {
    const c = client();
    renderView(c);
    fireEvent.click(screen.getByRole("button", { name: "Run Brief Agent" }));
    await screen.findByTestId("setup-glossary-cream_hydra_barrier");
    expect(c.runBrief).toHaveBeenCalledWith("cream_hydra_barrier");

    fireEvent.click(screen.getByLabelText("Include Squalane"));
    fireEvent.change(screen.getByLabelText("Use draft 1"), { target: { value: "replace:cr-p2" } });
    fireEvent.change(screen.getByLabelText("Use draft 2"), { target: { value: "add" } });
    expect(screen.getAllByText("Use as text for cr-p2", { selector: "option" })).toHaveLength(2);
    expect(screen.getAllByText("Add as new optional point", { selector: "option" })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Confirm glossary" }));
    expect(await screen.findByTestId("setup-confirmed")).toHaveTextContent("Confirmed · version 1");
    expect(c.confirmAll).toHaveBeenCalledWith({
      cream_hydra_barrier: {
        glossary: [
          { ...record.output!.glossary[0], include: true },
          { ...record.output!.glossary[1], include: false },
        ],
        prompter_points: [
          { text: "5% panthenol, 3% squalane, and 1% ceramide NP.", action: "replace", point_id: "cr-p2", source_section: "Key ingredients" },
          { text: "Airless pump tube.", action: "add", source_section: "Key facts" },
        ],
      },
    });
  });

  it("shows a Brief Agent error and keeps the previous result", async () => {
    const c = client({
      getBrief: vi.fn().mockResolvedValue(record),
      runBrief: vi.fn().mockRejectedValue(new Error("Brief Agent timeout: deadline 60000 ms")),
    });
    renderView(c);
    await screen.findByTestId("setup-glossary-cream_hydra_barrier");
    fireEvent.click(screen.getByRole("button", { name: "Run Brief Agent" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Brief Agent timeout");
    expect(screen.getByTestId("setup-glossary-cream_hydra_barrier")).toBeInTheDocument();
  });

  it("reports an already indexed upload", async () => {
    const c = client();
    renderView(c);
    await screen.findByTestId("setup-documents");
    const file = new File(["%PDF-1.4"], "same.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("setup-file-input"), { target: { files: [file] } });
    await waitFor(() => expect(c.upload).toHaveBeenCalledWith(file, "same.pdf"));
    expect(await screen.findByRole("status")).toHaveTextContent("Already indexed");
  });

  it("shows each upload stage as the backend reports it (D-093)", async () => {
    const indexed = { status: "indexed" as const, message: "Indexed locally · 38 passages" };
    const c = client({
      upload: vi.fn().mockResolvedValue(job("running", ["done", "running"])),
      uploadJob: vi
        .fn()
        .mockResolvedValueOnce(job("running", ["done", "done", "done", "running"]))
        .mockResolvedValueOnce(job("done", ["done", "done", "done", "done", "done", "done", "done"], indexed)),
    });
    renderView(c);
    await screen.findByTestId("setup-documents");
    const file = new File(["%PDF-1.4"], "cream_v2.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("setup-file-input"), { target: { files: [file] } });
    const progress = await screen.findByTestId("setup-upload-progress");
    expect(within(progress).getByText("Check the file")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("setup-stage-match")).toHaveAttribute("data-state", "running"));
    await waitFor(() => expect(progress).toHaveAttribute("data-status", "done"), { timeout: 3000 });
    expect(screen.getByTestId("setup-stage-index")).toHaveAttribute("data-state", "done");
    expect(within(progress).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("Indexed locally · 38 passages")).toBeInTheDocument();
  });

  it("marks the failing upload stage and shows the error", async () => {
    const failed = job("failed", ["done", "failed"], null, "Upload a PDF product sheet.");
    const c = client({ upload: vi.fn().mockResolvedValue(failed) });
    renderView(c);
    await screen.findByTestId("setup-documents");
    fireEvent.change(screen.getByTestId("setup-file-input"), { target: { files: [new File(["x"], "x.pdf")] } });
    expect(await screen.findByText("Upload a PDF product sheet.")).toBeInTheDocument();
    expect(screen.getByTestId("setup-stage-check")).toHaveAttribute("data-state", "failed");
  });

  it("edits and adds glossary terms before confirming (D-094)", async () => {
    const c = client({ getBrief: vi.fn().mockResolvedValue(record) });
    renderView(c);
    await screen.findByTestId("setup-glossary-cream_hydra_barrier");
    fireEvent.click(screen.getByRole("button", { name: "Edit Squalane" }));
    fireEvent.change(screen.getByLabelText("Spoken forms"), { target: { value: "squa-lane, squalene,  squa-lane " } });
    fireEvent.click(screen.getByRole("button", { name: "Save term" }));
    expect(screen.getByText("Edited")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));
    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "daon lab" } });
    fireEvent.click(screen.getByRole("button", { name: "Save term" }));
    expect(screen.getByRole("alert")).toHaveTextContent('"daon lab" is already in the list.');
    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "Hydra Barrier" } });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "product" } });
    fireEvent.change(screen.getByLabelText("Spoken forms"), { target: { value: "hydra barrier" } });
    fireEvent.click(screen.getByRole("button", { name: "Save term" }));
    expect(screen.getByText("Added")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm glossary" }));
    await screen.findByTestId("setup-confirmed");
    const sent = (c.confirmAll as ReturnType<typeof vi.fn>).mock.calls[0][0].cream_hydra_barrier.glossary;
    expect(sent).toEqual([
      { ...record.output!.glossary[0], include: true },
      { term: "Squalane", kind: "ingredient", spoken_forms: ["squa-lane", "squalene"], source_section: "Key ingredients", include: true },
      { term: "Hydra Barrier", kind: "product", spoken_forms: ["hydra barrier"], source_section: "Added on /setup", include: true },
    ]);
  });

  it("starts from the confirmed terms when they are newer than the Brief Agent run", async () => {
    const confirmed: GlossaryState = {
      ...version0,
      version: 2,
      confirmed_at: record.ran_at + 60_000,
      confirmed_products: ["cream_hydra_barrier"],
      terms_by_product: {
        cream_hydra_barrier: [{ term: "Squalane", kind: "ingredient", spoken_forms: ["squalene"], source_section: "Key ingredients" }],
      },
    };
    renderView(client({ getBrief: vi.fn().mockResolvedValue(record), glossary: vi.fn().mockResolvedValue(confirmed) }));
    const table = await screen.findByTestId("setup-glossary-cream_hydra_barrier");
    await waitFor(() => expect(within(table).getByText("squalene")).toBeInTheDocument());
    expect(within(table).queryByText("DAON LAB")).toBeNull();
  });
});

describe("market and language (D-142)", () => {
  it("shows the market and broadcast language of new sessions, read-only", async () => {
    renderView(client());
    expect(await screen.findByTestId("setup-market")).toHaveTextContent("Singapore · English");
  });
});
