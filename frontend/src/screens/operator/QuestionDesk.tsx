// Question desk (§12.4.7): grouped questions sorted by status bucket then score, with actions.
import { ChevronDown, ChevronRight, FileText, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, type AnswerOrigin } from "../../app/api";
import { useT } from "../../app/i18n";
import { deskTabOf, draftAnswer, groupStatusLabel, pendingMessages, questionDesk, relativeTime, waitReason, type DeskTab } from "../../app/selectors";
import type { Answer, QuestionGroup } from "../../app/types";
import { Button, Chip } from "../../components";
import { useAction, useOperator } from "./context";
import { debugOn, useArrivalDot } from "./attention";
import { CommentTranslation } from "./CommentStream";
import { CitationSheet } from "./Dialogs";
import {
  citationLabel,
  deskTabCounts,
  groupActions,
  intentInfo,
  isStale,
  productLabel,
  setting,
  statusTone,
  type GroupAction,
} from "./model";
import styles from "./operator.module.css";

// §12.4.7 tabs: what waits for a person, what is answered, everything. Closed and rejected questions are listed only
// under All, so every group is in exactly one of To do / Answered / closed and the counts add up.
const TABS: { key: DeskTab; label: string }[] = [
  { key: "todo", label: "To do" },
  { key: "answered", label: "Answered" },
  { key: "all", label: "All" },
];

export function QuestionDesk() {
  const t = useT();
  const { state, focusedGroup } = useOperator();
  const [tab, setTab] = useState<DeskTab>("todo");
  // The operator's own expand/collapse choice, once made ({id: null} = everything collapsed). Until then the first
  // row of To do is open, so the suggested reply is there without a click.
  const [choice, setChoice] = useState<{ id: string | null } | null>(null);
  const [auto, setAuto] = useState<string | null>(null);
  const all = Object.values(state.groups);
  const counts = deskTabCounts(all);
  const groups = questionDesk(state, tab);
  const topN = setting(state, "HOST_TOP_N");

  // the row opened by default stays open while it stays in the list (a reply typed in it is not lost when a more
  // urgent question arrives); when it leaves the list (posted), the first row of the list opens
  const firstId = tab === "todo" ? (groups[0]?.group_id ?? null) : null;
  const autoId = tab === "todo" ? (auto && groups.some((g) => g.group_id === auto) ? auto : firstId) : null;
  useEffect(() => {
    if (autoId !== auto && tab === "todo") setAuto(autoId);
  }, [autoId, auto, tab]);
  const chosen = choice && (choice.id === null || groups.some((g) => g.group_id === choice.id)) ? choice.id : undefined;
  const expanded = chosen !== undefined ? chosen : autoId;

  // a new question that needs a person, while the operator is on another tab: a dot on the To do tab
  const todoIds = all.filter((g) => deskTabOf(g) === "todo").map((g) => g.group_id).sort();
  const todoDot = useArrivalDot(todoIds, state.loaded, tab === "todo");

  useEffect(() => {
    if (!focusedGroup) return;
    const g = state.groups[focusedGroup];
    const list = g ? deskTabOf(g, state.messages[g.published_message_id ?? ""]?.kind) : "closed";
    setTab(list === "closed" ? "all" : list); // the list the question is in; closed ones are only under All
    setChoice({ id: focusedGroup });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedGroup]);

  return (
    <section className={[styles.block, styles.desk].join(" ")} data-testid="op-question-desk" aria-label={t("Question desk")}>
      <div className={styles.blockHeader}>
        <div>
          <h2 className={styles.blockTitle}>
            {t("Question desk")} <span className="tabular" data-testid="op-desk-count">{counts.all}</span>
          </h2>
          <p className={styles.muted}>{t("Viewer questions that need a person. Check the suggested reply, edit it if you want, and post.")}</p>
        </div>
        <span className={["tabular", styles.muted].join(" ")}>
          {t("{n}/{max} on host", { n: state.hostSlots.length, max: topN })}
        </span>
      </div>
      <div className={styles.tabs} role="tablist">
        {TABS.map((x) => (
          <button
            key={x.key}
            type="button"
            role="tab"
            data-testid={`op-desk-tab-${x.key}`}
            aria-selected={tab === x.key}
            className={[styles.tab, tab === x.key && styles.tabActive].filter(Boolean).join(" ")}
            onClick={() => setTab(x.key)}
          >
            {t(x.label)} <span className="tabular">{counts[x.key]}</span>
            {x.key === "todo" && todoDot && (
              <span className={styles.attnDot} data-testid="op-todo-dot" role="img" aria-label={t("New question")} />
            )}
          </button>
        ))}
      </div>
      {groups.length === 0 ? (
        <p className={styles.empty} data-testid="op-desk-empty">
          {tab === "todo"
            ? t("Nothing is waiting for you. Questions that need a person appear here.")
            : tab === "answered"
              ? t("No answered questions yet.")
              : t("No questions here yet.")}
        </p>
      ) : (
        <ul className={styles.groupList}>
          {groups.map((g) => (
            <GroupRow
              key={g.group_id}
              group={g}
              expanded={expanded === g.group_id}
              onToggle={() => setChoice({ id: expanded === g.group_id ? null : g.group_id })}
            />
          ))}
        </ul>
      )}
    </section>
  );
}


/** "Top questions by category": busiest intents first; a chip filters the desk (aria-pressed). */
/** The one reply offered when the product information holds no answer: it states no fact, so nothing is made up.
 * It is posted in English like every reply; the reply translator adds the asker's language afterwards. */
export const NO_SOURCE_REPLY = "That isn't covered in our product information. Our team will check and get back to you.";

/** Why a draft is not verified, in the operator's words. The checker's own reasons are for developers (?debug=1). */
function unverifiedNote(errors: string[], hasText: boolean, t: (k: string, v?: Record<string, string | number>) => string): string {
  const note = hasText
    ? t("Not confirmed by the product sheet. Check it before you post.")
    : t("The product information does not answer this.");
  return debugOn() && errors.length ? `${note} (${errors.join("; ")})` : note;
}

function GroupRow({ group: g, expanded, onToggle }: { group: QuestionGroup; expanded: boolean; onToggle: () => void }) {
  const t = useT();
  const { state, catalog, now, focusedGroup } = useOperator();
  const ref = useRef<HTMLLIElement>(null);
  const publishedKind = state.messages[g.published_message_id ?? ""]?.kind;
  const label = groupStatusLabel(g, publishedKind);
  const todo = deskTabOf(g, publishedKind) === "todo";
  const sensitive = Boolean(intentInfo(catalog, g.intent)?.sensitive) || g.approval_reason === "health";
  const stale = isStale(g, now, setting(state, "STALE_COMMENT_SEC"));
  const card = state.session?.pd_card;
  const onCard = card?.status === "active" && card.ref_id === g.group_id; // D-113: the push reached the host
  // why it waits, in quiet words; for a question that does not wait, its topic
  const quiet = (todo && waitReason(g)) || "";
  useEffect(() => {
    if (focusedGroup === g.group_id) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [focusedGroup, g.group_id]);
  return (
    <li
      ref={ref}
      className={[styles.groupRow, expanded && styles.groupExpanded, sensitive && todo && styles.groupSensitive].filter(Boolean).join(" ")}
      data-testid={`op-group-${g.group_id}`}
      data-status={g.status}
      data-tab={deskTabOf(g, publishedKind)}
      data-sensitive={sensitive || undefined}
      data-on-card={onCard || undefined}
    >
      <button type="button" className={styles.groupHead} onClick={onToggle} aria-expanded={expanded}>
        {expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
        <span className={styles.groupMain}>
          <span className={styles.groupQuestion}>{g.canonical_question}</span>
          <span className={styles.groupMeta}>
            <Chip tone={statusTone(label)} data-testid="op-status-chip" title={onCard ? t("On the host's card") : undefined}>
              {t(label)}
            </Chip>
            <span>{productLabel(catalog, g, t)}</span>
            <span className={styles.dotSep}>·</span>
            <span className={styles.quiet} data-testid="op-reason">{t(quiet)}</span>
            {sensitive && todo && <span className="visually-hidden">{t("Sensitive")}</span>}
          </span>
        </span>
        <span className={styles.groupStats}>
          <span className={styles.askers} title={t("Unique askers")}>
            <Users size={14} aria-hidden />
            <span className="tabular">{g.unique_author_ids.length}</span>
          </span>
          <span className={["tabular", stale ? styles.stale : styles.muted].join(" ")}>{relativeTime(g.first_at, now)}</span>
        </span>
      </button>
      {expanded ? <GroupDetail group={g} /> : <GroupPreview group={g} />}
    </li>
  );
}

const INLINE_ACTIONS = ["approve", "post_suggested", "push"] as const;

/** D-120: a collapsed row shows the proposed reply (or why there is none) and the next action. */
function GroupPreview({ group: g }: { group: QuestionGroup }) {
  const t = useT();
  const { sid, state } = useOperator();
  const act = useAction();
  if (["answered", "rejected", "closed"].includes(g.status)) return null;
  const answer = draftAnswer(state, g);
  const pending = pendingMessages(state).find((m) => m.group_id === g.group_id) ?? null;
  const next = INLINE_ACTIONS.map((k) => groupActions(g, answer, pending).find((a) => a.key === k && a.enabled))
    .find(Boolean);
  const text = answer?.text
    ? answer.text
    : g.status === "composing" || g.status === "new"
      ? t("Drafting a reply…")
      : t("No AI draft for this question.");
  const run = () =>
    next?.key === "approve"
      ? act.run(() => api.approve(sid, g.group_id))
      : next?.key === "post_suggested"
        ? act.run(() => api.postSuggested(sid, g.group_id))
        : act.run(() => api.pushToHost(sid, g.group_id));
  return (
    <div className={styles.groupPreview} data-testid={`op-preview-${g.group_id}`}>
      {/* the whole reply is readable before it can be posted (review of D-127 shots) */}
      <span className={[styles.previewText, !answer?.text && styles.muted, next && next.key !== "push" && styles.previewFull].filter(Boolean).join(" ")}>{text}</span>
      {next && (
        <Button size="sm" variant={next.key === "approve" ? "primary" : "secondary"} disabled={act.busy} onClick={() => void run()}>
          {t(next.label)}
        </Button>
      )}
    </div>
  );
}

function GroupDetail({ group: g }: { group: QuestionGroup }) {
  const t = useT();
  const { sid, state, catalog, now } = useOperator();
  const answer = draftAnswer(state, g);
  const pending = pendingMessages(state).find((m) => m.group_id === g.group_id) ?? null;
  const actions = groupActions(g, answer, pending);
  // The reply is written, edited and posted in one box (ReplyBox): the suggestion is its starting text. Posting it
  // unchanged, editing it and writing one from nothing are the same gesture, so their three buttons are gone.
  const canReply = actions.some((a) => a.key === "write");
  const rowActions = canReply ? actions.filter((a) => !["approve", "edit", "write"].includes(a.key)) : actions;
  const act = useAction();
  const [editor, setEditor] = useState<{ origin: AnswerOrigin; text: string } | null>(null);
  const [sheet, setSheet] = useState<{ passageId: string; quote: string } | null>(null);
  const [assigning, setAssigning] = useState(false);

  const run = (a: GroupAction) => {
    switch (a.key) {
      case "push":
        return act.run(() => api.pushToHost(sid, g.group_id));
      case "recall":
        return act.run(() => api.recall(sid, g.group_id));
      case "approve":
        return act.run(() => api.approve(sid, g.group_id));
      case "post_suggested":
        return act.run(() => api.postSuggested(sid, g.group_id));
      case "reject":
        return act.run(() => api.reject(sid, g.group_id));
      case "edit":
        setEditor({ origin: "operator_edit", text: answer?.text ?? "" });
        return;
      case "write":
        setEditor({ origin: "operator_written", text: "" });
        return;
      case "assign":
        setAssigning((v) => !v);
        return;
    }
  };

  return (
    <div className={styles.groupDetail}>
      <ul className={styles.memberList}>
        {g.member_comment_ids.map((cid) => {
          const c = state.comments[cid];
          if (!c) return null;
          const basis = state.analyses[cid]?.product_basis;
          return (
            <li key={cid}>
              <span className={styles.author}>{c.author_name}</span>
              <span>{c.text}</span>
              <span className={["tabular", styles.muted].join(" ")}>{relativeTime(c.received_at, now)}</span>
              {basis && <Chip>{basis}</Chip>}
              <CommentTranslation comment={c} />
            </li>
          );
        })}
      </ul>

      <div className={styles.reply}>
        <span className="eyebrow">{canReply ? t("Reply") : t("Suggested reply")}</span>
        {canReply && (
          <ReplyBox group={g} answer={answer} busy={Boolean(pending)} composing={g.status === "composing" || g.status === "new"} />
        )}
        {answer && answer.text ? (
          <>
            {!canReply && <p className={styles.replyText}>{answer.text}</p>}
            {answer.citations.length > 0 && (
              <div className={styles.citations}>
                {answer.citations.map((c, i) => (
                  <button
                    key={`${c.passage_id}-${i}`}
                    type="button"
                    className={styles.citationChip}
                    onClick={() => setSheet({ passageId: c.passage_id, quote: c.quote })}
                  >
                    <FileText size={12} aria-hidden />
                    {citationLabel(c.section ?? catalog?.passages?.[c.passage_id]?.section, t)}
                  </button>
                ))}
              </div>
            )}
            <p className={answer.verified ? styles.verified : styles.unverified}>
              {answer.verified
                ? t("Verified against the product sheet")
                : unverifiedNote(answer.verify_errors, true, t)}
            </p>
          </>
        ) : (
          <p className={styles.muted}>
            {g.status === "composing" || g.status === "new"
              ? t("Composing…")
              : answer && !answer.verified
                ? unverifiedNote(answer.verify_errors, false, t)
                : t("No AI draft for this question.")}
          </p>
        )}
      </div>

      {pending && (
        <div className={styles.pendingPost} role="status">
          <span>{t("Posting answer…")}</span>
          <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.cancelMessage(sid, pending.message_id))}>
            {t("Cancel")}
          </Button>
        </div>
      )}

      {rowActions.length > 0 && (
        <div className={styles.actions}>
          {rowActions.map((a) => (
            <Button
              key={a.key}
              size="sm"
              variant={a.key === "approve" ? "primary" : a.key === "reject" ? "ghost" : "secondary"}
              disabled={!a.enabled || act.busy}
              title={a.reason && t(a.reason)}
              onClick={() => void run(a)}
            >
              {t(a.label)}
            </Button>
          ))}
        </div>
      )}

      {assigning && (
        <label className={styles.assign}>
          <span className={styles.muted}>{t("Assign a product")}</span>
          <select
            defaultValue=""
            onChange={async (e) => {
              const pid = e.target.value;
              if (pid && (await act.run(() => api.assignProduct(sid, g.group_id, pid)))) setAssigning(false);
            }}
          >
            <option value="" disabled>
              {t("Choose…")}
            </option>
            {catalog?.products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {editor && (
        <ReplyEditor
          group={g}
          origin={editor.origin}
          initial={editor.text}
          onDone={() => setEditor(null)}
        />
      )}
      {act.error && <p className={styles.error}>{act.error}</p>}
      {sheet && <CitationSheet passageId={sheet.passageId} quote={sheet.quote} onClose={() => setSheet(null)} />}
    </div>
  );
}

/** The operator's reply, in place: it starts as the suggested reply and can be posted as it is, edited, or written
 * from nothing. Unchanged and verified, it is approved as the suggestion; anything else is posted as the operator's
 * own text. Ctrl+Enter posts. While the operator has not typed, a suggestion that arrives later fills the box. */
export function ReplyBox({ group: g, answer, busy, composing }: {
  group: QuestionGroup;
  answer: Answer | null;
  busy: boolean;
  composing: boolean;
}) {
  const t = useT();
  const { sid } = useOperator();
  const act = useAction();
  const suggestion = answer?.text ?? "";
  // nothing in the product information answers it: the standard reply is the starting text, never a made-up answer
  const noSource = !composing && !suggestion.trim();
  const start = noSource ? NO_SOURCE_REPLY : suggestion;
  const [text, setText] = useState(start);
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!touched) setText(start);
  }, [start, touched]);
  const edited = text.trim() !== start.trim();
  const asSuggested = !edited && Boolean(answer?.verified);
  const post = () =>
    act.run(() =>
      asSuggested
        ? api.approve(sid, g.group_id)
        : api.answer(sid, g.group_id, text.trim(), suggestion ? "operator_edit" : "operator_written"),
    );
  const disabled = act.busy || busy || !text.trim();
  return (
    <div className={styles.editor} data-testid={`op-reply-${g.group_id}`}>
      {noSource && (
        <p className={styles.unverified} data-testid={`op-no-source-${g.group_id}`}>
          {t("No source: the product information does not answer this, so no answer was suggested. The standard reply is filled in; edit it if you know more. Viewers do not see this note.")}
        </p>
      )}
      <textarea
        className={styles.textarea}
        rows={3}
        value={text}
        aria-label={t("Reply")}
        placeholder={composing ? t("A suggestion is being written. You can type your own reply now.") : t("Write a reply…")}
        onChange={(e) => {
          setText(e.target.value);
          setTouched(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !disabled) void post();
        }}
      />
      {act.error && <p className={styles.error}>{act.error}</p>}
      <div className={styles.actions}>
        <Button variant="primary" className={styles.postBtn} disabled={disabled} title={t("Post (Ctrl+Enter)")} onClick={() => void post()}>
          {t("Post")}
        </Button>
        {edited && start && (
          <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => { setText(start); setTouched(false); act.clear(); }}>
            {noSource ? t("Back to the standard reply") : t("Back to the suggestion")}
          </Button>
        )}
        <span className={styles.muted}>
          {!text.trim()
            ? ""
            : noSource && !edited
              ? t("Posts the standard reply: it states no product fact")
              : asSuggested
              ? t("Posts the suggested reply as it is")
              : edited && suggestion
                ? t("Edited: posts as it is, not checked")
                : suggestion
                  ? t("Not verified: posts as it is, not checked")
                  : t("Your own reply: posts as it is, not checked")}
        </span>
      </div>
    </div>
  );
}

/** Inline editor (§12.4.7): posts the operator's text as it is. */
export function ReplyEditor({
  group: g,
  origin,
  initial,
  onDone,
}: {
  group: QuestionGroup;
  origin: AnswerOrigin;
  initial: string;
  onDone: () => void;
}) {
  const t = useT();
  const { sid } = useOperator();
  const [text, setText] = useState(initial);
  const act = useAction();
  const post = async () => {
    if (await act.run(() => api.answer(sid, g.group_id, text.trim(), origin))) onDone();
  };
  return (
    <div className={styles.editor}>
      <textarea
        className={styles.textarea}
        rows={3}
        value={text}
        autoFocus
        aria-label={origin === "operator_edit" ? t("Edit reply") : t("Write reply")}
        onChange={(e) => setText(e.target.value)}
      />
      {act.error && <p className={styles.error}>{act.error}</p>}
      <div className={styles.actions}>
        <Button size="sm" variant="primary" disabled={act.busy || !text.trim()} onClick={() => void post()}>
          {t("Post")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          {t("Cancel")}
        </Button>
      </div>
    </div>
  );
}
