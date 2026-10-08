// Pre-broadcast setup page (DEV_SPEC §12.7): documents, Brief Agent results, glossary confirmation.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useT } from "../../app/i18n";
import { PDF_ACCEPT, pdfOnly } from "../../app/pdfOnly";
import type { ThemeName, ThemePref } from "../../app/theme";
import type { PrompterPoint, Product } from "../../app/types";
import { Button, Chip, Eyebrow, HubLink, Panel, SettingsButton } from "../../components";
import { GlossaryTable, type TermRow } from "./GlossaryTable";
import type {
  BriefRecord,
  ConfirmProduct,
  GlossaryState,
  GlossaryTerm,
  PointChoice,
  SetupClient,
  SetupDocument,
  SetupMarket,
  UploadJob,
} from "./setupApi";
import styles from "./setup.module.css";
import { RegulationsPanel } from "../onboarding/RegulationsPanel";
import { UploadStages } from "./UploadStages";

type Choice = "" | "add" | `replace:${string}`;

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const time = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const POLL_MS = 300;

const toRows = (terms: GlossaryTerm[]): TermRow[] => terms.map((t) => ({ ...t, spoken_forms: [...t.spoken_forms], include: true }));

/** D-094: rows start from the confirmed terms when the confirmation is newer than the Brief Agent
 * run (so edits survive a reload), else from the Brief Agent draft. */
function initialRows(brief: BriefRecord | null | undefined, glossary: GlossaryState | null, productId: string): TermRow[] | null {
  const draft = brief?.output?.glossary;
  if (!draft) return null;
  const confirmed = glossary?.terms_by_product?.[productId];
  if (confirmed && glossary?.confirmed_at != null && brief!.ran_at <= glossary.confirmed_at) return toRows(confirmed);
  return toRows(draft);
}

export interface SetupViewProps {
  products: Product[];
  brand: string;
  client: SetupClient;
  theme: ThemeName;
  /** the shared Settings gear (theme and UI language); absent in a Studio pane */
  themePref?: ThemePref;
  onSetTheme?: (t: ThemePref) => void;
  sessionId?: string | null;
}

export function SetupView({ products, brand, client, theme, themePref, onSetTheme, sessionId = null }: SetupViewProps) {
  const t = useT();
  const [docs, setDocs] = useState<SetupDocument[]>([]);
  const [docMessage, setDocMessage] = useState<{ tone: "ok" | "risk"; text: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState<UploadJob | null>(null);
  const [glossary, setGlossary] = useState<GlossaryState | null>(null);
  const [glossaryLoaded, setGlossaryLoaded] = useState(false);
  const [market, setMarket] = useState<SetupMarket | null>(null);
  const [briefs, setBriefs] = useState<Record<string, BriefRecord | null>>({});
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [briefErrors, setBriefErrors] = useState<Record<string, string | null>>({});
  const [rows, setRows] = useState<Record<string, TermRow[]>>({});
  const [choices, setChoices] = useState<Record<string, Record<number, Choice>>>({});
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState<number | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const loadDocs = useCallback(async () => {
    try {
      setDocs((await client.documents()).documents);
    } catch (e) {
      setDocMessage({ tone: "risk", text: errorText(e) });
    }
  }, [client]);

  useEffect(() => {
    void loadDocs();
    // D-142: the market and broadcast language new sessions get (read-only while only one pair exists)
    client.market?.().then(setMarket, () => setMarket(null));
    client.glossary().then(
      (g) => {
        setGlossary(g);
        setGlossaryLoaded(true);
      },
      () => {
        setGlossary(null);
        setGlossaryLoaded(true);
      },
    );
  }, [client, loadDocs]);

  const productIds = useMemo(() => products.map((p) => p.product_id).join(","), [products]);
  useEffect(() => {
    for (const p of products) {
      client.getBrief(p.product_id).then(
        (b) => setBriefs((prev) => (p.product_id in prev ? prev : { ...prev, [p.product_id]: b })),
        () => undefined,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, productIds]);

  // Rows for products whose Brief Agent result or confirmed glossary arrived (never over edits).
  useEffect(() => {
    if (!glossaryLoaded) return; // the confirmed terms decide where the rows start
    setRows((prev) => {
      let next = prev;
      for (const p of products) {
        if (next[p.product_id]) continue;
        const init = initialRows(briefs[p.product_id], glossary, p.product_id);
        if (init) next = { ...next, [p.product_id]: init };
      }
      return next;
    });
  }, [products, briefs, glossary, glossaryLoaded]);

  const onUpload = async (file: File) => {
    setUploading(true);
    setDocMessage(null);
    try {
      let current = await client.upload(file, file.name);
      setJob(current);
      while (current.status === "running" && alive.current) {
        await sleep(POLL_MS);
        current = await client.uploadJob(current.job_id);
        if (alive.current) setJob(current);
      }
      if (current.status === "failed") setDocMessage({ tone: "risk", text: current.error ?? "Upload failed" });
      else if (current.result)
        setDocMessage({ tone: "ok", text: current.result.status === "already_indexed" ? "Already indexed" : current.result.message });
      await loadDocs();
    } catch (e) {
      setDocMessage({ tone: "risk", text: errorText(e) });
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const runBrief = async (productId: string) => {
    setRunning((r) => ({ ...r, [productId]: true }));
    setBriefErrors((e) => ({ ...e, [productId]: null }));
    try {
      const record = await client.runBrief(productId);
      setBriefs((b) => ({ ...b, [productId]: record }));
      setRows((r) => ({ ...r, [productId]: toRows(record.output?.glossary ?? []) })); // a new run replaces edits
      setChoices((c) => ({ ...c, [productId]: {} }));
    } catch (e) {
      setBriefErrors((errs) => ({ ...errs, [productId]: errorText(e) })); // the previous result stays
    } finally {
      setRunning((r) => ({ ...r, [productId]: false }));
    }
  };

  const currentPoints = (p: Product): PrompterPoint[] => glossary?.prompter_points?.[p.product_id] ?? p.prompter_points;
  const reviewed = products.filter((p) => briefs[p.product_id]?.output);
  const selectedTerms = reviewed.reduce((n, p) => n + (rows[p.product_id] ?? []).filter((t) => t.include).length, 0);

  const confirm = async () => {
    const payload: Record<string, ConfirmProduct> = {};
    for (const p of reviewed) {
      const out = briefs[p.product_id]!.output!;
      const picks: PointChoice[] = [];
      out.prompter_points.forEach((d, i) => {
        const c = choices[p.product_id]?.[i] ?? "";
        if (c === "add") picks.push({ text: d.text, action: "add", source_section: d.source_section });
        else if (c.startsWith("replace:"))
          picks.push({ text: d.text, action: "replace", point_id: c.slice("replace:".length), source_section: d.source_section });
      });
      payload[p.product_id] = {
        glossary: (rows[p.product_id] ?? toRows(out.glossary)).map(({ term, kind, spoken_forms, source_section, include }) => ({
          term,
          kind,
          spoken_forms,
          source_section,
          include,
        })),
        prompter_points: picks,
      };
    }
    setConfirming(true);
    setConfirmError(null);
    try {
      const state = await client.confirmAll(payload);
      setConfirmed(state.version);
      setGlossary(await client.glossary().catch(() => state));
      setChoices({});
    } catch (e) {
      setConfirmError(errorText(e));
    } finally {
      setConfirming(false);
    }
  };

  const productName = (pid: string | null) => products.find((p) => p.product_id === pid)?.name ?? pid ?? "Unknown";

  return (
    <div className={styles.root} data-theme={theme}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <Eyebrow>
            {onSetTheme && (
              <>
                <HubLink sessionId={sessionId} /> ·{" "}
              </>
            )}
            Pre-broadcast
          </Eyebrow>
          <span className={styles.title}>Setup</span>
          <span className={styles.subtitle}>{brand} · Product documents, Brief Agent and glossary</span>
        </div>
        <div className={styles.headerActions}>
          {market && (
            <Chip tone="neutral" data-testid="setup-market" title={`Rules: ${market.regulator} · speech: ${market.stt_language}`}>
              {market.name} · {market.lang_name}
            </Chip>
          )}
          <Chip tone={glossary?.version ? "ok" : "neutral"} data-testid="setup-glossary-version">
            {glossary
              ? glossary.version
                ? `Glossary version ${glossary.version}`
                : "Default glossary (version 0)"
              : "Glossary"}
          </Chip>
          {onSetTheme && <SettingsButton themePref={themePref} onTheme={onSetTheme} />}
        </div>
      </header>

      <main className={styles.body}>
        <Panel
          title={<span className={styles.panelTitle} data-testid="setup-product-docs">1 · {t("Product documents")}</span>}
          actions={
            <>
              <input
                ref={fileInput}
                type="file"
                accept={PDF_ACCEPT}
                hidden
                data-testid="setup-file-input"
                onChange={(e) => {
                  const pick = pdfOnly(Array.from(e.target.files ?? []), t);  // D-368 (user): PDF only
                  if (pick.error) {
                    setDocMessage({ tone: "risk", text: pick.error });
                    e.target.value = "";
                  } else if (pick.files[0]) void onUpload(pick.files[0]);
                }}
              />
              <Button disabled={uploading} onClick={() => fileInput.current?.click()}>
                {uploading ? t("Uploading…") : t("Upload PDF")}
              </Button>
            </>
          }
        >
          <table className={styles.table} data-testid="setup-documents">
            <thead>
              <tr>
                <th>{t("Document")}</th>
                <th>{t("Product")}</th>
                <th>{t("Pages")}</th>
                <th>{t("Index")}</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={`${d.source}:${d.name}`}>
                  <td>{d.name}</td>
                  <td>{productName(d.product_id)}</td>
                  <td className="tabular">{d.pages}</td>
                  <td>
                    <Chip tone="ok">{d.status}</Chip>
                  </td>
                </tr>
              ))}
              {docs.length === 0 && (
                <tr>
                  <td colSpan={4} className={styles.muted}>
                    {t("No documents.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {job && <UploadStages job={job} />}
          {docMessage && (
            <p className={docMessage.tone === "ok" ? styles.okText : styles.errorText} role="status">
              {docMessage.text}
            </p>
          )}
        </Panel>

        {/* D-371 (user): regulation documents apart from the product's (the onboarding Regulations panel, D-359) */}
        <Panel title={<span className={styles.panelTitle} data-testid="setup-regulation-docs">1 · {t("Regulation documents")}</span>}>
          <RegulationsPanel title={null} />
        </Panel>

        <h2 className={styles.sectionTitle}>2 · Brief Agent</h2>
        <div className={styles.products}>
          {products.map((p) => {
            const record = briefs[p.product_id];
            const out = record?.output;
            const busy = running[p.product_id] ?? false;
            return (
              <section key={p.product_id} className={styles.productCard} data-testid={`setup-product-${p.product_id}`}>
                <header className={styles.productHead}>
                  <div>
                    <Eyebrow>{p.code}</Eyebrow>
                    <div className={styles.productName}>{p.name}</div>
                  </div>
                  <Button variant="primary" disabled={busy} aria-busy={busy} onClick={() => void runBrief(p.product_id)}>
                    {busy ? (
                      <>
                        <span className={styles.spinner} aria-hidden /> Running…
                      </>
                    ) : (
                      "Run Brief Agent"
                    )}
                  </Button>
                </header>
                {briefErrors[p.product_id] && (
                  <p className={styles.errorText} role="alert">
                    {briefErrors[p.product_id]}
                  </p>
                )}
                {!out && !busy && <p className={styles.muted}>Not run yet. The glossary uses the default terms.</p>}
                {out && (
                  <>
                    <p className={styles.meta}>
                      Ran at {time(record!.ran_at)} · {out.glossary.length} terms · {out.prompter_points.length} point drafts
                    </p>
                    <h3 className={styles.subTitle}>Glossary</h3>
                    <GlossaryTable
                      productId={p.product_id}
                      rows={rows[p.product_id] ?? []}
                      onChange={(next) => setRows((all) => ({ ...all, [p.product_id]: next }))}
                    />

                    <h3 className={styles.subTitle}>Prompter points</h3>
                    <div className={styles.points}>
                      <div>
                        <Eyebrow>Current points</Eyebrow>
                        <ol className={styles.pointList}>
                          {currentPoints(p).map((pt) => (
                            <li key={pt.point_id}>
                              <span className={styles.pointId}>{pt.point_id}</span> {pt.text}
                              {pt.required && <span className={styles.required}>Required point</span>}
                            </li>
                          ))}
                        </ol>
                      </div>
                      <div>
                        <Eyebrow>Drafts (optional)</Eyebrow>
                        <ol className={styles.pointList}>
                          {out.prompter_points.map((d, i) => (
                            <li key={i} className={styles.draft}>
                              <span>
                                {d.text}
                                <span className={styles.draftMeta}>
                                  {d.required ? "Required in draft" : "Optional"} · {d.source_section}
                                </span>
                              </span>
                              <select
                                aria-label={`Use draft ${i + 1}`}
                                value={choices[p.product_id]?.[i] ?? ""}
                                onChange={(e) =>
                                  setChoices((all) => ({
                                    ...all,
                                    [p.product_id]: { ...all[p.product_id], [i]: e.target.value as Choice },
                                  }))
                                }
                              >
                                <option value="">Not used</option>
                                {currentPoints(p).map((pt) => (
                                  <option key={pt.point_id} value={`replace:${pt.point_id}`}>
                                    Use as text for {pt.point_id}
                                  </option>
                                ))}
                                <option value="add">Add as new optional point</option>
                              </select>
                            </li>
                          ))}
                        </ol>
                        <p className={styles.muted}>Required flags and run-sheet points do not change here.</p>
                      </div>
                    </div>
                  </>
                )}
              </section>
            );
          })}
        </div>

        <Panel title={<span className={styles.panelTitle}>3 · Confirm</span>} className={styles.confirmPanel}>
          <div className={styles.confirmRow}>
            <span className={styles.muted}>
              {reviewed.length
                ? `${selectedTerms} terms selected across ${reviewed.length} product${reviewed.length === 1 ? "" : "s"}. Confirmed terms become STT phrase hints at the next stream start; point changes apply from the next session.`
                : "Run the Brief Agent for at least one product first."}
            </span>
            <Button variant="primary" disabled={confirming || reviewed.length === 0} onClick={() => void confirm()}>
              Confirm glossary
            </Button>
          </div>
          {confirmed !== null && (
            <p className={styles.okText} role="status" data-testid="setup-confirmed">
              Confirmed · version {confirmed}
            </p>
          )}
          {confirmError && (
            <p className={styles.errorText} role="alert">
              {confirmError}
            </p>
          )}
        </Panel>
      </main>
    </div>
  );
}
