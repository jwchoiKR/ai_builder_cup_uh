// Right rail (§12.4.9): live transcript, host cue, banners & notices, quick replies, alert log, agent calls.
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { useState, type ReactNode } from "react";

import { api } from "../../app/api";
import { useT } from "../../app/i18n";
import { alertLog, clearedTiming, formatMmSs, onAirProduct, recentTranscripts, runsheetOf, shownTiming, timingLabel } from "../../app/selectors";
import { Button, Chip } from "../../components";
import { debugOn, useStoredOpen } from "./attention";
import { useAction, useOperator } from "./context";
import { impactChips, latencyShown, metricChips } from "./Header";
import { alertOutcome, fieldLabel, fillProductName, sentenceCase, transcriptChips } from "./model";
import styles from "./operator.module.css";

// The second job first (what the host says, what was flagged), then what is used during the show, then what is
// occasional: host cue and quick replies stay closed until opened, statistics are one click away, and the agent
// calls are developer information (?debug=1).
export function RightRail() {
  return (
    <>
      <LiveTranscript />
      <AlertLogPanel />
      <BannersPanel />
      <HostCuePanel />
      <QuickReplies />
      <StatsPanel />
      {debugOn() && <AgentCalls />}
    </>
  );
}

/** A section header that opens and closes its body; the choice is remembered per browser. */
function Disclosure({ storageKey, title, testId, children }: { storageKey: string; title: string; testId?: string; children: ReactNode }) {
  const [open, toggle] = useStoredOpen(storageKey);
  return (
    <section className={styles.block} data-testid={testId} aria-label={title}>
      <button type="button" className={styles.collapse} aria-expanded={open} onClick={toggle}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <h2 className={styles.blockTitle}>{title}</h2>
      </button>
      {open && children}
    </section>
  );
}

/** Statistics of the show so far: closed by default, off the header. */
function StatsPanel() {
  const t = useT();
  const { state } = useOperator();
  const [open, setOpen] = useState(false);
  const chips = metricChips(state.metrics, t);
  const shown = latencyShown(state.metrics);
  return (
    <section className={styles.block} data-testid="op-stats" aria-label={t("Stats")}>
      <button type="button" className={styles.collapse} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <span className={styles.blockTitle}>{open ? t("Hide stats") : t("Show stats")}</span>
      </button>
      {open && (
        <>
          <div className={styles.metricChips} data-testid="op-metrics">
            {shown.alert && <Chip className="tabular">{chips.alert}</Chip>}
            {shown.judge && <Chip className="tabular">{chips.judge}</Chip>}
            <Chip className="tabular">{chips.instant}</Chip>
          </div>
          <div className={styles.metricChips} data-testid="op-impact">
            {impactChips(state.metrics as Parameters<typeof impactChips>[0], t).map((x) => (
              <Chip key={x} className="tabular">{x}</Chip>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function LiveTranscript() {
  const tr = useT();
  const { state, catalog } = useOperator();
  const lines = recentTranscripts(state, 20);
  return (
    <section className={styles.block} data-testid="op-transcript" aria-label={tr("Live transcript")}>
      <h2 className={styles.blockTitle}>{tr("Live transcript")}</h2>
      {state.interim && <p className={styles.interim}>{state.interim.text}</p>}
      {lines.length === 0 && !state.interim ? (
        <p className={styles.empty}>{tr("Waiting for the host.")}</p>
      ) : (
        <ol className={styles.transcriptList}>
          {lines.map((t) => (
            <li key={t.transcript_id} data-testid={`op-transcript-${t.transcript_id}`}>
              <p>{t.text}</p>
              <div className={styles.commentChips}>
                {transcriptChips(state, catalog, t, tr).map((c, i) => (
                  <Chip key={i} tone={c.tone}>
                    {c.text}
                  </Chip>
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function HostCuePanel() {
  const t = useT();
  const { sid, state, catalog } = useOperator();
  const [text, setText] = useState("");
  const act = useAction();
  const cue = state.session?.cue;
  const presets = catalog?.notices?.host_cue_presets ?? [];
  return (
    <Disclosure storageKey="ls.op.cue.open" title={t("Host cue")} testId="op-cue">
      <div className={styles.presetRow}>
        {presets.map((p) => (
          <Button key={p.cue_id} size="sm" disabled={act.busy} onClick={() => act.run(() => api.sendCue(sid, { preset_id: p.cue_id }))}>
            {p.label}
          </Button>
        ))}
      </div>
      <form
        className={styles.inlineForm}
        onSubmit={async (e) => {
          e.preventDefault();
          if (text.trim() && (await act.run(() => api.sendCue(sid, { text: text.trim() })))) setText("");
        }}
      >
        <input className={styles.input} value={text} maxLength={200} placeholder={t("Cue for the host")} aria-label={t("Cue text")} onChange={(e) => setText(e.target.value)} />
        <Button size="sm" type="submit" variant="primary" disabled={act.busy || !text.trim()}>
          {t("Send")}
        </Button>
      </form>
      {cue && cue.status !== "cleared" && (
        <div className={styles.currentCue}>
          <Chip tone={cue.status === "done" ? "ok" : "accent"}>{cue.status === "done" ? t("Done") : t("Active")}</Chip>
          <span>{cue.text}</span>
          <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => act.run(() => api.clearCue(sid, cue.cue_id))}>
            {t("Clear")}
          </Button>
        </div>
      )}
      {act.error && <p className={styles.error}>{act.error}</p>}
    </Disclosure>
  );
}

function BannersPanel() {
  const t = useT();
  const { sid, state, catalog, now } = useOperator();
  const [notice, setNotice] = useState("");
  const act = useAction();
  const rs = runsheetOf(state, catalog);
  const promos = (catalog?.promos ?? []).filter((p) => !rs || rs.promo_ids.includes(p.promo_id));
  const active = new Map((state.session?.active_promos ?? []).map((a) => [a.promo_id, a]));
  const live = state.session?.status === "live";
  const pinned = state.session?.pinned_notice;
  return (
    <section className={styles.block} data-testid="op-promos" aria-label={t("Banners & notices")}>
      <h2 className={styles.blockTitle}>{t("Banners & notices")}</h2>
      <ul className={styles.promoList}>
        {promos.map((p) => {
          const a = active.get(p.promo_id);
          return (
            <li key={p.promo_id} data-testid={`op-promo-${p.promo_id}`}>
              <span className={styles.promoTitle}>{p.title}</span>
              {a ? (
                <>
                  <Chip tone="live" className="tabular">
                    {formatMmSs(a.ends_at - now)}
                  </Chip>
                  <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.stopPromo(sid, p.promo_id))}>
                    {t("Stop")}
                  </Button>
                </>
              ) : (
                <Button size="sm" disabled={act.busy || !live} onClick={() => act.run(() => api.startPromo(sid, p.promo_id))}>
                  {t("Start")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <form
        className={styles.inlineForm}
        onSubmit={async (e) => {
          e.preventDefault();
          if (notice.trim() && (await act.run(() => api.pinNotice(sid, notice.trim())))) setNotice("");
        }}
      >
        <input className={styles.input} value={notice} maxLength={300} placeholder={t("Pinned notice for viewers")} aria-label={t("Pinned notice")} onChange={(e) => setNotice(e.target.value)} />
        <Button size="sm" type="submit" disabled={act.busy || !notice.trim()}>
          {t("Pin")}
        </Button>
      </form>
      {pinned && (
        <div className={styles.currentCue}>
          <Chip tone="accent">{t("Pinned")}</Chip>
          <span>{pinned}</span>
          <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => act.run(() => api.unpinNotice(sid))}>
            {t("Unpin")}
          </Button>
        </div>
      )}
      {act.error && <p className={styles.error}>{act.error}</p>}
    </section>
  );
}

function QuickReplies() {
  const t = useT();
  const { state, catalog } = useOperator();
  const [copied, setCopied] = useState<string | null>(null);
  const product = onAirProduct(state, catalog);
  const replies = catalog?.notices?.operator_quick_replies ?? [];
  return (
    <Disclosure storageKey="ls.op.quick.open" title={t("Quick replies")} testId="op-quick">
      <ul className={styles.quickList}>
        {replies.map((r) => {
          const text = fillProductName(r.text, product?.name ?? null);
          return (
            <li key={r.reply_id}>
              <span>{text}</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  try {
                    await navigator.clipboard?.writeText(text);
                    setCopied(r.reply_id);
                  } catch {
                    setCopied(null);
                  }
                }}
              >
                <Copy size={14} aria-hidden />
                {copied === r.reply_id ? t("Copied") : t("Copy")}
              </Button>
            </li>
          );
        })}
      </ul>
    </Disclosure>
  );
}

function AlertLogPanel() {
  const t = useT();
  const { state, catalog } = useOperator();
  const log = alertLog(state);
  const start = state.session?.started_at ?? 0;
  return (
    <section className={styles.block} data-testid="op-alert-log" aria-label={t("Alert log")}>
      <h2 className={styles.blockTitle}>{t("Alert log")}</h2>
      {log.length === 0 ? (
        <p className={styles.empty}>{t("No alerts yet.")}</p>
      ) : (
        <ul className={styles.logList}>
          {log.map((a) => {
            return (
              <li key={a.alert_id}>
                <span className={["tabular", styles.muted].join(" ")}>{formatMmSs((a.shown_at ?? a.created_at) - start)}</span>
                <Chip tone={a.kind === "compliance" ? "risk" : "fact"}>
                  {a.kind === "compliance" ? a.rule_id : `${sentenceCase(t(fieldLabel(catalog, a.field)))}`}
                </Chip>
                <span className={styles.logText}>
                  {a.kind === "compliance" ? `“${a.span}”` : `${a.stated_value} → ${a.correct_value}`}
                </span>
                <span className={styles.muted}>
                  {alertOutcome(a, t)}
                  {[timingLabel("shown", shownTiming(a, state.transcripts), t),
                    timingLabel("cleared", clearedTiming(a, state.transcripts), t)].filter(Boolean)
                    .map((x) => ` · ${x}`).join("")}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function AgentCalls() {
  const t = useT();
  const { state } = useOperator();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section className={styles.block} aria-label={t("Agent calls")}>
      <button type="button" className={styles.collapse} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <span className={styles.blockTitle}>{t("Agent calls")}</span>
        <span className={["tabular", styles.muted].join(" ")}>{state.agentCalls.length}</span>
      </button>
      {open && (
        <ul className={styles.callList}>
          {state.agentCalls.map((c) => (
            <li key={c.call_id}>
              <button type="button" className={styles.callHead} onClick={() => setExpanded((e) => (e === c.call_id ? null : c.call_id))}>
                <span>{c.agent}</span>
                <Chip tone={c.status === "ok" ? "ok" : "risk"}>{c.status}</Chip>
                <span className="tabular">{c.latency_ms} ms</span>
              </button>
              {expanded === c.call_id && (
                <div className={styles.callBody}>
                  <p className={styles.muted}>{c.model} · {c.prompt_version}</p>
                  <p>{c.input_preview}</p>
                  <pre>{c.error ?? JSON.stringify(c.output, null, 1)}</pre>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
