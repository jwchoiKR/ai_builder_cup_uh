// Post-broadcast summary (DEV_SPEC §12.8): numbers computed by the backend (§8.14) and the AI recap (§7.8).
import { useCallback, useEffect, useState } from "react";

import { api } from "../app/api";
import { navigate, withSession, type ScreenProps } from "../app/nav";
import { useTheme } from "../app/theme";
import { exportSummaryJson } from "./summary/exportJson";
import { printSummary } from "./summary/exportPdf";
import { SummaryView } from "./summary/SummaryView";
import type { SummaryData } from "./summary/types";
import styles from "./summary/summary.module.css";

const POLL_COMPUTING_MS = 2000;
const POLL_LIVE_MS = 5000;

export function Summary({ sessionId, theme: forcedTheme, embedded }: ScreenProps) {
  const [ownTheme, toggle] = useTheme("summary");
  const theme = forcedTheme ?? ownTheme;
  const [data, setData] = useState<SummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  // D-097: render the light theme, then open the print dialog ("Save as PDF").
  useEffect(() => {
    if (!printing || !data) return;
    const id = window.setTimeout(() => {
      printSummary(data);
      setPrinting(false);
    }, 50);
    return () => window.clearTimeout(id);
  }, [printing, data]);

  const load = useCallback(async () => {
    if (!sessionId) return;
    try {
      setData((await api.summary(sessionId)) as unknown as SummaryData);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while the recap is being written (and every few seconds while still live).
  useEffect(() => {
    if (!data || (data.status !== "computing" && data.status !== "not_ended")) return;
    const id = window.setTimeout(() => void load(), data.status === "computing" ? POLL_COMPUTING_MS : POLL_LIVE_MS);
    return () => window.clearTimeout(id);
  }, [data, load]);

  if (!data) {
    return (
      <div className={styles.root} data-theme={theme}>
        <p className={styles.muted}>{error ? `Summary unavailable: ${error}` : "Loading the summary…"}</p>
      </div>
    );
  }
  return (
    <SummaryView
      data={data}
      theme={printing ? "light" : theme}
      embedded={embedded}
      onToggleTheme={forcedTheme ? undefined : toggle}
      onExport={() => exportSummaryJson(data)}
      onExportPdf={() => setPrinting(true)}
      onBack={() => navigate(withSession("/", sessionId))}
    />
  );
}

export default Summary;
