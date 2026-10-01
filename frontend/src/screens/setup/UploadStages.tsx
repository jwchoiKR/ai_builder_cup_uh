// Upload progress (D-093): the stages the backend really runs for this upload, polled while it runs.
import { Check, Circle, Minus, X } from "lucide-react";
import type { ReactNode } from "react";

import type { UploadJob, UploadStage } from "./setupApi";
import styles from "./setup.module.css";

const ICON: Record<UploadStage["status"], ReactNode> = {
  pending: <Circle aria-hidden />,
  running: <span className={styles.spinner} aria-hidden />,
  done: <Check aria-hidden />,
  failed: <X aria-hidden />,
  skipped: <Minus aria-hidden />,
};

const STATUS_TEXT: Record<UploadStage["status"], string> = {
  pending: "Waiting",
  running: "In progress",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

function seconds(s: UploadStage): string | null {
  if (s.status !== "done" || s.started_at == null || s.ended_at == null) return null;
  return `${((s.ended_at - s.started_at) / 1000).toFixed(1)} s`;
}

export function UploadStages({ job }: { job: UploadJob }) {
  const finished = job.stages.filter((s) => s.status === "done" || s.status === "skipped").length;
  const pct = Math.round((100 * finished) / Math.max(1, job.stages.length));
  return (
    <div className={styles.upload} data-testid="setup-upload-progress" data-status={job.status}>
      <div className={styles.uploadHead}>
        <span className={styles.term}>{job.name}</span>
        <span className={styles.meta}>
          {job.status === "running" ? `${pct}%` : job.status === "done" ? "Finished" : "Stopped"}
        </span>
      </div>
      <div
        className={styles.progressTrack}
        role="progressbar"
        aria-label={`Upload of ${job.name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className={job.status === "failed" ? styles.progressFailed : styles.progressFill} style={{ width: `${pct}%` }} />
      </div>
      <ol className={styles.stageList}>
        {job.stages.map((s) => (
          <li key={s.stage_id} className={styles.stage} data-testid={`setup-stage-${s.stage_id}`} data-state={s.status}>
            <span className={styles.stageIcon} title={STATUS_TEXT[s.status]}>
              {ICON[s.status]}
            </span>
            <span className={styles.stageLabel}>{s.label}</span>
            <span className={styles.stageDetail}>
              {s.detail}
              {seconds(s) && <span className="tabular"> · {seconds(s)}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
