// Product onboarding (P0 step 6, D-224): upload any documents of one product, watch the read, review every field
// with its evidence (file, place, quote), resolve conflicts, edit if needed, approve, and start a show on the release.
import { useEffect, useState } from "react";

import { Button, Chip, Eyebrow, HubLink } from "../../components";
import { navigate } from "../../app/nav";
import { onboardingApi, type Evidence, type Job, type ProductRecord } from "./onboardingApi";
import styles from "./onboarding.module.css";

function Ev({ items }: { items: Evidence[] }) {
  if (!items.length) return null;
  return (
    <span className={styles.evidence}>
      {items.map((e, i) => (
        <span key={i} title={e.quote}>
          {e.file} · {e.locator} · “{e.quote}”
        </span>
      ))}
    </span>
  );
}

function Rows({ title, rows }: { title: string; rows: { value: string; evidence: Evidence[] }[] }) {
  return (
    <section className={styles.block} data-testid={`onb-${title.toLowerCase().replace(/\W+/g, "-")}`}>
      <h2 className={styles.blockTitle}>
        {title} <span className={styles.count}>{rows.length}</span>
      </h2>
      {rows.length === 0 ? (
        <p className={styles.muted}>None in the documents.</p>
      ) : (
        <ul className={styles.rows}>
          {rows.map((r, i) => (
            <li key={i} className={styles.row}>
              <span className={styles.value}>{r.value}</span>
              <Ev items={r.evidence} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const money = (m: { currency: string; minor: number }) => `${m.currency} ${(m.minor / 100).toFixed(2)}`;

export function RecordReview({ record }: { record: ProductRecord }) {
  const r = record;
  return (
    <>
      <Rows
        title="Variants and prices"
        rows={r.variants.flatMap((v) => [
          { value: `${v.name} (${v.variant_id})${v.size_value ? ` · ${v.size_value} ${v.size_unit ?? ""}` : ""}`,
            evidence: v.evidence },
          ...v.prices.map((m) => ({ value: `  ${m.kind} price ${money(m)}${m.market ? ` · ${m.market}` : ""}`,
            evidence: m.evidence })),
        ])}
      />
      <Rows title="Offers" rows={r.offers.map((o) => ({
        value: `${o.title} (${o.kind}${o.percent ? ` ${o.percent}%` : ""}${o.amount ? ` ${money(o.amount)}` : ""})`,
        evidence: o.evidence }))} />
      <Rows title="Cautions" rows={r.cautions.map((c) => ({ value: c.text, evidence: c.evidence }))} />
      <Rows title="Approved claims" rows={r.approved_claims.map((c) => ({ value: c.text, evidence: c.evidence }))} />
      <Rows title="Not approved claims" rows={r.not_approved_claims.map((c) => ({ value: c.text, evidence: c.evidence }))} />
      <Rows title="Test results" rows={r.qualified_results.map((q) => ({
        value: `${q.statement} — say “${q.qualifier}” (${q.provenance}${q.marker ? `, ${q.marker}` : ""})`,
        evidence: q.evidence }))} />
      <Rows title="Avoid saying" rows={r.avoid_saying.map((a) => ({ value: `“${a.say_not}” → “${a.say}”`,
        evidence: a.evidence }))} />
      <Rows title={`Ingredients${r.ingredient_list_complete ? " (complete list)" : ""}`} rows={r.ingredients.map((i) => ({
        value: `${i.name}${i.amount_value ? ` ${i.amount_value}${i.amount_unit ?? ""}` : ""}`, evidence: i.evidence }))} />
      <Rows title="How to use" rows={r.how_to_use.map((c) => ({ value: c.text, evidence: c.evidence }))} />
      <Rows title="Key facts" rows={r.key_facts.map((c) => ({ value: c.text, evidence: c.evidence }))} />
    </>
  );
}

export function OnboardingView() {
  const [files, setFiles] = useState<File[]>([]);
  const [hints, setHints] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [release, setRelease] = useState<{ release_id: string; warnings: string[] } | null>(null);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = window.setTimeout(() => {
      onboardingApi.job(job.job_id).then(setJob, (e) => setError(String(e)));
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
  const result = job?.status === "done" ? job.result : null;
  const record = result?.record ?? null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · PRODUCT ONBOARDING
        </Eyebrow>
        <h1 className={styles.title}>Onboard a product</h1>
        <p className={styles.muted}>
          Any documents of one product: spec sheets, label photos, price lists, brochures, in any layout or language. Every
          value comes with the place it was read from. Nothing is live until you approve it.
        </p>
      </header>

      <section className={styles.block}>
        <input type="file" multiple data-testid="onb-files"
               onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        <input className={styles.input} placeholder="Optional hints (brand, market)" value={hints}
               onChange={(e) => setHints(e.target.value)} />
        <Button variant="primary" disabled={busy || files.length === 0} data-testid="onb-read"
                onClick={() => act(async () => {
                  setRelease(null);
                  const { job_id } = await onboardingApi.upload(files, hints);
                  setJob({ job_id, status: "queued", files: files.map((f) => f.name), result: null, error: null });
                })}>
          Read {files.length || ""} document{files.length === 1 ? "" : "s"}
        </Button>
        {job && job.status !== "done" && (
          <p className={styles.status} data-testid="onb-status">
            {job.status === "failed" ? `Failed: ${job.error}` : `Reading ${job.files.length} file(s)… about 1–3 minutes.`}
          </p>
        )}
      </section>

      {error && <p className={styles.error}>{error}</p>}

      {record && result && (
        <>
          <section className={styles.summary} data-testid="onb-summary">
            <h2 className={styles.product}>{record.brand} · {record.product_name}</h2>
            <div className={styles.chips}>
              <Chip>{record.category}</Chip>
              <Chip>{record.language}</Chip>
              <Chip>{record.variants.length} variants</Chip>
              <Chip>{record.cautions.length} cautions</Chip>
              <Chip tone={record.conflicts.length ? "risk" : undefined}>{record.conflicts.length} conflicts</Chip>
              <Chip>{Math.round(result.seconds)} s</Chip>
            </div>
            <Ev items={record.category_evidence} />
          </section>

          {record.conflicts.length > 0 && (
            <section className={`${styles.block} ${styles.risk}`} data-testid="onb-conflicts">
              <h2 className={styles.blockTitle}>Conflicts to check</h2>
              <ul className={styles.rows}>
                {record.conflicts.map((c, i) => (
                  <li key={i} className={styles.row}>
                    <span className={styles.value}>
                      {c.field}: {c.values.map((v, j) => `${v}${c.effective_dates[j] ? ` (${c.effective_dates[j]})` : ""}`).join(" vs ")}
                    </span>
                    <Ev items={c.evidence} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {(record.missing.length > 0 || result.notes.length > 0) && (
            <section className={styles.block}>
              <h2 className={styles.blockTitle}>Not in the documents, or dropped</h2>
              <ul className={styles.rows}>
                {[...record.missing, ...result.notes].map((m, i) => <li key={i} className={styles.muted}>{m}</li>)}
              </ul>
            </section>
          )}

          <RecordReview record={record} />

          <section className={styles.block}>
            <div className={styles.actions}>
              <Button onClick={() => { setEditing(!editing); setDraft(JSON.stringify(record, null, 1)); }}>
                {editing ? "Close editor" : "Edit record"}
              </Button>
              <Button variant="primary" disabled={busy} data-testid="onb-approve"
                      onClick={() => act(async () => {
                        const edited = editing ? (JSON.parse(draft) as ProductRecord) : undefined;
                        setRelease(await onboardingApi.approve(job!.job_id, edited));
                      })}>
                Approve and create release
              </Button>
            </div>
            {editing && (
              <textarea className={styles.editor} rows={18} value={draft} onChange={(e) => setDraft(e.target.value)}
                        aria-label="Record JSON" />
            )}
          </section>

          {release && (
            <section className={`${styles.block} ${styles.ok}`} data-testid="onb-release">
              <p>
                Release <b>{release.release_id}</b> created.
              </p>
              {release.warnings.map((w) => <p key={w} className={styles.warning}>{w}</p>)}
              <Button variant="primary" disabled={busy}
                      onClick={() => act(async () => {
                        const s = await onboardingApi.startShow(release.release_id);
                        navigate(`/studio?session=${encodeURIComponent(s.session_id)}`);
                      })}>
                Start a show with this product
              </Button>
            </section>
          )}
        </>
      )}
    </div>
  );
}
