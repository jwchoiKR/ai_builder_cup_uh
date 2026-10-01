// Operator header (§12.4.1): title, metric chips, LIVE timer, Start/End broadcast, theme toggle.
import { useState } from "react";

import { api } from "../../app/api";
import { formatClock, runsheetOf } from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ThemeName } from "../../app/theme";
import { Button, Chip, ConnectionLabel, Eyebrow, StatusDot, ThemeToggle } from "../../components";
import { useAction, useOperator } from "./context";
import { ConfirmDialog } from "./Dialogs";
import styles from "./operator.module.css";

const NO_VALUE = "–";

/** A measured value, or null when there is none (missing, null, NaN, not a number). */
function measured(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Header chips (§8.16). Anything not measured yet shows "–", never "0.0s". */
export function metricChips(metrics: Record<string, unknown> & { header?: { alert_in_s?: number | null; judge_p50_s?: number | null; instant_answers?: number; answers_total?: number } }) {
  const h = metrics?.header;
  const alertIn = measured(h?.alert_in_s);
  const judge = measured(h?.judge_p50_s);
  const instant = measured(h?.instant_answers ?? metrics?.instant_answers);
  const composed = measured(metrics?.composed_answers);
  const total = measured(h?.answers_total) ?? (instant !== null ? instant + (composed ?? 0) : null);
  return {
    alert: `Alert in ${alertIn === null ? NO_VALUE : `${alertIn.toFixed(1)}s`}`,
    judge: `Judge p50 ${judge === null ? NO_VALUE : `${judge.toFixed(1)}s`}`,
    instant: `Instant answers ${instant === null || !total ? NO_VALUE : `${instant}/${total}`}`,
  };
}

export function OperatorHeader({
  connection,
  theme,
  onToggleTheme,
  showThemeToggle,
}: {
  connection: ConnectionStatus;
  theme: ThemeName;
  onToggleTheme: () => void;
  showThemeToggle: boolean;
}) {
  const { sid, state, catalog, now } = useOperator();
  const [confirmEnd, setConfirmEnd] = useState(false);
  const start = useAction();
  const s = state.session;
  const rs = runsheetOf(state, catalog);
  const brand = catalog?.brand ?? rs?.brand ?? "";
  const title = rs?.title ?? s?.title ?? "";
  const subtitle = brand && !title.startsWith(brand) ? `${brand} · ${title}` : title;
  const chips = metricChips(state.metrics);

  return (
    <header className={styles.header} data-testid="op-header">
      <div className={styles.headerTitle}>
        <Eyebrow>BROADCAST WORKSPACE</Eyebrow>
        <h1 className={styles.title}>Live control room</h1>
        <span className={styles.subtitle}>{subtitle}</span>
      </div>
      <div className={styles.headerRight}>
        <div className={styles.metricChips} data-testid="op-metrics">
          <Chip className="tabular">{chips.alert}</Chip>
          <Chip className="tabular">{chips.judge}</Chip>
          <Chip className="tabular">{chips.instant}</Chip>
        </div>
        {s?.status === "live" && s.started_at !== null ? (
          <span className={styles.live}>
            <StatusDot tone="live" pulse />
            LIVE <span className="tabular">{formatClock(now - s.started_at)}</span>
          </span>
        ) : (
          <span className={styles.ready}>{s?.status === "ended" ? "ENDED" : "READY"}</span>
        )}
        {connection !== "connected" && <ConnectionLabel status={connection} />}
        {s?.status === "ready" && (
          <Button variant="primary" disabled={start.busy} onClick={() => start.run(() => api.start(sid))}>
            Start broadcast
          </Button>
        )}
        {s?.status === "live" && (
          <Button variant="danger" onClick={() => setConfirmEnd(true)}>
            End broadcast
          </Button>
        )}
        {s?.status === "ended" && (
          <a className={styles.linkButton} href={`/summary?session=${encodeURIComponent(sid)}`}>
            Open summary
          </a>
        )}
        {showThemeToggle && <ThemeToggle theme={theme} onToggle={onToggleTheme} />}
      </div>
      {start.error && <p className={styles.error}>{start.error}</p>}
      {confirmEnd && (
        <ConfirmDialog
          title="End broadcast"
          text="End the broadcast? This stops the feed and creates the summary."
          confirmLabel="End broadcast"
          danger
          onConfirm={() => api.end(sid)}
          onClose={() => setConfirmEnd(false)}
        />
      )}
    </header>
  );
}
