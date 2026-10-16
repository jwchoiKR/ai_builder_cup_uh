import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setLang } from "../../app/i18n";
import { reduceEvent, reduceSnapshot, type ClientState } from "../../app/state";
import type { SessionEvent } from "../../app/types";
import { CREAM, T0, catalog, comment, message, segment, session, snapshot } from "../../test/fixtures";
import { Viewer } from "../Viewer";
import { chatSignature, viewerChat } from "./chat";
import { api } from "../../app/api";
import { eventsUrl } from "../../app/sse";
import { useAudience } from "../../app/store";
import { Watching } from "../../components";
import { ID_KEY, NAME_KEY, readIdentity, saveIdentity, viewerId } from "./identity";
import { Animal, SPECIES } from "./animals";
import { POPUP_MS, ViewerView } from "./ViewerView";

const NOW = T0 + 10_000;

function stateWith(over: Parameters<typeof snapshot>[0] = {}): ClientState {
  return reduceSnapshot(snapshot(over), "viewer", NOW);
}

function apply(state: ClientState, ...events: SessionEvent[]): ClientState {
  return events.reduce((s, ev) => reduceEvent(s, ev, NOW), state);
}

function view(state: ClientState, extra: Partial<Parameters<typeof ViewerView>[0]> = {}) {
  // the source line is off for viewers by default; these tests cover it where it is switched on
  return <ViewerView state={state} catalog={catalog} connection="connected" theme="light" inputEnabled={false} showSources {...extra} />;
}

describe("sources are not shown to viewers by default", () => {
  it("an AI answer shows its text and label only", () => {
    const state = stateWith({
      comments: [comment({ comment_id: "cm_9", author_name: "Lee", text: "price?", received_at: T0 })],
      messages: [
        message({ message_id: "msg_9", kind: "ai_answer", text: "It is S$36.00.", reply_to_comment_ids: ["cm_9"],
                  reply_to_author_names: ["Lee"], published_at: T0 + 2000,
                  citations: [{ passage_id: "DL-CR-01#key-facts#live-broadcast-price", quote: "Live broadcast price: S$36.00", section: "Key facts" }] }),
      ],
    });
    render(view(state, { showSources: false }));
    const reply = screen.getByTestId("viewer-reply-msg_9");
    expect(reply).toHaveTextContent("It is S$36.00.");
    expect(within(reply).getByText("AI answer")).toBeInTheDocument();
    expect(within(reply).queryByTestId("viewer-source")).toBeNull();
    expect(within(reply).queryByText(/Source:/)).toBeNull();
  });
});

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
  window.localStorage.clear();
  setLang("en");
});

/** This browser's viewer joined the chat earlier as `authorId`. */
function joinedAs(authorId: string, name = "Me") {
  window.localStorage.setItem(ID_KEY, authorId);
  window.localStorage.setItem(NAME_KEY, name);
}

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
    // in its place: who wrote it and that it was hidden, never what it said
    const line = screen.getByTestId("viewer-hidden-cm_2");
    expect(line).toHaveTextContent("This comment has been hidden.");
    expect(line).toHaveTextContent(priya.author_name);
    expect(line).not.toHaveTextContent(priya.text);
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

describe("Viewer: where my own question stands", () => {
  const mine = comment({ comment_id: "cm_me", author_id: "v_me", author_name: "Mina", text: "Can I use it while pregnant?", received_at: T0 + 3000 });
  const statusEvent = (seq: number, c: typeof mine, reply_status: string | null): SessionEvent => ({
    seq, type: "comment.status", payload: { ...c, reply_status },
  });

  it("shows a calm status line under my own waiting question, by status, inside the chat's live region", () => {
    joinedAs("v_me");
    let state = stateWith({ comments: [raj, { ...mine, reply_status: "checking" }] });
    const { rerender } = render(view(state));
    const line = screen.getByTestId("viewer-reply-status-cm_me");
    expect(line).toHaveTextContent("Checking…");
    expect(line).toHaveAttribute("data-status", "checking");
    expect(screen.getByTestId("viewer-chat")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByTestId("viewer-chat").contains(line)).toBe(true);
    expect(within(screen.getByTestId("viewer-comment-cm_me")).getByTestId("viewer-reply-status-cm_me")).toBeInTheDocument();

    state = apply(state, statusEvent(11, mine, "host"));
    rerender(view(state));
    expect(screen.getByTestId("viewer-reply-status-cm_me")).toHaveTextContent("The host will answer this on air");
    state = apply(state, statusEvent(12, mine, "team"));
    rerender(view(state));
    expect(screen.getByTestId("viewer-reply-status-cm_me")).toHaveTextContent("Sent to the team");
    state = apply(state, statusEvent(13, mine, null)); // the question was closed: the line goes away
    rerender(view(state));
    expect(screen.queryByTestId("viewer-reply-status-cm_me")).toBeNull();
  });

  it("shows nothing extra under other viewers' questions, or before I have joined", () => {
    const others = [{ ...raj, reply_status: "host" as const }, { ...priya, reply_status: "team" as const }];
    const { unmount } = render(view(stateWith({ comments: [...others, { ...mine, reply_status: "checking" }] })));
    expect(screen.queryAllByTestId(/^viewer-reply-status-/)).toHaveLength(0); // no identity in this browser
    unmount();
    joinedAs("v_me");
    render(view(stateWith({ comments: [...others, { ...mine, reply_status: "checking" }] })));
    expect(screen.getAllByTestId(/^viewer-reply-status-/).map((e) => e.getAttribute("data-testid"))).toEqual(["viewer-reply-status-cm_me"]);
  });

  it("the reply takes over once it is posted: no status line and no 'answered' label", () => {
    joinedAs("v_me");
    let state = stateWith({ comments: [{ ...mine, reply_status: "team" }] });
    const { rerender } = render(view(state));
    expect(screen.getByTestId("viewer-reply-status-cm_me")).toBeInTheDocument();
    // the reply arrives before the status event: the line is already gone
    state = apply(state, { seq: 11, type: "message.published", payload: message({ message_id: "msg_me", kind: "brand_answer", text: "Please ask your doctor first.", reply_to_comment_ids: ["cm_me"], reply_to_author_names: ["Mina"] }) });
    rerender(view(state));
    expect(screen.queryByTestId("viewer-reply-status-cm_me")).toBeNull();
    expect(within(screen.getByTestId("viewer-comment-cm_me")).getByTestId("viewer-reply-msg_me")).toBeInTheDocument();
    state = apply(state, statusEvent(12, mine, "answered"));
    rerender(view(state));
    expect(screen.queryByTestId("viewer-reply-status-cm_me")).toBeNull();
    expect(screen.getByTestId("viewer-comment-cm_me")).not.toHaveTextContent(/answered/i);
  });

  it("an 'answered' status without a reply in view renders nothing: publish state is never made up", () => {
    joinedAs("v_me");
    render(view(stateWith({ comments: [{ ...mine, reply_status: "answered" }] })));
    expect(screen.queryByTestId("viewer-reply-status-cm_me")).toBeNull();
    expect(within(screen.getByTestId("viewer-comment-cm_me")).queryByTestId(/^viewer-reply-/)).toBeNull();
  });

  it("a later asker of a coalesced reply keeps 'Also answered' and gets no status line", () => {
    joinedAs("u_priya");
    render(view(stateWith({
      comments: [raj, { ...priya, reply_status: "checking" }],
      messages: [message({ message_id: "msg_1", kind: "host_answer", reply_to_comment_ids: ["cm_1", "cm_2"], reply_to_author_names: ["Raj", "Priya"] })],
    })));
    expect(screen.getByTestId("viewer-also-answered-cm_2")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer-reply-status-cm_2")).toBeNull();
  });

  it("joining the chat in this page makes my next question mine", async () => {
    vi.useRealTimers();
    const onSend = vi.fn(async () => ({}));
    const { rerender } = render(view(stateWith(), { inputEnabled: true, onSend }));
    fireEvent.change(screen.getByTestId("viewer-input"), { target: { value: "Mina" } });
    fireEvent.submit(screen.getByTestId("viewer-input").closest("form")!);
    await waitFor(() => expect(screen.getByTestId("viewer-input")).toHaveAttribute("placeholder", "Chat as Mina"));
    const id = window.localStorage.getItem(ID_KEY)!;
    rerender(view(stateWith({ comments: [{ ...mine, author_id: id, reply_status: "checking" }] }), { inputEnabled: true, onSend }));
    expect(screen.getByTestId("viewer-reply-status-cm_me")).toHaveTextContent("Checking…");
  });

  it("the status line follows the screen language, and the chat stays pinned when it appears", () => {
    joinedAs("v_me");
    setLang("ko");
    const state = stateWith({ comments: [{ ...mine, reply_status: "host" }] });
    render(view(state));
    expect(screen.getByTestId("viewer-reply-status-cm_me")).toHaveTextContent("진행자가 방송에서 답변할 예정입니다");
    const plain = stateWith({ comments: [mine] });
    expect(chatSignature(viewerChat(state, NOW, "v_me"))).not.toBe(chatSignature(viewerChat(plain, NOW, "v_me")));
  });
});

describe("Viewer: a reply in the language I asked in", () => {
  const mine = comment({ comment_id: "cm_ko", author_id: "v_me", author_name: "민아", text: "크림 얼마예요?", received_at: T0 + 3000, language: "ko" });
  const reply = message({ message_id: "msg_t", kind: "ai_answer", text: "It is S$36.00 during this live.", reply_to_comment_ids: ["cm_ko"], reply_to_author_names: ["민아"], published_at: T0 + 5000 });
  const translated: SessionEvent = { seq: 21, type: "message.updated", payload: { ...reply, translations: { ko: "이번 라이브에서는 S$36.00입니다." } } };

  it("shows the translation with the original reply beneath it, once the translation arrives", () => {
    joinedAs("v_me");
    let state = stateWith({ comments: [mine], messages: [reply] });
    const { rerender } = render(view(state));
    const card = screen.getByTestId("viewer-reply-msg_t");
    expect(card).toHaveTextContent("It is S$36.00 during this live.");
    expect(screen.queryByTestId("viewer-reply-translation-msg_t")).toBeNull();

    state = apply(state, translated);
    rerender(view(state));
    const translation = screen.getByTestId("viewer-reply-translation-msg_t");
    const original = screen.getByTestId("viewer-reply-original-msg_t");
    expect(translation).toHaveTextContent("이번 라이브에서는 S$36.00입니다.");
    expect(translation).toHaveAttribute("lang", "ko");
    expect(original).toHaveTextContent("It is S$36.00 during this live.");
    expect(translation.compareDocumentPosition(original) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(screen.getByTestId("viewer-reply-msg_t")).getByText("AI answer")).toBeInTheDocument();
  });

  it("shows the original only when I asked in the show's language or the reply has no translation in mine", () => {
    joinedAs("v_me");
    const english = { ...mine, language: null };
    const { unmount } = render(view(apply(stateWith({ comments: [english], messages: [reply] }), translated)));
    expect(screen.queryByTestId("viewer-reply-translation-msg_t")).toBeNull();
    expect(screen.getByTestId("viewer-reply-msg_t")).toHaveTextContent("It is S$36.00 during this live.");
    unmount();
    const japanese = { ...mine, language: "ja" };
    render(view(apply(stateWith({ comments: [japanese], messages: [reply] }), translated)));
    expect(screen.queryByTestId("viewer-reply-translation-msg_t")).toBeNull();
  });

  it("shows the original only for a reply addressed to others", () => {
    joinedAs("v_someone_else");
    render(view(apply(stateWith({ comments: [mine], messages: [reply] }), translated)));
    expect(screen.queryByTestId("viewer-reply-translation-msg_t")).toBeNull();
    expect(screen.getByTestId("viewer-reply-msg_t")).toHaveTextContent("It is S$36.00 during this live.");
    expect(screen.getByTestId("viewer-reply-msg_t")).not.toHaveTextContent("이번 라이브에서는");
  });

  it("a coalesced reply shown under the first asker is translated for me when I am a later asker", () => {
    joinedAs("v_me");
    const both = { ...reply, reply_to_comment_ids: ["cm_1", "cm_ko"], reply_to_author_names: ["Raj", "민아"], translations: { ko: "이번 라이브에서는 S$36.00입니다." } };
    render(view(stateWith({ comments: [raj, mine], messages: [both] })));
    expect(within(screen.getByTestId("viewer-comment-cm_1")).getByTestId("viewer-reply-translation-msg_t")).toBeInTheDocument();
    expect(screen.getByTestId("viewer-also-answered-cm_ko")).toBeInTheDocument();
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
    expect(within(video).getByText("DL")).toBeInTheDocument();  // D-332: the brand's initials, not an empty frame
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
    expect(input).toHaveAttribute("placeholder", "Enter a name to join the chat");
    expect(input).toHaveAccessibleName("Your display name");
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
          : path.split("?")[0] === "/api/catalog"
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

describe("D-474/D-476: viewer animals on the video", () => {
  /** a comment by `who`, `ago` ms before the server's now */
  const said = (who: string, ago: number, over: Partial<Parameters<typeof comment>[0]> = {}) =>
    comment({ comment_id: `cm_${who}_${ago}`, author_id: `u_${who}`, author_name: who, text: `hello from ${who}`,
              received_at: NOW - ago, group_id: null, kind: "reaction", ...over });
  const shown = () => screen.queryAllByTestId(/^viewer-figure-/).filter((e) => !e.hasAttribute("data-leaving"));
  const figures = () => shown().map((e) => e.getAttribute("data-testid")!.slice(14));
  const bubbles = () => screen.queryAllByTestId(/^viewer-bubble-/).map((e) => e.getAttribute("data-testid")!.slice(14));

  it("keeps 6 animals of 6 different species: a newcomer replaces the longest-silent one, the viewer's own stays", () => {
    joinedAs("u_me");
    const others = Array.from({ length: 6 }, (_, i) => said(`p${i}`, 50_000 - i * 1000));
    render(view(stateWith({ comments: [said("me", 60_000), ...others] })));
    const ids = figures();
    expect(ids).toHaveLength(6);
    expect(ids).toContain("u_me");  // the oldest, but never replaced
    expect(ids).not.toContain("u_p0");  // the longest-silent of the others
    expect(screen.getByTestId("viewer-figure-u_p0")).toHaveAttribute("data-leaving");  // fading out
    act(() => vi.advanceTimersByTime(400));
    expect(screen.queryByTestId("viewer-figure-u_p0")).toBeNull();
    expect(new Set(shown().map((e) => e.getAttribute("data-species"))).size).toBe(6);
    expect(screen.getByTestId("viewer-figure-u_me")).toHaveAttribute("data-own");
    expect(screen.getByTestId("viewer-crowd")).toHaveAttribute("aria-hidden");
  });

  it("an animal stops where it is while it speaks (D-480: front view for a chat too) and walks on after 4 s", () => {
    const { rerender } = render(view(stateWith({ comments: [said("old", 15_000), said("ann", 1000)] })));
    const ann = () => screen.getByTestId("viewer-figure-u_ann");
    const walk = ann().getAttribute("style");
    expect(ann()).toHaveAttribute("data-stopped");
    expect(screen.getByTestId("viewer-figure-u_old")).not.toHaveAttribute("data-stopped");
    expect(ann().querySelector("svg")).toHaveAttribute("data-view", "front");
    expect(screen.getByTestId("viewer-figure-u_old").querySelector("svg")).toHaveAttribute("data-view", "side");
    act(() => vi.advanceTimersByTime(2000));
    rerender(view(stateWith({ comments: [said("old", 15_000), said("ann", 1000)] })));
    expect(ann()).toHaveAttribute("data-stopped");
    expect(ann().getAttribute("style")).toBe(walk);  // its walk (and so its paused spot) is unchanged
    act(() => vi.advanceTimersByTime(2000));
    expect(ann()).not.toHaveAttribute("data-stopped");
    expect(ann().getAttribute("style")!.replace(/z-index: \d+;?/, "")).toBe(walk!.replace(/z-index: \d+;?/, ""));
  });

  it("a hidden comment adds no figure and no bubble", () => {
    render(view(stateWith({ comments: [said("ann", 1000, { visibility: "hidden" })] })));
    expect(figures()).toEqual([]);
    expect(bubbles()).toEqual([]);
  });

  it("shows a fresh comment's bubble for 4 s; an old one (page load) adds its figure only", () => {
    render(view(stateWith({ comments: [said("old", 15_000), said("ann", 1000)] })));
    expect(figures()).toEqual(["u_old", "u_ann"]);
    expect(bubbles()).toEqual(["u_ann"]);
    expect(screen.getByTestId("viewer-bubble-u_ann")).toHaveTextContent("hello from ann");
    act(() => vi.advanceTimersByTime(3900));
    expect(bubbles()).toEqual(["u_ann"]);
    act(() => vi.advanceTimersByTime(100));
    expect(bubbles()).toEqual([]);
    expect(figures()).toEqual(["u_old", "u_ann"]);
  });

  it("a comment hidden while its bubble is up loses the bubble at once", () => {
    let state = stateWith({ comments: [said("ann", 1000)] });
    const { rerender } = render(view(state));
    expect(bubbles()).toEqual(["u_ann"]);
    state = apply(state, { seq: 11, type: "comment.hidden", payload: { comment_id: "cm_ann_1000", visibility: "hidden" } });
    rerender(view(state));
    expect(bubbles()).toEqual([]);
  });

  it("shows at most 3 bubbles: a 4th closes the oldest, the newest on top", () => {
    const first = [said("a", 3000), said("b", 2000), said("c", 1000)];
    const { rerender } = render(view(stateWith({ comments: first })));
    expect(bubbles().sort()).toEqual(["u_a", "u_b", "u_c"]);
    rerender(view(stateWith({ comments: [...first, said("d", 500)] })));
    expect(bubbles().sort()).toEqual(["u_b", "u_c", "u_d"]);
    // D-476: the speaking animal (and so its bubble) is in front, the newest on top
    expect(screen.getByTestId("viewer-figure-u_d").style.zIndex).toBe("13");
    expect(screen.getByTestId("viewer-figure-u_b").style.zIndex).toBe("11");
    expect(screen.getByTestId("viewer-figure-u_a").style.zIndex).toBe("3");  // D-478: a walker in the front lane
  });

  it("D-475: an older bubble that overlaps a newer one moves up a row", () => {
    const spy = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const id = this.getAttribute("data-testid");  // a and b overlap, c stands apart
      const x = id === "viewer-bubble-u_a" ? 0 : id === "viewer-bubble-u_b" ? 80 : 300;
      return { left: x, right: x + 120, top: 0, bottom: 20 } as DOMRect;
    });
    try {
      render(view(stateWith({ comments: [said("a", 3000), said("b", 2000), said("c", 1000)] })));
      const lift = (who: string) => screen.getByTestId(`viewer-bubble-u_${who}`).style.getPropertyValue("--lift");
      expect([lift("a"), lift("b"), lift("c")]).toEqual(["1", "0", "0"]);
    } finally {
      spy.mockRestore();
    }
  });
});

describe("D-475: raised hands and hearts", () => {
  const said = (who: string, ago: number, over: Partial<Parameters<typeof comment>[0]> = {}) =>
    comment({ comment_id: `cm_${who}`, author_id: `u_${who}`, author_name: who, text: `hello from ${who}`,
              received_at: NOW - ago, group_id: null, kind: "reaction", ...over });
  const flag = (who: string, name: "hand" | "happy") =>
    screen.queryByTestId(`viewer-figure-u_${who}`)?.hasAttribute(`data-${name}`) ?? false;
  const answer = (id: string, kind: "host_answer" | "ai_answer" | "brand_answer", to: string[]) =>
    message({ message_id: id, kind, text: "Yes.", group_id: null, reply_to_comment_ids: to, reply_to_author_names: to,
              published_at: NOW });

  it("a question status that comes after the bubble closed raises the paw only (D-481: until closed); no status, no paw", () => {
    const { rerender } = render(view(stateWith({ comments: [said("ann", 1000), said("bob", 1000)] })));
    act(() => vi.advanceTimersByTime(5000));  // the bubbles are gone
    rerender(view(stateWith({ comments: [said("ann", 1000, { reply_status: "checking" }), said("bob", 1000)] })));
    expect(flag("ann", "hand")).toBe(true);
    expect(screen.queryByTestId("viewer-bubble-u_ann")).toBeNull();  // never reopened
    expect(screen.getByTestId("viewer-figure-u_ann").querySelector("svg")).toHaveAttribute("data-view", "front");  // D-476
    expect(screen.getByTestId("viewer-figure-u_bob").querySelector("svg")).toHaveAttribute("data-view", "side");
    expect(flag("bob", "hand")).toBe(false);
    act(() => vi.advanceTimersByTime(30_000));
    expect(flag("ann", "hand")).toBe(true);  // still waiting
    rerender(view(stateWith({ comments: [said("ann", 1000, { reply_status: null }), said("bob", 1000)] })));
    expect(flag("ann", "hand")).toBe(false);  // closed back to chat
  });

  it("a host answer to two askers makes both happy, and puts the hand down", () => {
    const asked = [said("ann", 2000, { reply_status: "host" }), said("bob", 1000, { reply_status: "host" })];
    const { rerender } = render(view(stateWith({ comments: asked })));
    expect(flag("ann", "hand")).toBe(true);
    rerender(view(stateWith({ comments: asked, messages: [answer("msg_h", "host_answer", ["cm_ann", "cm_bob"])] })));
    expect(flag("ann", "happy") && flag("bob", "happy")).toBe(true);
    expect(flag("ann", "hand")).toBe(false);
    expect(screen.getAllByTestId("viewer-heart")).toHaveLength(12);  // D-476: 6 hearts each
    // D-481: the hearts end the held bubble at once, so the happy animal keeps the side view (D-480)
    expect(screen.queryByTestId("viewer-bubble-u_ann")).toBeNull();
    expect(screen.getByTestId("viewer-figure-u_ann").querySelector("svg")).toHaveAttribute("data-view", "side");
    act(() => vi.advanceTimersByTime(2000));
    expect(flag("ann", "happy") || flag("bob", "happy")).toBe(false);
  });

  it("answers already there at page load or replayed after a reconnect are not celebrated", () => {
    const comments = [said("ann", 2000, { reply_status: "answered" })];
    const messages = [answer("msg_h", "host_answer", ["cm_ann"]), answer("msg_a", "ai_answer", ["cm_ann"])];
    const { rerender } = render(view(stateWith({ comments, messages })));
    expect(flag("ann", "happy")).toBe(false);
    rerender(view(stateWith({ comments: [...comments], messages: [...messages] })));  // the snapshot again
    expect(flag("ann", "happy")).toBe(false);
  });

  it("D-483: an AI or brand answer brings hearts too; a notice or a correction does not", () => {
    const comments = [said("ann", 2000, { reply_status: "answered" }), said("bob", 1500, { reply_status: "answered" })];
    const first = render(view(stateWith({ comments })));
    first.rerender(view(stateWith({ comments, messages: [answer("msg_a", "ai_answer", ["cm_ann"]), answer("msg_b", "brand_answer", ["cm_bob"])] })));
    expect(flag("ann", "happy") && flag("bob", "happy")).toBe(true);
    first.unmount();
    const quiet = [said("cy", 1000, { reply_status: "answered" })];
    const again = render(view(stateWith({ comments: quiet })));
    again.rerender(view(stateWith({ comments: quiet, messages: [
      { ...answer("msg_n", "ai_answer", ["cm_cy"]), kind: "notice" },
      { ...answer("msg_c", "ai_answer", ["cm_cy"]), kind: "correction_notice" },
    ] })));
    expect(flag("cy", "happy")).toBe(false);
    expect(screen.queryAllByTestId("viewer-heart")).toHaveLength(0);
  });

  it("a figure waiting for an answer keeps its slot; the longest-silent of the rest gives way", () => {
    const others = Array.from({ length: 6 }, (_, i) => said(`p${i}`, 50_000 - i * 1000, i === 0 ? { reply_status: "team" } : {}));
    render(view(stateWith({ comments: [...others, said("new", 1000)] })));
    const ids = screen.queryAllByTestId(/^viewer-figure-/).filter((e) => !e.hasAttribute("data-leaving"))
      .map((e) => e.getAttribute("data-testid")!.slice(14));
    expect(ids).toContain("u_p0");
    expect(ids).not.toContain("u_p1");
    expect(ids).toContain("u_new");
  });

  it("under reduced motion the hearts are one still heart", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} }));
    const asked = [said("ann", 1000, { reply_status: "host" })];
    const { rerender } = render(view(stateWith({ comments: asked })));
    rerender(view(stateWith({ comments: asked, messages: [answer("msg_h", "host_answer", ["cm_ann"])] })));
    const hearts = screen.getAllByTestId("viewer-heart");
    expect(hearts).toHaveLength(1);
    expect(hearts[0]).toHaveAttribute("data-still");
    expect(screen.getByTestId("viewer-figure-u_ann")).toHaveAttribute("data-still");  // D-476: no walking
  });
});

describe("D-477: viewers watching", () => {
  it("the viewer page makes its id on open, without a name, and keeps it when the viewer joins the chat", () => {
    const id = viewerId();
    expect(id).toMatch(/^v_/);
    expect(window.localStorage.getItem(ID_KEY)).toBe(id);
    expect(readIdentity()).toBeNull();  // chatting still needs a name
    expect(viewerId()).toBe(id);
    expect(saveIdentity("Kim").authorId).toBe(id);
    expect(eventsUrl("ses_1", "viewer", 0, id)).toContain(`&viewer_id=${id}`);
    expect(eventsUrl("ses_1", "host", 0)).not.toContain("viewer_id");
  });

  it("shows the count on the video, and nothing while it is unknown", () => {
    const { rerender } = render(view(stateWith(), { audience: 4 }));
    expect(screen.getByTestId("audience-count")).toHaveTextContent("4 watching");
    rerender(view(stateWith(), { audience: 0 }));
    expect(screen.getByTestId("audience-count")).toHaveTextContent("0 watching");  // a confirmed 0 is shown
    rerender(view(stateWith(), { audience: null }));
    expect(screen.queryByTestId("audience-count")).toBeNull();
    setLang("ko");
    rerender(view(stateWith(), { audience: 4 }));
    expect(screen.getByTestId("audience-count")).toHaveTextContent("시청 중 4명");
  });

  it("polls every 10 s and hides the number after a failure instead of keeping the old one", async () => {
    const audience = vi.spyOn(api, "audience")
      .mockResolvedValueOnce({ count: 7, at: NOW })
      .mockRejectedValueOnce(new Error("503"))
      .mockResolvedValueOnce({ count: 2, at: NOW });
    function Probe() {
      return <Watching count={useAudience("ses_1")} />;
    }
    render(<Probe />);
    await act(async () => {});
    expect(screen.getByTestId("audience-count")).toHaveTextContent("7 watching");
    await act(async () => vi.advanceTimersByTime(11_000));
    expect(screen.queryByTestId("audience-count")).toBeNull();
    await act(async () => vi.advanceTimersByTime(11_000));
    expect(screen.getByTestId("audience-count")).toHaveTextContent("2 watching");
    expect(audience).toHaveBeenCalledTimes(3);
    audience.mockRestore();
  });
});

describe("D-478: names and lanes", () => {
  const said = (who: string, ago: number) =>
    comment({ comment_id: `cm_${who}`, author_id: `u_${who}`, author_name: who, text: `hello from ${who}`,
              received_at: NOW - ago, group_id: null, kind: "reaction" });

  it("a walking animal shows no name; a speaking one and the viewer's own do", () => {
    joinedAs("u_me");
    render(view(stateWith({ comments: [said("me", 30_000), said("old", 20_000), said("ann", 1000)] })));
    const shown = (who: string) => {
      const el = screen.getByTestId(`viewer-figure-u_${who}`);
      return [...el.querySelectorAll("span")].find((s) => s.textContent === who)!.hasAttribute("data-shown");
    };
    expect(shown("old")).toBe(false);  // walking
    expect(shown("ann")).toBe(true);  // speaking
    expect(shown("me")).toBe(true);  // own
    act(() => vi.advanceTimersByTime(4000));
    expect(shown("ann")).toBe(false);  // walks on: the name fades out
  });

  it("walkers keep to 3 lanes by roster slot, the lower lane in front", () => {
    const people = ["a", "b", "c", "d", "e"].map((w, i) => said(w, 60_000 - i * 1000));
    render(view(stateWith({ comments: people })));
    const lane = (w: string) => screen.getByTestId(`viewer-figure-u_${w}`).style.getPropertyValue("--lane");
    const z = (w: string) => screen.getByTestId(`viewer-figure-u_${w}`).style.zIndex;
    expect(["a", "b", "c", "d", "e"].map(lane)).toEqual(["0", "1", "2", "0", "1"]);
    expect(["a", "b", "c"].map(z)).toEqual(["3", "2", "1"]);
  });
});

describe("D-480: facing and posture", () => {
  const said = (who: string, ago: number) =>
    comment({ comment_id: `cm_${who}`, author_id: `u_${who}`, author_name: who, text: `hello from ${who}`,
              received_at: NOW - ago, group_id: null, kind: "reaction", reply_status: "host" });

  it("an animal with hearts and no bubble keeps the side view", () => {
    const asked = [said("ann", 1000)];
    const { rerender } = render(view(stateWith({ comments: asked })));
    act(() => vi.advanceTimersByTime(4000));  // its bubble and paw are over
    rerender(view(stateWith({ comments: asked, messages: [message({ message_id: "msg_h", kind: "host_answer", text: "Yes.",
      group_id: null, reply_to_comment_ids: ["cm_ann"], reply_to_author_names: ["ann"], published_at: NOW + 4000 })] })));
    const ann = screen.getByTestId("viewer-figure-u_ann");
    expect(ann).toHaveAttribute("data-happy");
    expect(ann.querySelector("svg")).toHaveAttribute("data-view", "side");
  });

  it("every animal stands upright in the side view: its body is under its head, in both step frames", () => {
    for (const species of SPECIES) {
      for (const frame of [0, 1] as const) {
        const { container, unmount } = render(<Animal species={species} view="side" frame={frame} />);
        const ink = container.querySelector("svg > g:nth-of-type(2)")!;  // the silhouette (the first group is the halo)
        const head = Number(ink.querySelector(":scope > circle[r='11.5']")!.getAttribute("cx"));
        const group = ink.querySelector(":scope > g[transform]")!;
        const shift = Number(/translate\((-?[\d.]+)/.exec(group.getAttribute("transform")!)![1]);
        const body = Number(group.querySelector(":scope > ellipse")!.getAttribute("cx")) + shift;
        expect(Math.abs(body - head), `${species} frame ${frame}`).toBeLessThanOrEqual(1.5);
        expect(group.getAttribute("transform")).not.toMatch(/rotate|skew/);  // the body is only moved, never tilted
        unmount();
      }
    }
  });
});

describe("D-481: a question's bubble stays up until it is answered", () => {
  const q = (who: string, ago: number, status: "checking" | "host" | "team" | "answered" | null = "checking") =>
    comment({ comment_id: `cm_${who}`, author_id: `u_${who}`, author_name: who, text: `question from ${who}`,
              received_at: NOW - ago, group_id: null, kind: "question", reply_status: status });
  const chat = (who: string, ago: number) =>
    comment({ comment_id: `cm_${who}`, author_id: `u_${who}`, author_name: who, text: `hi from ${who}`,
              received_at: NOW - ago, group_id: null, kind: "reaction" });
  const bubble = (who: string) => screen.queryByTestId(`viewer-bubble-u_${who}`) !== null;
  const paw = (who: string) => screen.getByTestId(`viewer-figure-u_${who}`).hasAttribute("data-hand");
  const reply = (id: string, kind: "host_answer" | "ai_answer", to: string) =>
    message({ message_id: id, kind, text: "Yes.", group_id: null, reply_to_comment_ids: [to], reply_to_author_names: [to],
              published_at: NOW });

  it("holds past 4 s; an answered status with no reply yet closes it 1 s later, without hearts", () => {
    const { rerender } = render(view(stateWith({ comments: [q("ann", 500)] })));
    act(() => vi.advanceTimersByTime(20_000));
    expect(bubble("ann") && paw("ann")).toBe(true);
    rerender(view(stateWith({ comments: [q("ann", 500, "answered")] })));
    expect(bubble("ann")).toBe(true);  // waits 1 s for the reply's hearts
    act(() => vi.advanceTimersByTime(1000));
    expect(bubble("ann") || paw("ann")).toBe(false);
    expect(screen.getByTestId("viewer-figure-u_ann")).not.toHaveAttribute("data-happy");
  });

  it("D-483: an AI answer brings the hearts and closes it at once", () => {
    const { rerender } = render(view(stateWith({ comments: [q("ann", 500)] })));
    act(() => vi.advanceTimersByTime(20_000));
    rerender(view(stateWith({ comments: [q("ann", 500, "answered")], messages: [reply("m_ai", "ai_answer", "cm_ann")] })));
    expect(screen.getByTestId("viewer-figure-u_ann")).toHaveAttribute("data-happy");
    expect(bubble("ann") || paw("ann")).toBe(false);
  });

  it("a host answer brings the hearts and closes it at once", () => {
    const { rerender } = render(view(stateWith({ comments: [q("ann", 500)] })));
    act(() => vi.advanceTimersByTime(20_000));
    rerender(view(stateWith({ comments: [q("ann", 500, "answered")], messages: [reply("m_h", "host_answer", "cm_ann")] })));
    expect(screen.getByTestId("viewer-figure-u_ann")).toHaveAttribute("data-happy");
    expect(bubble("ann") || paw("ann")).toBe(false);
  });

  it("a null status or hiding the comment closes it", () => {
    let state = stateWith({ comments: [q("ann", 500), q("bob", 400)] });
    const { rerender } = render(view(state));
    act(() => vi.advanceTimersByTime(10_000));
    rerender(view(stateWith({ comments: [q("ann", 500, null), q("bob", 400)] })));
    expect(bubble("ann") || paw("ann")).toBe(false);
    expect(bubble("bob")).toBe(true);
    state = apply(stateWith({ comments: [q("ann", 500, null), q("bob", 400)] }),
      { seq: 11, type: "comment.hidden", payload: { comment_id: "cm_bob", visibility: "hidden" } });
    rerender(view(state));
    expect(bubble("bob")).toBe(false);
  });

  it("closes after 90 s from the comment and the animal walks on", () => {
    render(view(stateWith({ comments: [q("ann", 500)] })));
    act(() => vi.advanceTimersByTime(89_000));
    expect(bubble("ann")).toBe(true);
    act(() => vi.advanceTimersByTime(600));
    expect(bubble("ann") || paw("ann")).toBe(false);
    expect(screen.getByTestId("viewer-figure-u_ann")).not.toHaveAttribute("data-stopped");
  });

  it("a status inside the first 4 s extends the open bubble without closing it", () => {
    const { rerender } = render(view(stateWith({ comments: [chat("ann", 500)] })));
    act(() => vi.advanceTimersByTime(2000));
    rerender(view(stateWith({ comments: [q("ann", 500, "host")] })));
    act(() => vi.advanceTimersByTime(10_000));
    expect(bubble("ann") && paw("ann")).toBe(true);
  });

  it("a 3rd question closes the oldest held one; a chat replaces the chat bubble, never a held question", () => {
    const { rerender } = render(view(stateWith({ comments: [q("a", 900), q("b", 800), chat("c", 700)] })));
    expect([bubble("a"), bubble("b"), bubble("c")]).toEqual([true, true, true]);
    rerender(view(stateWith({ comments: [q("a", 900), q("b", 800), chat("c", 700), chat("d", 600)] })));
    expect([bubble("a"), bubble("b"), bubble("c"), bubble("d")]).toEqual([true, true, false, true]);
    rerender(view(stateWith({ comments: [q("a", 900), q("b", 800), chat("c", 700), chat("d", 600), q("e", 500)] })));
    expect([bubble("a"), paw("a"), bubble("b"), bubble("d"), bubble("e")]).toEqual([false, false, true, true, true]);
  });
});

describe("D-482: a bubble comes up when triage has judged the comment", () => {
  const c = (kind: "pending" | "reaction" | "question" | "hide", ago = 500, over: Partial<Parameters<typeof comment>[0]> = {}) =>
    comment({ comment_id: "cm_ann", author_id: "u_ann", author_name: "ann", text: "is it vegan?", received_at: NOW - ago,
              group_id: null, kind, ...over });
  const bubble = () => screen.queryByTestId("viewer-bubble-u_ann") !== null;
  const ann = () => screen.getByTestId("viewer-figure-u_ann");

  it("the viewer state takes the verdict from comment.analyzed", () => {
    const state = apply(stateWith({ comments: [c("pending")] }),
      { seq: 11, type: "comment.analyzed", payload: { comment: { ...c("question"), reply_status: "checking" } } });
    expect(state.comments["cm_ann"]!.kind).toBe("question");
  });

  it("pending: the chat shows it at once, the animal joins, no bubble; a question verdict brings bubble, paw and front", () => {
    const { rerender } = render(view(stateWith({ comments: [c("pending")] })));
    expect(screen.getByTestId("viewer-comment-cm_ann")).toBeInTheDocument();
    expect(ann()).not.toHaveAttribute("data-stopped");
    expect(bubble()).toBe(false);
    act(() => vi.advanceTimersByTime(3000));
    rerender(view(stateWith({ comments: [c("question", 500, { reply_status: "checking" })] })));
    expect(bubble()).toBe(true);
    expect(ann()).toHaveAttribute("data-hand");
    expect(ann().querySelector("svg")).toHaveAttribute("data-view", "front");
    act(() => vi.advanceTimersByTime(30_000));
    expect(bubble()).toBe(true);  // held (D-481)
  });

  it("a chat verdict brings the 4 s bubble, facing front", () => {
    const { rerender } = render(view(stateWith({ comments: [c("pending")] })));
    rerender(view(stateWith({ comments: [c("reaction")] })));
    expect(bubble()).toBe(true);
    expect(ann()).not.toHaveAttribute("data-hand");
    expect(ann().querySelector("svg")).toHaveAttribute("data-view", "front");
    act(() => vi.advanceTimersByTime(4000));
    expect(bubble()).toBe(false);
  });

  it("a verdict later than 10 s still speaks for a comment first seen live; an old one from a snapshot never does", () => {
    const { rerender, unmount } = render(view(stateWith({ comments: [c("pending")] })));
    act(() => vi.advanceTimersByTime(15_000));
    rerender(view(stateWith({ comments: [c("reaction")] })));
    expect(bubble()).toBe(true);
    unmount();
    const again = render(view(stateWith({ comments: [c("pending", 20_000)] })));
    again.rerender(view(stateWith({ comments: [c("reaction", 20_000)] })));
    expect(bubble()).toBe(false);
  });

  it("hidden wins: a comment hidden before its verdict never speaks, not even after an unhide", () => {
    let state = stateWith({ comments: [c("pending")] });
    const { rerender } = render(view(state));
    state = apply(state, { seq: 11, type: "comment.hidden", payload: { comment_id: "cm_ann", visibility: "hidden" } });
    rerender(view(state));
    act(() => vi.advanceTimersByTime(20_000));
    rerender(view(stateWith({ comments: [c("reaction")] })));  // unhidden, judged
    expect(bubble()).toBe(false);
  });

  it("a question already answered when its verdict comes gets the plain 4 s bubble, no paw", () => {
    const { rerender } = render(view(stateWith({ comments: [c("pending")] })));
    rerender(view(stateWith({ comments: [c("question", 500, { reply_status: "answered" })] })));
    expect(bubble()).toBe(true);
    expect(ann()).not.toHaveAttribute("data-hand");
    act(() => vi.advanceTimersByTime(4000));
    expect(bubble()).toBe(false);
  });
});
