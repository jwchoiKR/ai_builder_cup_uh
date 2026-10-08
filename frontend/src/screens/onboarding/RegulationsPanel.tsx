// D-359: regulations on the onboarding screen. Upload a regulator's documents for a market and a product category,
// watch the read, approve (write-once), see every approved pack with its source files and the sections its rules
// cite, which pack is active, and for each approved product the regulation originals its live judge reads (D-358).
// The source documents are the authority; the extracted rules are not shown as such.
import { useCallback, useEffect, useState } from "react";

import { PDF_ACCEPT, pdfOnly } from "../../app/pdfOnly";
import { Button, Chip } from "../../components";
import { regulationsApi, type LawJob, type Regulations } from "./onboardingApi";
import styles from "./onboarding.module.css";

const STATUS: Record<LawJob["status"], string> = {
  queued: "Queued",
  reading: "Reading the documents… about 1–3 minutes.",
  done: "Read. Review the source files and sections, then approve.",
  failed: "Failed",
};

const day = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function RegulationsPanel() {
  const [reg, setReg] = useState<Regulations | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [market, setMarket] = useState("");
  const [category, setCategory] = useState("");
  const [job, setJob] = useState<LawJob | null>(null);
  const [approved, setApproved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    regulationsApi.list().then((r) => {
      setReg(r);
      setMarket((m) => m || r.market);
      setCategory((c) => c || r.categories[0] || "");
    }, (e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = window.setTimeout(() => {
      regulationsApi.job(job.job_id).then(setJob, (e) => setError(String(e)));
    }, 1500);
    return () => window.clearTimeout(t);
  }, [job]);

  const act = async (fn: () => Promise<void>) => {
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

  const sections = job?.result
    ? [...new Set(job.result.record.rules.flatMap((r) => r.evidence.map((e) => `${e.file} · ${e.locator}`)))].sort()
    : [];

  return (
    <section className={styles.block} data-testid="reg-panel">
      <h2 className={styles.blockTitle}>Regulations</h2>
      <p className={styles.muted}>
        The live compliance judge reads these documents as they are. Upload a regulator's documents (PDF only) for one
        market and one product category.
      </p>

      <div className={styles.inline}>
        <input type="file" multiple accept={PDF_ACCEPT} data-testid="reg-files"
               onChange={(e) => {
                 const pick = pdfOnly(Array.from(e.target.files ?? []));  // D-367 (user): PDF only
                 setError(pick.error);
                 setFiles(pick.files);
                 if (pick.error) e.target.value = "";
               }} />
        <label>
          Market{" "}
          <select value={market} onChange={(e) => setMarket(e.target.value)} data-testid="reg-market">
            {(reg?.markets ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label>
          Category{" "}
          <select value={category} onChange={(e) => setCategory(e.target.value)} data-testid="reg-category"
                  disabled={!reg?.categories.length}>
            {(reg?.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <Button variant="primary" data-testid="reg-read"
                disabled={busy || !files.length || !market || !category}
                onClick={() => act(async () => {
                  setApproved(null);
                  const { job_id } = await regulationsApi.upload(files, market, category);
                  setJob({ job_id, status: "queued", files: files.map((f) => f.name), error: null, result: null });
                })}>
          Read regulation
        </Button>
      </div>
      {!reg?.categories.length && reg && (
        <p className={styles.muted} data-testid="reg-no-categories">
          Categories come from approved products. Approve a product first.
        </p>
      )}
      <p className={styles.muted}>
        A read in progress is kept in the server's memory: it is lost if the server restarts.
      </p>

      {job && (
        <div data-testid="reg-job" data-status={job.status}>
          <p className={job.status === "failed" ? styles.error : styles.status} data-testid="reg-status">
            {STATUS[job.status]}{job.status === "failed" && job.error ? `: ${job.error}` : ""}
          </p>
          {job.status === "done" && job.result && (
            <>
              <p className={styles.value}>
                {job.result.record.name} · {job.result.record.regulator}
              </p>
              <p className={styles.muted}>Source files: {job.files.join(", ")}</p>
              <ul className={styles.rows} data-testid="reg-job-sections">
                {sections.map((s) => <li key={s} className={styles.value}>{s}</li>)}
              </ul>
              <p className={styles.muted}>
                Approval is write-once: an approved pack is never edited. A newer approved pack for the same market and
                category replaces it in live shows.
              </p>
              <Button variant="primary" disabled={busy || approved !== null} data-testid="reg-approve"
                      onClick={() => act(async () => {
                        const { pack_id } = await regulationsApi.approve(job.job_id);
                        setApproved(pack_id);
                        load();
                      })}>
                Approve regulation
              </Button>
              {approved && <p className={styles.status} data-testid="reg-approved">Approved as {approved}.</p>}
            </>
          )}
        </div>
      )}

      {error && <p className={styles.error}>{error}</p>}

      {reg && (
        <>
          <h3 className={styles.blockTitle}>Approved regulations</h3>
          <ul className={styles.rows} data-testid="reg-packs">
            <li className={styles.row} data-testid="reg-market-law">
              <span className={styles.value}>
                {reg.market} market law: {reg.market_law.name} · covers {reg.market_law.covers.join(", ")}
              </span>
              <span className={styles.muted}>Source files: {reg.market_law.files.join(", ") || "none"}</span>
            </li>
            {reg.packs.map((p) => (
              <li key={p.pack_id} className={styles.row} data-testid={`reg-pack-${p.pack_id}`}>
                <span className={styles.value}>
                  {p.name} · {p.market} · {p.covers.join(", ")} · approved {day(p.approved_at)}{" "}
                  {p.active_for.length
                    ? <Chip tone="ok">Active for {p.active_for.join(", ")}</Chip>
                    : <Chip>Replaced by a newer pack</Chip>}
                </span>
                <span className={styles.muted}>Source files: {p.files.join(", ") || "none"}</span>
                <span className={styles.evidence}>{p.sections.map((s) => <span key={s}>{s}</span>)}</span>
              </li>
            ))}
          </ul>

          <h3 className={styles.blockTitle}>What each product's live judge reads</h3>
          <ul className={styles.rows} data-testid="reg-releases">
            {reg.releases.map((r) => (
              <li key={r.release_id} className={styles.row} data-testid={`reg-release-${r.release_id}`}>
                <span className={styles.value}>{r.product_name} · {r.category}</span>
                {r.originals.length > 0 && (
                  <span className={styles.muted}>
                    {r.originals.map((o) => (o.kind === "brand" ? `${o.name} (brand)` : o.name)).join(", ")}
                  </span>
                )}
                {r.warning && (
                  <p className={styles.warning} data-testid={`reg-warning-${r.release_id}`}>
                    No regulation matches this product's category ({r.category}): its live compliance judge has no
                    regulation to read.{r.error ? ` (${r.error})` : ""}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
