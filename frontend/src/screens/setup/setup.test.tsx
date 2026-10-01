import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Product } from "../../app/types";
import type { BriefRecord, GlossaryState, SetupClient } from "./setupApi";
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

function client(over: Partial<SetupClient> = {}): SetupClient {
  return {
    documents: vi.fn().mockResolvedValue({
      documents: [
        { name: "DAON_LAB_Hydra_Barrier_Cream.pdf", product_id: "cream_hydra_barrier", pages: 3, sha256: "x", size: 1, source: "shipped", status: "Indexed locally" },
      ],
      doc_version: 0,
    }),
    upload: vi.fn().mockResolvedValue({ status: "already_indexed", message: "Already indexed" }),
    runBrief: vi.fn().mockResolvedValue(record),
    getBrief: vi.fn().mockResolvedValue(null),
    confirmAll: vi.fn().mockResolvedValue({ ...version0, version: 1, confirmed_products: ["cream_hydra_barrier"] }),
    glossary: vi.fn().mockResolvedValue(version0),
    ...over,
  } as SetupClient;
}

const renderView = (c: SetupClient) => render(<SetupView products={[cream]} brand="DAON LAB" client={c} theme="light" />);

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
});
