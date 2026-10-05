import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { reduceEvent, reduceSnapshot, type ClientState } from "../../app/state";
import type { SessionEvent } from "../../app/types";
import { CREAM, T0, catalog, comment, message, segment, session, snapshot } from "../../test/fixtures";
import { Viewer } from "../Viewer";
import { viewerChat } from "./chat";
import { POPUP_MS, ViewerView } from "./ViewerView";

const NOW = T0 + 10_000;

function stateWith(over: Parameters<typeof snapshot>[0] = {}): ClientState {
  return reduceSnapshot(snapshot(over), "viewer", NOW);
}

function apply(state: ClientState, ...events: SessionEvent[]): ClientState {
  return events.reduce((s, ev) => reduceEvent(s, ev, NOW), state);
}

function view(state: ClientState, extra: Partial<Parameters<typeof ViewerView>[0]> = {}) {
  return <ViewerView state={state} catalog={catalog} connection="connected" theme="light" inputEnabled={false} {...extra} />;
}

describe("page chrome", () => {
  it("the standalone viewer has the hub link and the Settings gear outside the phone; embedded it has neither", () => {
    const { unmount } = render(view(stateWith(), { onSetTheme: vi.fn(), themePref: "system" }));
    const phone = screen.getByTestId("viewer-phone");
    expect(screen.getByTestId("hub-link")).toHaveAttribute("href", "/?session=ses_000001");
    expect(phone.contains(screen.getByTestId("hub-link"))).toBe(false);
    expect(phone.contains(screen.getByTestId("settings-button"))).toBe(false);
    unmount();
    render(view(stateWith(), { embedded: true }));
    expect(screen.queryByTestId("hub-link")).toBeNull();
  });
});

const raj = comment({ comment_id: "cm_1", author_id: "u_raj", author_name: "Raj", text: "Is it OK for oily skin?", received_at: T0 + 1000 });
const priya = comment({ comment_id: "cm_2", author_id: "u_priya", author_name: "Priya", text: "oily skin here, ok?", received_at: T0 + 2000 });
const lee = comment({ comment_id: "cm_3", author_id: "u_lee", author_name: "Lee", text: "How much is the cream?", received_at: T0 + 2500, group_id: "grp_2" });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Viewer chat", () => {
  it("renders a coalesced reply once under the first asker; later askers show 'Also answered: @Name'", () => {
    const state = stateWith({
      comments: [raj, priya, lee],
      messages: [
        message({ message_id: "msg_1", kind: "host_answer", text: "Yes, use a smaller amount on oily areas.",
                  reply_to_comment_ids: ["cm_1", "cm_2"], reply_to_author_names: ["Raj", "Priya"], published_at: T0 + 4000 }),
        message({ message_id: "msg_2", kind: "ai_answer", text: "It is S$36.00 during this live.", group_id: "grp_2",
                  reply_to_comment_ids: ["cm_3"], reply_to_author_names: ["Lee"], published_at: T0 + 5000,
                  citations: [{ passage_id: "DL-CR-01#key-facts#live-broadcast-price", quote: "Live broadcast price: S$36.00", section: "Key facts" }] }),
      ],
    });
    render(view(state));
    const first = screen.getByTestId("viewer-comment-cm_1");
    const reply = within(first).getByTestId("viewer-reply-msg_1");
    expect(reply).toHaveAttribute("data-kind", "host_answer");
    expect(within(reply).getByText("Host answer")).toBeInTheDocument();
    expect(within(screen.getByTestId("viewer-comment-cm_2")).getByTestId("viewer-also-answered-cm_2")).toHaveTextContent(
      "↳ Also answered: @Priya",
    );
    expect(within(screen.getByTestId("viewer-comment-cm_2")).queryByTestId("viewer-reply-msg_1")).toBeNull();
    expect(within(first).queryByText(/Also answered/)).toBeNull();
    const ai = within(screen.getByTestId("viewer-comment-cm_3")).getByTestId("viewer-reply-msg_2");
    expect(ai).toHaveAttribute("data-kind", "ai_answer");
    expect(within(ai).getByText("AI answer")).toBeInTheDocument();
    fireEvent.click(within(ai).getByText("Source: product sheet"));  // D-122: expands inline
    expect(within(ai).getByTestId("viewer-source-details")).toHaveTextContent("Live broadcast price: S$36.00");
  });

  it("an AI answer citing the active promotion says 'Source: active promotion' (item 5)", () => {
    const state = stateWith({
      comments: [lee],
      messages: [
        message({ message_id: "msg_p", kind: "ai_answer", text: "With the time sale it's S$32.40 right now.", group_id: "grp_2",
                  reply_to_comment_ids: ["cm_3"], reply_to_author_names: ["Lee"], published_at: T0 + 5000,
                  citations: [{ passage_id: "PROMO#promo_time_sale_10", quote: "Hydra Barrier Cream S$32.40", section: "Active promotion" }] }),
      ],
    });
    render(view(state));
    const reply = screen.getByTestId("viewer-reply-msg_p");
    expect(within(reply).getAllByTestId("viewer-source").map((b) => b.textContent)).toEqual(["Source: active promotion"]);
    expect(within(reply).queryByText("Source: product sheet")).toBeNull();
    fireEvent.click(within(reply).getByText("Source: active promotion"));
    expect(within(reply).getByTestId("viewer-source-details")).toHaveTextContent("Hydra Barrier Cream S$32.40");
  });

  it("an AI answer citing a sheet passage and the promotion shows both sources (item 5)", () => {
    const state = stateWith({
      comments: [lee],
      messages: [
        message({ message_id: "msg_b", kind: "ai_answer", text: "S$32.40 now; the set is S$55.80.", group_id: "grp_2",
                  reply_to_comment_ids: ["cm_3"], reply_to_author_names: ["Lee"], published_at: T0 + 5000,
                  citations: [
                    { passage_id: "PROMO#promo_time_sale_10", quote: "Hydra Barrier Cream S$32.40", section: "Active promotion" },
                    { passage_id: "DL-CR-01#key-facts#live-set-price", quote: "Live set price: S$62.00", section: "Key facts" },
                  ] }),
      ],
    });
    render(view(state));
    const labels = within(screen.getByTestId("viewer-reply-msg_b")).getAllByTestId("viewer-source").map((b) => b.textContent);
    expect(labels).toEqual(["Source: product sheet", "Source: active promotion"]);
  });

  it("labels brand answers DAON LAB", () => {
    const state = stateWith({
      comments: [raj],
      messages: [message({ message_id: "msg_9", kind: "brand_answer", text: "Please check with your doctor.", reply_to_comment_ids: ["cm_1"] })],
    });
    render(view(state));
    const reply = screen.getByTestId("viewer-reply-msg_9");
    expect(reply).toHaveAttribute("data-kind", "brand_answer");
    expect(within(reply).getByText("DAON LAB")).toBeInTheDocument();
  });

  it("removes a comment that is hidden after display", () => {
    let state = stateWith({ comments: [raj, priya] });
    const { rerender } = render(view(state));
    expect(screen.getByTestId("viewer-comment-cm_2")).toBeInTheDocument();
    // host/viewer streams carry a redacted payload for hidden comments
    state = apply(state, { seq: 11, type: "comment.hidden", payload: { comment_id: "cm_2", visibility: "hidden" } });
    rerender(view(state));
    expect(screen.queryByTestId("viewer-comment-cm_2")).toBeNull();
    expect(screen.getByTestId("viewer-comment-cm_1")).toBeInTheDocument();
  });

  it("keeps a correction notice pinned for 60 s with the label 'Correction'", () => {
    const notice = message({ message_id: "msg_n", kind: "correction_notice", text: "Correction: the current price of Hydra Barrier Cream is S$36.00.",
                             group_id: null, reply_to_comment_ids: [], reply_to_author_names: [], published_at: NOW - 1000 });
    const { rerender } = render(view(stateWith({ messages: [notice] })));
    const pinned = screen.getByTestId("viewer-correction-notice");
    expect(pinned).toHaveTextContent("Correction");
    expect(pinned).toHaveTextContent("S$36.00");
    act(() => {
      vi.setSystemTime(NOW + 61_000);
      vi.advanceTimersByTime(1000);
    });
    rerender(view(stateWith({ messages: [notice] })));
    expect(screen.queryByTestId("viewer-correction-notice")).toBeNull();
    expect(viewerChat(stateWith({ messages: [notice] }), NOW + 61_000)).toHaveLength(1); // now in the chat
  });

  it("shows the pinned notice", () => {
    render(view(stateWith({ session: session({ pinned_notice: "Free pouch over S$60" }) })));
    expect(screen.getByTestId("viewer-pinned-notice")).toHaveTextContent("Free pouch over S$60");
  });
});

describe("Viewer product strip and time sale", () => {
  const promoStarted: SessionEvent = {
    seq: 20,
    type: "promo.started",
    payload: { promo_id: "promo_time_sale_10", started_at: NOW, ends_at: NOW + 600_000, changes_prices: true },
  };

  it("shows live price and set price, then promo prices during the time sale", () => {
    let state = stateWith();
    const { rerender } = render(view(state));
    expect(screen.getByTestId("viewer-price")).toHaveTextContent("S$36.00");
    expect(screen.getByTestId("viewer-set-price")).toHaveTextContent("Set S$62.00");
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    state = apply(state, promoStarted);
    rerender(view(state));
    expect(screen.getByTestId("viewer-price")).toHaveTextContent("S$32.40");
    expect(screen.getByTestId("viewer-set-price")).toHaveTextContent("Set S$55.80");
  });

  it("pops up the time sale card for 4 s, then keeps the chip", () => {
    let state = stateWith();
    const { rerender } = render(view(state));
    expect(screen.queryByTestId("viewer-timesale-popup")).toBeNull();
    state = apply(state, promoStarted);
    rerender(view(state));
    const popup = screen.getByTestId("viewer-timesale-popup");
    expect(popup).toHaveTextContent("TIME SALE");
    expect(popup).toHaveTextContent("10:00");
    act(() => {
      vi.advanceTimersByTime(POPUP_MS - 100);
    });
    expect(screen.getByTestId("viewer-timesale-popup")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByTestId("viewer-timesale-popup")).toBeNull();
    expect(screen.getByTestId("viewer-timesale-chip")).toHaveTextContent(/TIME SALE\s*09:5\d/);
  });

  it("does not pop up for a promo that was already running when the page opened", () => {
    const state = apply(stateWith(), promoStarted);
    render(view(state));
    expect(screen.queryByTestId("viewer-timesale-popup")).toBeNull();
    expect(screen.getByTestId("viewer-timesale-chip")).toBeInTheDocument();
  });

  it("shows the product placeholder and no LIVE badge before the start", () => {
    render(view(stateWith({ session: session({ status: "ready", started_at: null, current_segment_id: null }), segments: [] })));
    const video = screen.getByTestId("viewer-video");
    expect(within(video).getByText("Sample product preview")).toBeInTheDocument();
    expect(within(video).getByText("Hydra Barrier Cream")).toBeInTheDocument();
    expect(within(video).getByText("DAON LAB")).toBeInTheDocument();
    expect(screen.queryByText("LIVE")).toBeNull();
  });
});

describe("Viewer input", () => {
  it("is read-only when viewer input is disabled", () => {
    render(view(stateWith()));
    const input = screen.getByTestId("viewer-input");
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute("placeholder", "Chat is read-only in this demo");
  });

  it("asks for a display name once, then sends comments", async () => {
    vi.useRealTimers();
    window.localStorage.clear();
    const onSend = vi.fn(async () => ({}));
    render(view(stateWith(), { inputEnabled: true, onSend }));
    const input = screen.getByTestId("viewer-input");
    expect(input).toHaveAttribute("placeholder", "Your display name");
    fireEvent.change(input, { target: { value: "Mina" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(screen.getByTestId("viewer-input")).toHaveAttribute("placeholder", "Chat as Mina"));
    expect(window.localStorage.getItem("ls.viewer.name")).toBe("Mina");
    const id = window.localStorage.getItem("ls.viewer.id");
    fireEvent.change(screen.getByTestId("viewer-input"), { target: { value: "is it sticky?" } });
    fireEvent.submit(screen.getByTestId("viewer-input").closest("form")!);
    await waitFor(() => expect(onSend).toHaveBeenCalledWith({ authorId: id, name: "Mina" }, "is it sticky?"));
  });
});

// ---- wired: store + SSE ------------------------------------------------------------------------

class FakeEventSource {
  static CLOSED = 2;
  static last: FakeEventSource | null = null;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (e: MessageEvent) => void>();
  constructor(public url: string) {
    FakeEventSource.last = this;
    setTimeout(() => this.onopen?.(), 0);
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners.set(type, fn);
  }
  emit(type: string, seq: number, payload: unknown) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(payload), lastEventId: String(seq) }));
  }
  close() {}
}

describe("Viewer wired to the session store", () => {
  it("loads /state as the viewer role and applies SSE events", async () => {
    vi.useRealTimers();
    const urls: string[] = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(url);
        const path = url.split("?")[0];
        const body = path.endsWith("/state")
          ? snapshot({ last_seq: 3, server_time: Date.now(), comments: [raj, priya], segments: [segment({ product_id: CREAM })] })
          : path === "/api/catalog"
            ? catalog
            : path === "/api/health"
              ? { status: "ok", viewer_input_enabled: false, demo_tools_enabled: true }
              : {};
        return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
      }),
    );
    render(<Viewer sessionId="ses_viewer_wired" embedded />);
    expect(await screen.findByTestId("viewer-comment-cm_2")).toBeInTheDocument();
    expect(urls.some((u) => u.includes("/sessions/ses_viewer_wired/state?role=viewer"))).toBe(true);
    expect(FakeEventSource.last?.url).toContain("role=viewer");
    act(() => FakeEventSource.last!.emit("comment.hidden", 4, { comment_id: "cm_2", visibility: "hidden" }));
    await waitFor(() => expect(screen.queryByTestId("viewer-comment-cm_2")).toBeNull());
    act(() =>
      FakeEventSource.last!.emit("message.published", 5, message({ message_id: "msg_5", kind: "ai_answer", reply_to_comment_ids: ["cm_1"] })),
    );
    expect(await screen.findByTestId("viewer-reply-msg_5")).toHaveAttribute("data-kind", "ai_answer");
    expect(screen.queryByRole("button", { name: /switch to/ })).toBeNull(); // embedded: no own theme toggle
  });
});
