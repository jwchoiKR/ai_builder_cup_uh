// Judge test drive (D-238): one button. A fictional sample product's documents are read, approved with one click,
// and a short scene plays on its show in the Studio (risky line and correction, comment burst answered with a
// citation, a spoken answer, a viewer's purchase), then the show ends.
import { useEffect, useState } from "react";

import { request } from "../app/api";
import { navigate } from "../app/nav";
import { Button, Chip, Eyebrow, HubLink } from "../components";
import { onboardingApi, type Job } from "./onboarding/onboardingApi";
import styles from "./onboarding/onboarding.module.css";

type Start = { job_id: string; status: string; files: string[]; cached: boolean };

export function TestDrive() {
  const [start, setStart] = useState<Start | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!start || job?.status === "done" || job?.status === "failed") return;
    const t = window.setTimeout(() => onboardingApi.job(start.job_id).then(setJob, (e) => setError(String(e))),
      job ? 1500 : 300);
    return () => window.clearTimeout(t);
  }, [start, job]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const rec = job?.status === "done" ? job.result?.record ?? null : null;
  const live = rec?.variants.flatMap((v) => v.prices.filter((m) => m.kind === "live").map((m) => `${v.name} ${m.currency} ${(m.minor / 100).toFixed(2)}`)) ?? [];

  return (
    <div className={styles.page} data-testid="testdrive">
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · TEST DRIVE
        </Eyebrow>
        <h1 className={styles.title}>Try it with a sample product</h1>
        <p className={styles.muted}>
          A fictional brand's documents (a spec sheet, two price lists that disagree, a label photo) are read by the AI,
          you approve them in one click, and a 75-second live show plays: a risky claim and its correction, a burst of
          questions answered with their source, a spoken answer, a viewer's purchase.
        </p>
      </header>

      {!start && (
        <section className={styles.block}>
          <Button variant="primary" disabled={busy} data-testid="testdrive-start"
                  onClick={() => run(async () => setStart(await request<Start>("POST", "/testdrive/start", {})))}>
            Start the test drive
          </Button>
        </section>
      )}

      {start && !rec && (
        <section className={styles.block} data-testid="testdrive-reading">
          <h2 className={styles.blockTitle}>1. Reading {start.files.length} documents</h2>
          <ul className={styles.rows}>{start.files.map((f) => <li key={f} className={styles.muted}>{f}</li>)}</ul>
          <p className={styles.status}>
            {job?.status === "failed" ? `Failed: ${job.error}` : start.cached ? "Read before: loading…" : "About 2 minutes…"}
          </p>
        </section>
      )}

      {rec && job && (
        <section className={styles.block} data-testid="testdrive-approve">
          <h2 className={styles.blockTitle}>2. Approve what the AI read</h2>
          <p className={styles.product}>{rec.brand} · {rec.product_name}</p>
          <div className={styles.chips}>
            <Chip>{rec.category}</Chip>
            {live.map((x) => <Chip key={x}>{x} live</Chip>)}
            <Chip>{rec.cautions.length} cautions</Chip>
            <Chip>{rec.approved_claims.length} approved claims</Chip>
            <Chip tone={rec.conflicts.length ? "risk" : undefined}>
              {rec.conflicts.length} price conflicts · newest used
            </Chip>
          </div>
          <Button variant="primary" disabled={busy} data-testid="testdrive-go"
                  onClick={() => run(async () => {
                    const r = await request<{ session_id: string }>("POST", `/testdrive/${encodeURIComponent(job.job_id)}/go`, {});
                    navigate(`/studio?session=${encodeURIComponent(r.session_id)}`);
                  })}>
            Approve and start the show
          </Button>
          <a className={styles.muted} href="/onboarding">Review every field instead →</a>
        </section>
      )}

      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}

export default TestDrive;
