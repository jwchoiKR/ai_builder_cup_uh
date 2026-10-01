// Pre-broadcast setup page (DEV_SPEC §12.7): documents, Brief Agent results, glossary confirmation.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ThemeName } from "../../app/theme";
import type { PrompterPoint, Product } from "../../app/types";
import { Button, Chip, Eyebrow, Panel, ThemeToggle } from "../../components";
import type { BriefRecord, ConfirmProduct, GlossaryState, PointChoice, SetupClient, SetupDocument } from "./setupApi";
import styles from "./setup.module.css";

type Choice = "" | "add" | `replace:${string}`;

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const time = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export interface SetupViewProps {
  products: Product[];
  brand: string;
  client: SetupClient;
  theme: ThemeName;
  onToggleTheme?: () => void;
}

export function SetupView({ products, brand, client, theme, onToggleTheme }: SetupViewProps) {
  const [docs, setDocs] = useState<SetupDocument[]>([]);
  const [docMessage, setDocMessage] = useState<{ tone: "ok" | "risk"; text: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [glossary, setGlossary] = useState<GlossaryState | null>(null);
  const [briefs, setBriefs] = useState<Record<string, BriefRecord | null>>({});
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [briefErrors, setBriefErrors] = useState<Record<string, string | null>>({});
  const [include, setInclude] = useState<Record<string, Record<string, boolean>>>({});
  const [choices, setChoices] = useState<Record<string, Record<number, Choice>>>({});
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState<number | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadDocs = useCallback(async () => {
    try {
      setDocs((await client.documents()).documents);
    } catch (e) {
      setDocMessage({ tone: "risk", text: errorText(e) });
    }
  }, [client]);

  useEffect(() => {
    void loadDocs();
    client.glossary().then(setGlossary, () => setGlossary(null));
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

  const onUpload = async (file: File) => {
    setUploading(true);
    setDocMessage(null);
    try {
      const res = await client.upload(file, file.name);
      setDocMessage({ tone: "ok", text: res.status === "already_indexed" ? "Already indexed" : res.message });
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
      setInclude((i) => ({ ...i, [productId]: {} }));
      setChoices((c) => ({ ...c, [productId]: {} }));
    } catch (e) {
      setBriefErrors((errs) => ({ ...errs, [productId]: errorText(e) })); // the previous result stays
    } finally {
      setRunning((r) => ({ ...r, [productId]: false }));
    }
  };

  const currentPoints = (p: Product): PrompterPoint[] => glossary?.prompter_points?.[p.product_id] ?? p.prompter_points;
  const reviewed = products.filter((p) => briefs[p.product_id]?.output);
  const selectedTerms = reviewed.reduce(
    (n, p) => n + (briefs[p.product_id]?.output?.glossary ?? []).filter((t) => include[p.product_id]?.[t.term] ?? true).length,
    0,
  );

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
        glossary: out.glossary.map((t) => ({ ...t, include: include[p.product_id]?.[t.term] ?? true })),
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
          <Eyebrow>Pre-broadcast</Eyebrow>
          <span className={styles.title}>Setup</span>
          <span className={styles.subtitle}>{brand} · Product documents, Brief Agent and glossary</span>
        </div>
        <div className={styles.headerActions}>
          <Chip tone={glossary?.version ? "ok" : "neutral"} data-testid="setup-glossary-version">
            {glossary
              ? glossary.version
                ? `Glossary version ${glossary.version}`
                : "Default glossary (version 0)"
              : "Glossary"}
          </Chip>
          {onToggleTheme && <ThemeToggle theme={theme} onToggle={onToggleTheme} />}
        </div>
      </header>

      <main className={styles.body}>
        <Panel
          title={<span className={styles.panelTitle}>1 · Documents</span>}
          actions={
            <>
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                hidden
                data-testid="setup-file-input"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void onUpload(f);
                }}
              />
              <Button disabled={uploading} onClick={() => fileInput.current?.click()}>
                {uploading ? "Uploading…" : "Upload PDF"}
              </Button>
            </>
          }
        >
          <table className={styles.table} data-testid="setup-documents">
            <thead>
              <tr>
                <th>Document</th>
                <th>Product</th>
                <th>Pages</th>
                <th>Index</th>
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
                    No documents.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {docMessage && (
            <p className={docMessage.tone === "ok" ? styles.okText : styles.errorText} role="status">
              {docMessage.text}
            </p>
          )}
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
                    <table className={styles.table} data-testid={`setup-glossary-${p.product_id}`}>
                      <thead>
                        <tr>
                          <th>Include</th>
                          <th>Term</th>
                          <th>Kind</th>
                          <th>Spoken forms</th>
                          <th>Source section</th>
                        </tr>
                      </thead>
                      <tbody>
                        {out.glossary.map((t) => {
                          const on = include[p.product_id]?.[t.term] ?? true;
                          return (
                            <tr key={t.term} className={on ? undefined : styles.excluded}>
                              <td>
                                <input
                                  type="checkbox"
                                  checked={on}
                                  aria-label={`Include ${t.term}`}
                                  onChange={(e) =>
                                    setInclude((all) => ({
                                      ...all,
                                      [p.product_id]: { ...all[p.product_id], [t.term]: e.target.checked },
                                    }))
                                  }
                                />
                              </td>
                              <td className={styles.term}>{t.term}</td>
                              <td>
                                <Chip>{t.kind}</Chip>
                              </td>
                              <td className={styles.muted}>{t.spoken_forms.join(", ")}</td>
                              <td className={styles.muted}>{t.source_section}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>

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
