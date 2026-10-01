import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionLabel } from "./ui";
import { VirtualList, windowRange } from "./VirtualList";

describe("ConnectionLabel", () => {
  it("shows the exact copy for both states", () => {
    const { rerender } = render(<ConnectionLabel status="connected" />);
    expect(screen.getByText("Connected")).toBeInTheDocument();
    rerender(<ConnectionLabel status="reconnecting" />);
    expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
  });
});

describe("windowing", () => {
  it("computes the visible range with overscan", () => {
    expect(windowRange(0, 0, 500, 50)).toEqual([0, 0]);
    expect(windowRange(1000, 0, 500, 50, 5)).toEqual([0, 15]);
    expect(windowRange(1000, 5000, 500, 50, 5)).toEqual([95, 115]);
    expect(windowRange(10, 5000, 500, 50, 5)).toEqual([10, 10]);
  });

  it("renders every row up to the threshold and windows beyond it", () => {
    const few = Array.from({ length: 20 }, (_, i) => i);
    const { unmount } = render(<VirtualList items={few} getKey={(i) => String(i)} renderItem={(i) => <span>row {i}</span>} />);
    expect(screen.getAllByText(/^row /)).toHaveLength(20);
    unmount();
    const many = Array.from({ length: 1000 }, (_, i) => i);
    render(<VirtualList items={many} rowHeight={50} getKey={(i) => String(i)} renderItem={(i) => <span>row {i}</span>} />);
    expect(screen.getAllByText(/^row /).length).toBeLessThan(100);
  });
});
