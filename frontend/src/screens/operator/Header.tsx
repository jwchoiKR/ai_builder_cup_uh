// Operator header (§12.4.1): title, live alerts (stream problem, collecting context), LIVE timer, Start/End broadcast, settings gear (D-109).
import { useState } from "react";

import { api } from "../../app/api";
import { translate, useT, type Translate } from "../../app/i18n";
import { formatClock, runsheetOf } from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ThemePref } from "../../app/theme";
import { Button, Chip, ConnectionLabel, Eyebrow, HubLink, SettingsButton, StatusDot } from "../../components";
import { useAction, useOperator } from "./context";
import { ConfirmDialog } from "./Dialogs";
import { streamIssues } from "./model";
import styles from "./operator.module.css";

const NO_VALUE = "–";

/** A measured value, or null when there is none (missing, null, NaN, not a number). */
function measured(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** D-120: latency chips appear only once a real latency is measured (mock runs report 0, "0.0s"). */
export function latencyShown(metrics: { header?: { alert_in_s?: number | null; judge_p50_s?: number | null } }) {
  const h = metrics?.header;
  const real = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v > 0;
  return { alert: real(h?.alert_in_s), judge: real(h?.judge_p50_s) };
}

/** Header chips (§8.16). Anything not measured yet shows "–", never "0.0s". */
export function metricChips(
  metrics: Record<string, unknown> & { header?: { alert_in_s?: number | null; judge_p50_s?: number | null; instant_answers?: number; answers_total?: number } },
  t: Translate = (en, vars) => translate("en", en, vars),
) {
  const h = metrics?.header;
  const alertIn = measured(h?.alert_in_s);
  const judge = measured(h?.judge_p50_s);
  const instant = measured(h?.instant_answers ?? metrics?.instant_answers);
  const composed = measured(metrics?.composed_answers);
  const total = measured(h?.answers_total) ?? (instant !== null ? instant + (composed ?? 0) : null);
  return {
    alert: t("Alert in {v}", { v: alertIn === null ? NO_VALUE : `${alertIn.toFixed(1)}s` }),
    judge: t("Judge p50 {v}", { v: judge === null ? NO_VALUE : `${judge.toFixed(1)}s` }),
    instant: t("Instant answers {v}", { v: instant === null || !total ? NO_VALUE : `${instant}/${total}` }),
  };
}

type Impact = {
  risky_lines: { alerted: number; of_lines: number };
  questions: { ai: number; host: number; operator: number; of_askers: number };
  operator_actions: number;
  llm: { calls: number; tokens: number; tokens_per_hour: number | null };
};

/** D-240: live impact from logged state, each count with its denominator. */
export function impactChips(metrics: { impact?: Impact } | undefined, t: Translate = (en, vars) => translate("en", en, vars)) {
  const i = metrics?.impact;
  if (!i) return [];
  const q = i.questions;
  return [
    t("Risky lines alerted {a}/{n}", { a: String(i.risky_lines.alerted), n: String(i.risky_lines.of_lines) }),
    t("Askers answered: AI {a} · host {h} · operator {o} of {n}",
      { a: String(q.ai), h: String(q.host), o: String(q.operator), n: String(q.of_askers) }),
    t("Operator actions {n}", { n: String(i.operator_actions) }),
    // D-332: no "LLM –k tokens/h" placeholder before the first number
    ...(i.llm.tokens_per_hour === null ? [] : [t("LLM {k}k tokens/h", { k: String(Math.round(i.llm.tokens_per_hour / 1000)) })]),
  ];
}

export function OperatorHeader({
  connection,
  themePref,
  onSetTheme,
  showSettings,
}: {
  connection: ConnectionStatus;
  themePref: ThemePref;
  onSetTheme: (t: ThemePref) => void;
  showSettings: boolean;
}) {
  const t = useT();
  const { sid, state, catalog, now } = useOperator();
  const issues = streamIssues(state.comments, now);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const start = useAction();
  const s = state.session;
  const rs = runsheetOf(state, catalog);
  const brand = catalog?.brand ?? rs?.brand ?? "";
  const title = rs?.title ?? s?.title ?? "";
  const subtitle = brand && !title.startsWith(brand) ? `${brand} · ${title}` : title;

  return (
    <header className={styles.header} data-testid="op-header">
      <div className={styles.headerTitle}>
        <Eyebrow>
          {showSettings && (
            // back to the Hub (not in a Studio pane); during a live show it asks first
            <>
              <HubLink sessionId={sid} live={s?.status === "live"} /> ·{" "}
            </>
          )}
          {t("BROADCAST WORKSPACE")}
        </Eyebrow>
        <h1 className={styles.title}>{t("Live control room")}</h1>
        <span className={styles.subtitle}>{subtitle}</span>
      </div>
      <div className={styles.headerRight}>
        {state.market?.tier === "preview" && (
          <Chip tone="fact" data-testid="op-preview">
            {t("PREVIEW")} · {state.market.name}
          </Chip>
        )}
        {state.market?.law_checks === false && (
          <Chip tone="risk" data-testid="op-no-law">
            {t("No law checks for this category")} · {state.market.category}
          </Chip>
        )}
        {issues.viewers > 0 && (  // viewers report a stream problem: the team acts, nobody replies in chat
          <Chip tone="risk" data-testid="op-stream-issue"
            title={issues.latest ? `${issues.latest.author_name}: ${issues.latest.translation_en ?? issues.latest.text}` : undefined}>
            {issues.viewers === 1
              ? t("1 viewer reports a stream problem")
              : t("{n} viewers report a stream problem", { n: issues.viewers })}
          </Chip>
        )}
        {Object.keys(state.holds).length > 0 && (  // D-335: a question waits for its answer; operator only
          <Chip tone="accent" data-testid="op-hold">
            {t("Collecting context · up to {s} s", { s: Math.max(...Object.values(state.holds)) / 1000 })}
          </Chip>
        )}
        {s?.status === "live" && s.started_at !== null ? (
          <span className={styles.live}>
            <StatusDot tone="live" pulse />
            {t("LIVE")} <span className="tabular">{formatClock(now - s.started_at)}</span>
          </span>
        ) : (
          <span className={styles.ready}>{s?.status === "ended" ? t("ENDED") : t("READY")}</span>
        )}
        {connection !== "connected" && <ConnectionLabel status={connection} />}
        {s?.status === "ready" && (
          <Button variant="primary" disabled={start.busy} onClick={() => start.run(() => api.start(sid))}>
            {t("Start broadcast")}
          </Button>
        )}
        {s?.status === "live" && (
          <Button variant="danger" onClick={() => setConfirmEnd(true)}>
            {t("End broadcast")}
          </Button>
        )}
        {s?.status === "ended" && (
          <a className={styles.linkButton} href={`/summary?session=${encodeURIComponent(sid)}`}>
            {t("Open summary")}
          </a>
        )}
        {showSettings && <SettingsButton themePref={themePref} onTheme={onSetTheme} />}
      </div>
      {start.error && <p className={styles.error}>{start.error}</p>}
      {confirmEnd && (
        <ConfirmDialog
          title={t("End broadcast")}
          text={t("End the broadcast? This stops the feed and creates the summary.")}
          confirmLabel={t("End broadcast")}
          danger
          onConfirm={() => api.end(sid)}
          onClose={() => setConfirmEnd(false)}
        />
      )}
    </header>
  );
}
