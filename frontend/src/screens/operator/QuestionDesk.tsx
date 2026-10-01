// Question desk (§12.4.7): grouped questions sorted by status bucket then score, with actions.
import { ChevronDown, ChevronRight, FileText, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, type AnswerOrigin } from "../../app/api";
import { draftAnswer, groupStatusLabel, pendingMessages, questionDesk, relativeTime, type DeskTab } from "../../app/selectors";
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
  isOpenGroup,
  isStale,
  productLabel,
  setting,
  statusTone,
  type GroupAction,
} from "./model";
import styles from "./operator.module.css";

const TABS: { key: DeskTab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "on_host", label: "On host" },
  { key: "ready", label: "Ready" },
  { key: "answered", label: "Answered" },
  { key: "closed", label: "Closed" },
];

export function QuestionDesk() {
  const { state, focusedGroup } = useOperator();
  const [tab, setTab] = useState<DeskTab>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const all = Object.values(state.groups);
  const counts = deskTabCounts(all);
  const groups = questionDesk(state, tab);
  const topN = setting(state, "HOST_TOP_N");

  useEffect(() => {
    if (!focusedGroup) return;
    setTab("all");
    setExpanded(focusedGroup);
  }, [focusedGroup]);

  return (
    <section className={[styles.block, styles.desk].join(" ")} data-testid="op-question-desk" aria-label="Question desk">
      <div className={styles.blockHeader}>
        <div>
          <h2 className={styles.blockTitle}>
            Question desk <span className="tabular">{all.filter(isOpenGroup).length}</span>
          </h2>
          <p className={styles.muted}>Grouped by intent, ready for your next move.</p>
        </div>
        <span className={["tabular", styles.muted].join(" ")}>
          {state.hostSlots.length}/{topN} on host
        </span>
      </div>
      <div className={styles.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={[styles.tab, tab === t.key && styles.tabActive].filter(Boolean).join(" ")}
            onClick={() => setTab(t.key)}
          >
            {t.label} <span className="tabular">{counts[t.key]}</span>
          </button>
        ))}
      </div>
      {groups.length === 0 ? (
        <p className={styles.empty}>No questions here yet.</p>
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
  const { state, catalog, now, focusedGroup } = useOperator();
  const ref = useRef<HTMLLIElement>(null);
  const label = groupStatusLabel(g);
  const sensitive = intentInfo(catalog, g.intent)?.sensitive;
  const stale = isStale(g, now, setting(state, "STALE_COMMENT_SEC"));
  useEffect(() => {
    if (focusedGroup === g.group_id) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [focusedGroup, g.group_id]);
  return (
    <li ref={ref} className={[styles.groupRow, expanded && styles.groupExpanded].filter(Boolean).join(" ")} data-testid={`op-group-${g.group_id}`} data-status={g.status}>
      <button type="button" className={styles.groupHead} onClick={onToggle} aria-expanded={expanded}>
        {expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
        <span className={styles.groupMain}>
          <span className={styles.groupQuestion}>{g.canonical_question}</span>
          <span className={styles.groupMeta}>
            <Chip tone={statusTone(label)}>{label}</Chip>
            <span>{productLabel(catalog, g)}</span>
            <span className={styles.dotSep}>·</span>
            <span>{intentLabel(g.intent)}</span>
            {sensitive && <Chip tone="risk">Sensitive</Chip>}
          </span>
        </span>
        <span className={styles.groupStats}>
          <span className={styles.askers} title="Unique askers">
            <Users size={14} aria-hidden />
            <span className="tabular">{g.unique_author_ids.length}</span>
          </span>
          <span className={["tabular", stale ? styles.stale : styles.muted].join(" ")}>{relativeTime(g.first_at, now)}</span>
        </span>
      </button>
      {expanded && <GroupDetail group={g} />}
    </li>
  );
}

function GroupDetail({ group: g }: { group: QuestionGroup }) {
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
        <span className="eyebrow">Suggested reply</span>
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
                    {citationLabel(c.section ?? catalog?.passages?.[c.passage_id]?.section)}
                  </button>
                ))}
              </div>
            )}
            <p className={answer.verified ? styles.verified : styles.unverified}>
              {answer.verified ? "Verified against the product sheet" : `Unverified draft: ${answer.verify_errors.join("; ")}`}
            </p>
          </>
        ) : (
          <p className={styles.muted}>
            {g.status === "composing" || g.status === "new"
              ? "Composing…"
              : answer && !answer.verified
                ? `Unverified draft: ${answer.verify_errors.join("; ")}`
                : "No AI draft for this question."}
          </p>
        )}
      </div>

      {pending && (
        <div className={styles.pendingPost} role="status">
          <span>Posting answer…</span>
          <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.cancelMessage(sid, pending.message_id))}>
            Cancel
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
              title={a.reason}
              onClick={() => void run(a)}
            >
              {a.label}
            </Button>
          ))}
        </div>
      )}

      {assigning && (
        <label className={styles.assign}>
          <span className={styles.muted}>Assign a product</span>
          <select
            defaultValue=""
            onChange={async (e) => {
              const pid = e.target.value;
              if (pid && (await act.run(() => api.assignProduct(sid, g.group_id, pid)))) setAssigning(false);
            }}
          >
            <option value="" disabled>
              Choose…
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
  const { sid } = useOperator();
  const [text, setText] = useState(initial);
  const act = useAction();
  const restricted = act.errorCode === "restricted_phrase";
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
        aria-label={origin === "operator_edit" ? "Edit reply" : "Write reply"}
        onChange={(e) => {
          setText(e.target.value);
          if (restricted) act.clear();
        }}
      />
      {restricted ? (
        <div className={styles.restricted} role="alert">
          <span>{act.error}</span>
          <Button size="sm" variant="danger" disabled={act.busy} onClick={() => void post(true)}>
            Post anyway
          </Button>
        </div>
      ) : (
        act.error && <p className={styles.error}>{act.error}</p>
      )}
      <div className={styles.actions}>
        <Button size="sm" variant="primary" disabled={act.busy || !text.trim()} onClick={() => void post(false)}>
          Post
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
