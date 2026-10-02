// Formatting for the summary page. Numbers are shown as computed by the backend (§8.14).

/** 203 -> "3:23"; 3725 -> "1:02:05". */
export function formatDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || !Number.isFinite(sec)) return "–";
  const s = Math.max(0, Math.round(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? `${h}:` : ""}${mm}:${String(r).padStart(2, "0")}`;
}

/** Milliseconds as seconds with one decimal: 1640 -> "1.6 s". */
export function formatMsAsSeconds(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "–";
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Offset of `at` from the broadcast start, "m:ss". */
export function formatOffset(at: number | null | undefined, start: number | null | undefined): string {
  if (at === null || at === undefined || start === null || start === undefined) return "–";
  return formatDuration((at - start) / 1000);
}

export function formatDate(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "Not started";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(ms));
}

export function correctedIn(v: number | "dismissed" | "uncorrected"): string {
  if (v === "dismissed") return "Dismissed";
  if (v === "uncorrected") return "Not corrected";
  return formatMsAsSeconds(v);
}

const AGENT_LABELS: Record<string, string> = {
  compliance_judge: "Compliance judge",
  context_judge: "Context judge",
  utterance_judge: "Utterance judge",
  judge_single: "Judge (single)",
  fact_checker: "Fact checker",
  comment_triage: "Comment triage",
  answer_composer: "Answer composer",
  brief_agent: "Brief agent",
  broadcast_summary: "Broadcast summary",
};

export function agentLabel(name: string): string {
  return AGENT_LABELS[name] ?? name;
}

export function fieldLabel(field: string | null): string {
  if (!field) return "Fact";
  const s = field.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
