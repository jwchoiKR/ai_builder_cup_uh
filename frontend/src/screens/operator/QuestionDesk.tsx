// Question desk (§12.4.7): grouped questions sorted by status bucket then score, with actions.
import { ChevronDown, ChevronRight, FileText, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, type AnswerOrigin } from "../../app/api";
import { useT } from "../../app/i18n";
import { deskTabOf, draftAnswer, groupStatusLabel, pendingMessages, questionDesk, relativeTime, type DeskTab } from "../../app/selectors";
import type { QuestionGroup } from "../../app/types";
import { Button, Chip } from "../../components";
import { useAction, useOperator } from "./context";
import { CitationSheet } from "./Dialogs";
import {
  citationLabel,
  deskTabCounts,
  groupActions,
  intentInfo,
  intentLabel,
  isStale,
  productLabel,
  setting,
  statusTone,
  type GroupAction,
} from "./model";
import styles from "./operator.module.css";

// §12.4.7 tabs. "Composing" is added only while a group is composing, so every group always has
// exactly one tab and the tab counts add up to All.
const TABS: { key: DeskTab; label: string; onlyWhenUsed?: boolean }[] = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "on_host", label: "On host" },
  { key: "ready", label: "Ready" },
  { key: "composing", label: "Composing", onlyWhenUsed: true },
  { key: "answered", label: "Answered" },
  { key: "closed", label: "Closed" },
];

export function QuestionDesk() {
  const t = useT();
  const { state, focusedGroup } = useOperator();
  const [tab, setTab] = useState<DeskTab>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const all = Object.values(state.groups);
  const counts = deskTabCounts(all);
  const groups = questionDesk(state, tab);
  const topN = setting(state, "HOST_TOP_N");
  const tabs = TABS.filter((x) => !x.onlyWhenUsed || counts[x.key] > 0 || tab === x.key);

  useEffect(() => {
    if (!focusedGroup) return;
    setTab("all");
    setExpanded(focusedGroup);
  }, [focusedGroup]);

  return (
    <section className={[styles.block, styles.desk].join(" ")} data-testid="op-question-desk" aria-label={t("Question desk")}>
      <div className={styles.blockHeader}>
        <div>
          <h2 className={styles.blockTitle}>
            {t("Question desk")} <span className="tabular" data-testid="op-desk-count">{counts.all}</span>
          </h2>
          <p className={styles.muted}>{t("Grouped by intent, ready for your next move.")}</p>
        </div>
        <span className={["tabular", styles.muted].join(" ")}>
          {t("{n}/{max} on host", { n: state.hostSlots.length, max: topN })}
        </span>
      </div>
      <div className={styles.tabs} role="tablist">
        {tabs.map((x) => (
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
          </button>
        ))}
      </div>
      {groups.length === 0 ? (
        <p className={styles.empty}>{t("No questions here yet.")}</p>
      ) : (
        <ul className={styles.groupList}>
          {groups.map((g) => (
            <GroupRow
              key={g.group_id}
              group={g}
              expanded={expanded === g.group_id}
              onToggle={() => setExpanded((e) => (e === g.group_id ? null : g.group_id))}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function GroupRow({ group: g, expanded, onToggle }: { group: QuestionGroup; expanded: boolean; onToggle: () => void }) {
  const t = useT();
  const { state, catalog, now, focusedGroup } = useOperator();
  const ref = useRef<HTMLLIElement>(null);
  const label = groupStatusLabel(g);
  const sensitive = intentInfo(catalog, g.intent)?.sensitive;
  const stale = isStale(g, now, setting(state, "STALE_COMMENT_SEC"));
  const card = state.session?.pd_card;
  const onCard = card?.status === "active" && card.ref_id === g.group_id; // D-113: the push reached the host
  useEffect(() => {
    if (focusedGroup === g.group_id) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [focusedGroup, g.group_id]);
  return (
    <li
      ref={ref}
      className={[styles.groupRow, expanded && styles.groupExpanded].filter(Boolean).join(" ")}
      data-testid={`op-group-${g.group_id}`}
      data-status={g.status}
      data-tab={deskTabOf(g)}
    >
      <button type="button" className={styles.groupHead} onClick={onToggle} aria-expanded={expanded}>
        {expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
        <span className={styles.groupMain}>
          <span className={styles.groupQuestion}>{g.canonical_question}</span>
          <span className={styles.groupMeta}>
            <Chip tone={statusTone(label)}>{t(label)}</Chip>
            <span>{productLabel(catalog, g, t)}</span>
            <span className={styles.dotSep}>·</span>
            <span>{t(intentLabel(g.intent))}</span>
            {sensitive && <Chip tone="risk">{t("Sensitive")}</Chip>}
            {onCard && (
              <Chip tone="ok" data-testid="op-on-host-card">
                {t("On the host's card")}
              </Chip>
            )}
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
            </li>
          );
        })}
      </ul>

      <div className={styles.reply}>
        <span className="eyebrow">{t("Suggested reply")}</span>
        {answer && answer.text ? (
          <>
            <p className={styles.replyText}>{answer.text}</p>
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
                : t("Unverified draft: {errors}", { errors: answer.verify_errors.join("; ") })}
            </p>
          </>
        ) : (
          <p className={styles.muted}>
            {g.status === "composing" || g.status === "new"
              ? t("Composing…")
              : answer && !answer.verified
                ? t("Unverified draft: {errors}", { errors: answer.verify_errors.join("; ") })
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

      {actions.length > 0 && (
        <div className={styles.actions}>
          {actions.map((a) => (
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

/** Inline editor; a restricted phrase needs "Post anyway" (§12.4.7, §8.13). */
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
  // D-205: a restricted phrase or a reply that could not be verified needs an explicit "Post anyway"
  const restricted = act.errorCode === "restricted_phrase" || act.errorCode === "unverified_reply";
  const post = async (confirm: boolean) => {
    if (await act.run(() => api.answer(sid, g.group_id, text.trim(), origin, confirm))) onDone();
  };
  return (
    <div className={styles.editor}>
      <textarea
        className={styles.textarea}
        rows={3}
        value={text}
        autoFocus
        aria-label={origin === "operator_edit" ? t("Edit reply") : t("Write reply")}
        onChange={(e) => {
          setText(e.target.value);
          if (restricted) act.clear();
        }}
      />
      {restricted ? (
        <div className={styles.restricted} role="alert">
          <span>{act.error}</span>
          <Button size="sm" variant="danger" disabled={act.busy} onClick={() => void post(true)}>
            {t("Post anyway")}
          </Button>
        </div>
      ) : (
        act.error && <p className={styles.error}>{act.error}</p>
      )}
      <div className={styles.actions}>
        <Button size="sm" variant="primary" disabled={act.busy || !text.trim()} onClick={() => void post(false)}>
          {t("Post")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          {t("Cancel")}
        </Button>
      </div>
    </div>
  );
}
