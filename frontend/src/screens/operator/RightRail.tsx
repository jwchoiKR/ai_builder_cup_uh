// Right rail (§12.4.9): live transcript, host cue, banners & notices, quick replies, alert log, agent calls.
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { useState } from "react";

import { api } from "../../app/api";
import { alertLog, formatMmSs, onAirProduct, recentTranscripts, runsheetOf } from "../../app/selectors";
import { Button, Chip } from "../../components";
import { useAction, useOperator } from "./context";
import { alertLatencyMs, alertOutcome, fieldLabel, fillProductName, seconds1, sentenceCase, transcriptChips } from "./model";
import styles from "./operator.module.css";

export function RightRail() {
  return (
    <>
      <LiveTranscript />
      <HostCuePanel />
      <BannersPanel />
      <QuickReplies />
      <AlertLogPanel />
      <AgentCalls />
    </>
  );
}

function LiveTranscript() {
  const { state, catalog } = useOperator();
  const lines = recentTranscripts(state, 20);
  return (
    <section className={styles.block} data-testid="op-transcript" aria-label="Live transcript">
      <h2 className={styles.blockTitle}>Live transcript</h2>
      {state.interim && <p className={styles.interim}>{state.interim.text}</p>}
      {lines.length === 0 && !state.interim ? (
        <p className={styles.empty}>Waiting for the host.</p>
      ) : (
        <ol className={styles.transcriptList}>
          {lines.map((t) => (
            <li key={t.transcript_id} data-testid={`op-transcript-${t.transcript_id}`}>
              <p>{t.text}</p>
              <div className={styles.commentChips}>
                {transcriptChips(state, catalog, t).map((c, i) => (
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
  const { sid, state, catalog } = useOperator();
  const [text, setText] = useState("");
  const act = useAction();
  const cue = state.session?.cue;
  const presets = catalog?.notices?.host_cue_presets ?? [];
  return (
    <section className={styles.block} data-testid="op-cue" aria-label="Host cue">
      <h2 className={styles.blockTitle}>Host cue</h2>
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
        <input className={styles.input} value={text} maxLength={200} placeholder="Cue for the host" aria-label="Cue text" onChange={(e) => setText(e.target.value)} />
        <Button size="sm" type="submit" variant="primary" disabled={act.busy || !text.trim()}>
          Send
        </Button>
      </form>
      {cue && cue.status !== "cleared" && (
        <div className={styles.currentCue}>
          <Chip tone={cue.status === "done" ? "ok" : "accent"}>{cue.status === "done" ? "Done" : "Active"}</Chip>
          <span>{cue.text}</span>
          <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => act.run(() => api.clearCue(sid, cue.cue_id))}>
            Clear
          </Button>
        </div>
      )}
      {act.error && <p className={styles.error}>{act.error}</p>}
    </section>
  );
}

function BannersPanel() {
  const { sid, state, catalog, now } = useOperator();
  const [notice, setNotice] = useState("");
  const act = useAction();
  const rs = runsheetOf(state, catalog);
  const promos = (catalog?.promos ?? []).filter((p) => !rs || rs.promo_ids.includes(p.promo_id));
  const active = new Map((state.session?.active_promos ?? []).map((a) => [a.promo_id, a]));
  const live = state.session?.status === "live";
  const pinned = state.session?.pinned_notice;
  return (
    <section className={styles.block} data-testid="op-promos" aria-label="Banners & notices">
      <h2 className={styles.blockTitle}>Banners &amp; notices</h2>
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
                    Stop
                  </Button>
                </>
              ) : (
                <Button size="sm" disabled={act.busy || !live} onClick={() => act.run(() => api.startPromo(sid, p.promo_id))}>
                  Start
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
        <input className={styles.input} value={notice} maxLength={300} placeholder="Pinned notice for viewers" aria-label="Pinned notice" onChange={(e) => setNotice(e.target.value)} />
        <Button size="sm" type="submit" disabled={act.busy || !notice.trim()}>
          Pin
        </Button>
      </form>
      {pinned && (
        <div className={styles.currentCue}>
          <Chip tone="accent">Pinned</Chip>
          <span>{pinned}</span>
          <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => act.run(() => api.unpinNotice(sid))}>
            Unpin
          </Button>
        </div>
      )}
      {act.error && <p className={styles.error}>{act.error}</p>}
    </section>
  );
}

function QuickReplies() {
  const { state, catalog } = useOperator();
  const [copied, setCopied] = useState<string | null>(null);
  const product = onAirProduct(state, catalog);
  const replies = catalog?.notices?.operator_quick_replies ?? [];
  return (
    <section className={styles.block} aria-label="Quick replies">
      <h2 className={styles.blockTitle}>Quick replies</h2>
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
                {copied === r.reply_id ? "Copied" : "Copy"}
              </Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function AlertLogPanel() {
  const { state, catalog } = useOperator();
  const log = alertLog(state);
  const start = state.session?.started_at ?? 0;
  return (
    <section className={styles.block} data-testid="op-alert-log" aria-label="Alert log">
      <h2 className={styles.blockTitle}>Alert log</h2>
      {log.length === 0 ? (
        <p className={styles.empty}>No alerts yet.</p>
      ) : (
        <ul className={styles.logList}>
          {log.map((a) => {
            const lat = alertLatencyMs(a, state.transcripts);
            return (
              <li key={a.alert_id}>
                <span className={["tabular", styles.muted].join(" ")}>{formatMmSs((a.shown_at ?? a.created_at) - start)}</span>
                <Chip tone={a.kind === "compliance" ? "risk" : "fact"}>
                  {a.kind === "compliance" ? a.rule_id : `${sentenceCase(fieldLabel(catalog, a.field))}`}
                </Chip>
                <span className={styles.logText}>
                  {a.kind === "compliance" ? `“${a.span}”` : `${a.stated_value} → ${a.correct_value}`}
                </span>
                <span className={styles.muted}>
                  {alertOutcome(a)}
                  {lat !== null ? ` · shown ${seconds1(lat)} s after speech` : ""}
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
  const { state } = useOperator();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section className={styles.block} aria-label="Agent calls">
      <button type="button" className={styles.collapse} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <span className={styles.blockTitle}>Agent calls</span>
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
