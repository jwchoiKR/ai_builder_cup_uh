// Operator header (§12.4.1): title, metric chips, LIVE timer, Start/End broadcast, settings gear (D-109).
import { useState } from "react";

import { api } from "../../app/api";
import { translate, useT, type Translate } from "../../app/i18n";
import { formatClock, runsheetOf } from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ThemePref } from "../../app/theme";
import { Button, Chip, ConnectionLabel, Eyebrow, SettingsButton, StatusDot } from "../../components";
import { useAction, useOperator } from "./context";
import { ConfirmDialog } from "./Dialogs";
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
  const [confirmEnd, setConfirmEnd] = useState(false);
  const start = useAction();
  const s = state.session;
  const rs = runsheetOf(state, catalog);
  const brand = catalog?.brand ?? rs?.brand ?? "";
  const title = rs?.title ?? s?.title ?? "";
  const subtitle = brand && !title.startsWith(brand) ? `${brand} · ${title}` : title;
  const chips = metricChips(state.metrics, t);
  const shown = latencyShown(state.metrics);

  return (
    <header className={styles.header} data-testid="op-header">
      <div className={styles.headerTitle}>
        <Eyebrow>{t("BROADCAST WORKSPACE")}</Eyebrow>
        <h1 className={styles.title}>{t("Live control room")}</h1>
        <span className={styles.subtitle}>{subtitle}</span>
      </div>
      <div className={styles.headerRight}>
        {state.market?.tier === "preview" && (
          <Chip tone="fact" data-testid="op-preview">
            {t("PREVIEW")} · {state.market.name}
          </Chip>
        )}
        <div className={styles.metricChips} data-testid="op-metrics">
          {shown.alert && <Chip className="tabular">{chips.alert}</Chip>}
          {shown.judge && <Chip className="tabular">{chips.judge}</Chip>}
          <Chip className="tabular">{chips.instant}</Chip>
        </div>
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
