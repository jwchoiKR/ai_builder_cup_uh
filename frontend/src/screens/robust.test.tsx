// D-350: a live screen must survive odd live data (null alert fields, an unknown alert kind, a product missing from
// the catalog after a switch, an empty prompter, an event type it does not know) without unmounting.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { reduceEvent, reduceSnapshot } from "../app/state";
import { PanelBoundary } from "../components";
import type { Alert, StateSnapshot } from "../app/types";
import { alert, catalog, segment, snapshot, T0 } from "../test/fixtures";
import { Host } from "./Host";
import { Operator } from "./Operator";
import { Viewer } from "./Viewer";

class FakeEventSource {
  static CLOSED = 2;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    setTimeout(() => this.onopen?.(), 0);
  }
  addEventListener() {}
  close() {}
}

const GONE = "product_not_in_catalog";
const now = () => Date.now();

function hostile(): StateSnapshot {
  const at = now() - 2000;
  const nulls = (over: Partial<Alert>) => alert({ created_at: at, shown_at: at, ...over });
  return snapshot({
    segments: [segment({ ended_at: at - 1000 }), segment({ segment_id: "seg_000002", product_id: GONE, order: 2,
      started_at: at - 1000, start_reason: "auto_speech", covered_point_ids: [] })],
    session: { ...snapshot().session!, status: "live", current_segment_id: "seg_000002" },
    alerts: [
      nulls({ alert_id: "al_n1", say_instead: null, span: null, rule_id: null, severity: null }),
      nulls({ alert_id: "al_n2", severity: "MEDIUM", say_instead: null, rule_id: "TEST-QUALIFIER", product_id: GONE }),
      nulls({ alert_id: "fx_n1", kind: "fact", rule_id: null, severity: null, field: null, stated_value: null,
        correct_value: null, say_instead: null, product_id: GONE }),
      nulls({ alert_id: "xx_n1", kind: "weird" as Alert["kind"], product_id: GONE }),
    ],
  });
}

let snap: StateSnapshot;

beforeEach(() => {
  snap = hostile();
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = url.split("?")[0];
    const out = path === "/api/catalog" ? catalog : path === "/api/health" ? { status: "ok" } :
      path.endsWith("/state") ? snap : { ok: true };
    return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("D-350: odd live data never blanks a screen", () => {
  it("the reducer ignores an event type it does not know", () => {
    const s = reduceSnapshot(snapshot(), "host", T0);
    expect(reduceEvent(s, { seq: 50, type: "something.new", payload: { x: 1 } } as never, T0).session).toEqual(s.session);
  });

  it("an event whose payload cannot be applied is skipped, and later events still apply", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const s = reduceSnapshot(snapshot(), "host", T0);
    const bad = reduceEvent(s, { seq: 51, type: "segment.extended", payload: {} }, T0);  // no segment in it
    expect(bad.lastSeq).toBe(51);
    expect(errors).toHaveBeenCalledWith("[live] event skipped", "segment.extended", expect.any(TypeError));
    const next = reduceEvent(bad, { seq: 52, type: "segment.switch_decided", payload: { switch: false } }, T0);
    expect(next.lastSeq).toBe(52);
    errors.mockRestore();
  });

  for (const [name, Screen] of [["host", Host], ["operator", Operator], ["viewer", Viewer]] as const) {
    it(`${name}: null alert fields, an unknown kind, a product missing after a switch`, async () => {
      const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
      render(<Screen sessionId="ses_robust" />);
      await new Promise((r) => setTimeout(r, 200));  // the state and catalog fetches resolve
      expect(screen.queryByTestId("panel-error")).toBeNull();
      expect(document.body.textContent?.length ?? 0).toBeGreaterThan(0);
      errors.mockRestore();
    });
  }
});

describe("D-350: a panel error stays in its panel", () => {
  it("shows a small card with a reload, keeps the other panels, and reports the error", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    let broken = true;
    function Boom() {
      if (broken) throw new Error("bad live data");
      return <p>panel back</p>;
    }
    render(
      <>
        <PanelBoundary name="host"><Boom /></PanelBoundary>
        <PanelBoundary name="operator"><p>operator alive</p></PanelBoundary>
      </>,
    );
    expect(screen.getByTestId("panel-error")).toHaveTextContent("This panel hit an error");
    expect(screen.getByText("operator alive")).toBeInTheDocument();
    expect(errors).toHaveBeenCalledWith("[panel-error]", "host", "bad live data",
      expect.objectContaining({ stack: expect.any(String), lastEventType: null }));
    broken = false;
    fireEvent.click(screen.getByRole("button", { name: "Reload panel" }));
    expect(screen.getByText("panel back")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-error")).toBeNull();
    errors.mockRestore();
  });
});


