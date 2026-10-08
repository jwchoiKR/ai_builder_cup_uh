// Product onboarding (P0 step 6, D-224/D-231): upload any documents of one product, watch the read, review every field
// with its evidence (file, place, quote), choose between conflicting values, fix a value in place, approve, and start
// a show on the release.
import { useEffect, useState } from "react";

import { Button, Chip, Eyebrow, HubLink } from "../../components";
import { navigate } from "../../app/nav";
import {
  BRIEF_RUNNING_NOTE, onboardingApi, type Evidence, type Job, type Line, type ProductRecord, type TextItem, type Translations,
} from "./onboardingApi";
import { conflictValue, money, newestIndex, plainField, setAt } from "./recordEdit";
import { RegulationsPanel } from "./RegulationsPanel";
import styles from "./onboarding.module.css";

type Approved = Awaited<ReturnType<typeof onboardingApi.approve>>;

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

/** A value that turns into an input on click ("Edit"), and back on Enter or blur. */
function Editable({ value, onSave, label }: { value: string; onSave: (v: string) => void; label: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (!editing)
    return (
      <span className={styles.editable}>
        <span className={styles.value}>{value}</span>
        <button type="button" className={styles.editLink} onClick={() => { setDraft(value); setEditing(true); }}
                aria-label={`Edit ${label}`}>
          Edit
        </button>
      </span>
    );
  const save = () => { setEditing(false); if (draft.trim() && draft !== value) onSave(draft.trim()); };
  return (
    <input className={styles.input} autoFocus value={draft} aria-label={label} onChange={(e) => setDraft(e.target.value)}
           onBlur={save} onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }} />
  );
}

function TextRows({ title, items, onChange }: { title: string; items: TextItem[]; onChange: (items: TextItem[]) => void }) {
  return (
    <section className={styles.block} data-testid={`onb-${title.toLowerCase().replace(/\W+/g, "-")}`}>
      <h2 className={styles.blockTitle}>
        {title} <span className={styles.count}>{items.length}</span>
      </h2>
      {items.length === 0 ? (
        <p className={styles.muted}>None in the documents.</p>
      ) : (
        <ul className={styles.rows}>
          {items.map((it, i) => (
            <li key={i} className={styles.row}>
              <Editable value={it.text} label={title}
                        onSave={(v) => onChange(items.map((x, j) => (j === i ? { ...x, text: v } : x)))} />
              <Ev items={it.evidence} />
            </li>
          ))}
        </ul>
      )}
    </section>
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

export function RecordReview({ record, onChange }: { record: ProductRecord; onChange: (r: ProductRecord) => void }) {
  const r = record;
  const set = (path: string, v: string) => {
    const next = setAt(r, path, v);
    if (next) onChange(next);
  };
  const text = (key: "cautions" | "approved_claims" | "not_approved_claims" | "how_to_use" | "key_facts") =>
    (items: TextItem[]) => onChange({ ...r, [key]: items });
  return (
    <>
      <section className={styles.block} data-testid="onb-variants-and-prices">
        <h2 className={styles.blockTitle}>
          Sizes and prices <span className={styles.count}>{r.variants.length}</span>
        </h2>
        <ul className={styles.rows}>
          {r.variants.map((v, i) => (
            <li key={v.variant_id} className={styles.row}>
              <span className={styles.value}>{v.name} ({v.variant_id})</span>
              <span className={styles.inline}>
                Size:{" "}
                <Editable value={v.size_value ? `${v.size_value}` : "—"} label={`${v.name} size`}
                          onSave={(x) => set(`variants[${i}].size_value`, x)} /> {v.size_unit ?? ""}
              </span>
              {v.prices.map((m, j) => (
                <span key={j} className={styles.inline}>
                  {m.kind} price{m.market ? ` ${m.market}` : ""}:{" "}
                  <Editable value={money(m)} label={`${v.name} ${m.kind} price`}
                            onSave={(x) => set(`variants[${i}].prices[${j}].minor`, x)} />
                </span>
              ))}
              <Ev items={v.evidence} />
            </li>
          ))}
        </ul>
      </section>
      <Rows title="Offers" rows={r.offers.map((o) => ({
        value: `${o.title}${o.percent ? ` · ${o.percent}% off` : ""}${o.amount ? ` · ${money(o.amount)}` : ""}`,
        evidence: o.evidence }))} />
      <TextRows title="Cautions" items={r.cautions} onChange={text("cautions")} />
      <TextRows title="Approved claims" items={r.approved_claims} onChange={text("approved_claims")} />
      <TextRows title="Claims not approved" items={r.not_approved_claims} onChange={text("not_approved_claims")} />
      <Rows title="Test results" rows={r.qualified_results.map((q) => ({
        value: `${q.statement} — say “${q.qualifier}”${q.marker ? ` (${q.marker})` : ""}`, evidence: q.evidence }))} />
      <Rows title="Avoid saying" rows={r.avoid_saying.map((a) => ({ value: `“${a.say_not}” → “${a.say}”`,
        evidence: a.evidence }))} />
      <Rows title={`Ingredients${r.ingredient_list_complete ? " (complete list)" : ""}`} rows={r.ingredients.map((x) => ({
        value: `${x.name}${x.amount_value ? ` ${x.amount_value}${x.amount_unit ?? ""}` : ""}`, evidence: x.evidence }))} />
      <TextRows title="How to use" items={r.how_to_use} onChange={text("how_to_use")} />
      <TextRows title="Key facts" items={r.key_facts} onChange={text("key_facts")} />
    </>
  );
}

/** D-266: the release's brief runs after approval; until it lands a show uses the approved claims as points. */
function BriefStatus({ releaseId }: { releaseId: string }) {
  const [status, setStatus] = useState("running");
  useEffect(() => {
    if (status !== "running") return;
    const timer = window.setTimeout(
      () => onboardingApi.briefStatus(releaseId).then((r) => setStatus(r.status), () => setStatus("unknown")), 2000);
    return () => window.clearTimeout(timer);
  }, [releaseId, status]);
  return (
    <p className={status === "running" || status.startsWith("failed") ? styles.warning : styles.muted}
       data-testid="onb-brief-status">
      {status === "running" ? BRIEF_RUNNING_NOTE
        : status === "done" ? "Brief done: speech-recognition names and prompter points are ready."
          : `Brief ${status}: the show uses the approved claims as points and only the main names as hints.`}
    </p>
  );
}

/** D-233: machine-translated host lines; each one is approved on its own (only approved lines may be auto-posted). */
function TranslationReview({ translations, onChange }: { translations: Translations; onChange: (t: Translations) => void }) {
  const setAll = (value: boolean) =>
    onChange(Object.fromEntries(Object.entries(translations).map(([lang, t]) => [lang, {
      approved_claims: t.approved_claims.map((x) => ({ ...x, reviewed: value })),
      cautions: t.cautions.map((x) => ({ ...x, reviewed: value })),
      avoid_saying: t.avoid_saying.map((x) => ({ ...x, reviewed: value })) }])));
  const toggle = (lang: string, key: "approved_claims" | "cautions" | "avoid_saying", i: number) =>
    onChange({ ...translations, [lang]: { ...translations[lang],
      [key]: translations[lang][key].map((x: Line, j: number) => (j === i ? { ...x, reviewed: !x.reviewed } : x)) } });
  return (
    <section className={styles.block} data-testid="onb-translations">
      <h2 className={styles.blockTitle}>Machine translations to review</h2>
      <p className={styles.muted}>
        Unreviewed lines are shown to the host marked “unreviewed translation” and never posted to viewers by themselves.
      </p>
      <div className={styles.actions}>
        <Button size="sm" onClick={() => setAll(true)} data-testid="onb-approve-all-translations">Approve all translations</Button>
      </div>
      {Object.entries(translations).map(([lang, t]) => (
        <div key={lang}>
          <p className={styles.value}><b>{lang}</b></p>
          <ul className={styles.rows}>
            {(["approved_claims", "cautions", "avoid_saying"] as const).flatMap((key) =>
              t[key].map((x: Line, i: number) => (
                <li key={`${key}${i}`} className={styles.inline}>
                  <label>
                    <input type="checkbox" checked={x.reviewed} onChange={() => toggle(lang, key, i)} />{" "}
                    {x.text ?? `“${x.say_not}” → “${x.say}”`}
                  </label>
                </li>
              )))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function Conflicts({ record, onChange }: { record: ProductRecord; onChange: (r: ProductRecord) => void }) {
  const [chosen, setChosen] = useState<Record<number, number>>(() =>
    Object.fromEntries(record.conflicts.map((c, i) => [i, newestIndex(c.effective_dates)])));
  const choose = (i: number, k: number) => {
    setChosen((x) => ({ ...x, [i]: k }));
    const c = record.conflicts[i];
    const next = setAt(record, c.field, c.values[k]);
    if (next) onChange(next);
  };
  return (
    <section className={`${styles.block} ${styles.risk}`} data-testid="onb-conflicts">
      <h2 className={styles.blockTitle}>The documents disagree: choose one</h2>
      <ul className={styles.rows}>
        {record.conflicts.map((c, i) => (
          <li key={i} className={styles.row}>
            <span className={styles.value}>{plainField(record, c.field)}</span>
            <span className={styles.actions}>
              {c.values.map((v, k) => (
                <Button key={k} size="sm" variant={chosen[i] === k ? "primary" : "secondary"} onClick={() => choose(i, k)}
                        aria-pressed={chosen[i] === k}>
                  Use {conflictValue(record, c.field, v)}{c.effective_dates[k] ? ` (${c.effective_dates[k]}${k === newestIndex(c.effective_dates) ? ", newest" : ""})` : ""}
                </Button>
              ))}
            </span>
            <Ev items={c.evidence} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function OnboardingView() {
  const [files, setFiles] = useState<File[]>([]);
  const [hints, setHints] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [rec, setRec] = useState<ProductRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [draft, setDraft] = useState("");
  const [release, setRelease] = useState<Approved | null>(null);
  const [translations, setTranslations] = useState<Translations | null>(null);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = window.setTimeout(() => {
      onboardingApi.job(job.job_id).then((j) => {
        setJob(j);
        if (j.status === "done" && j.result) {
          setRec(j.result.record);
          onboardingApi.preview(j.job_id).then((p) => setTranslations(p.translations), () => setTranslations({}));
        }
      }, (e) => setError(String(e)));
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
  const edit = (r: ProductRecord) => { setRec(r); setRelease(null); };

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
                  setRec(null);
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

      {rec && result && (
        <>
          <section className={styles.summary} data-testid="onb-summary">
            <h2 className={styles.product}>{rec.brand} · {rec.product_name}</h2>
            <div className={styles.chips}>
              <Chip>{rec.category}</Chip>
              <Chip>{rec.language}</Chip>
              <Chip>{rec.variants.length} sizes</Chip>
              <Chip>{rec.cautions.length} cautions</Chip>
              <Chip tone={rec.conflicts.length ? "risk" : undefined}>{rec.conflicts.length} to choose</Chip>
              <Chip>{Math.round(result.seconds)} s</Chip>
            </div>
            <Ev items={rec.category_evidence} />
          </section>

          {(result.verify_mode === "risk" || result.verify_mode === "lean") && result.checks && (
            // D-236: only what would reach the live show, by group, plus audit samples; D-254 lean: at most 10
            <section className={styles.block} data-testid="onb-to-check">
              <h2 className={styles.blockTitle}>
                To check <span className={styles.count}>{result.checks.length}</span>
                {result.check_summary?.before !== undefined && (
                  <span className={styles.muted}> of {result.check_summary.before} found</span>
                )}
              </h2>
              <ul className={styles.rows}>
                {result.checks.map((c, i) => (
                  <li key={i} className={styles.row}>
                    <span className={styles.value}>
                      <b>{c.group}</b> · {plainField(rec, c.label)}
                    </span>
                    <span className={styles.muted}>{c.reason}</span>
                  </li>
                ))}
              </ul>
              {!!result.checks_collapsed?.length && (
                <details data-testid="onb-collapsed">
                  <summary className={styles.muted}>{result.checks_collapsed.length} more, lower live impact</summary>
                  <ul className={styles.rows}>
                    {result.checks_collapsed.map((c, i) => (
                      <li key={i} className={styles.row}>
                        <span className={styles.value}><b>{c.group}</b> · {plainField(rec, c.label)}</span>
                        <span className={styles.muted}>{c.reason}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {!!result.auto_accepted?.length && (
                <details data-testid="onb-auto-accepted">
                  <summary className={styles.muted}>
                    {result.auto_accepted.length} cautions added automatically, with their source
                  </summary>
                  <ul className={styles.rows}>
                    {result.auto_accepted.map((c, i) => (
                      <li key={i} className={styles.row}>
                        <span className={styles.value}>{c.label}</span>
                        <span className={styles.muted}>{c.source}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </section>
          )}
          {rec.conflicts.length > 0 && <Conflicts record={rec} onChange={edit} />}
          {(rec.missing.length > 0 || result.notes.length > 0) && (
            <section className={styles.block} data-testid="onb-missing">
              <h2 className={styles.blockTitle}>Not in the documents, or left out</h2>
              <ul className={styles.rows}>
                {rec.missing.map((m, i) => <li key={`m${i}`} className={styles.muted}>{plainField(rec, m)}</li>)}
                {result.notes.map((m, i) => <li key={`n${i}`} className={styles.muted}>{m}</li>)}
              </ul>
            </section>
          )}

          {translations && Object.keys(translations).length > 0 && (
            <TranslationReview translations={translations} onChange={setTranslations} />
          )}

          <RecordReview record={rec} onChange={edit} />

          <section className={styles.block}>
            <div className={styles.actions}>
              <Button variant="primary" disabled={busy} data-testid="onb-approve"
                      onClick={() => act(async () => {
                        const edited = advanced ? (JSON.parse(draft) as ProductRecord) : rec;
                        setRelease(await onboardingApi.approve(job!.job_id, edited, translations ?? undefined));
                      })}>
                Approve and create release
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setAdvanced(!advanced); setDraft(JSON.stringify(rec, null, 1)); }}>
                {advanced ? "Close advanced editor" : "Advanced: edit as JSON"}
              </Button>
            </div>
            {advanced && (
              <textarea className={styles.editor} rows={18} value={draft} onChange={(e) => setDraft(e.target.value)}
                        aria-label="Record JSON" />
            )}
          </section>

          {release && (
            <section className={`${styles.block} ${styles.ok}`} data-testid="onb-release">
              <p className={styles.value}>
                Release <b>{release.release_id}</b> is ready. In the live show:
              </p>
              <ul className={styles.rows} data-testid="onb-live-summary">
                <li>Price: {release.live?.price}</li>
                <li>Compliance: {release.live?.law}</li>
                <li>{release.live?.cautions} cautions for answers, {release.live?.approved_claims} approved claims for the prompter,
                  {" "}{release.live?.not_approved_claims} claims not approved, {release.live?.promos} offers to start</li>
              </ul>
              {release.warnings.map((w) => <p key={w} className={styles.warning}>{w}</p>)}
              <BriefStatus releaseId={release.release_id} />
              <Button variant="primary" disabled={busy}
                      onClick={() => act(async () => {
                        const s = await onboardingApi.startShow([release.release_id]);
                        navigate(`/studio?session=${encodeURIComponent(s.session_id)}`);
                      })}>
                Start a show with this product
              </Button>
            </section>
          )}
        </>
      )}

      <RegulationsPanel />
    </div>
  );
}
