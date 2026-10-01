import type { SummaryData } from "./types";

/** Download the summary (statistics and recap) as JSON. */
export function exportSummaryJson(data: SummaryData, doc: Document = document): string {
  const name = `summary-${data.stats.session_id || "session"}.json`;
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = doc.createElement("a");
  a.href = url;
  a.download = name;
  doc.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return name;
}
