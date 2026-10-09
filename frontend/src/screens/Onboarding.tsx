// Product onboarding. Product documents and regulation documents go in separate boxes, one PDF each.
// Dropping a file is the only manual step before approval: the product PDF is uploaded and read on its own,
// the regulation PDF is uploaded on its own. A person approves the product and creates the release.
import { useState, type ReactNode } from "react";

import { Plus, X } from "lucide-react";

import { Button, Chip, Elapsed, Eyebrow, HubLink } from "../components";
import { PDF_ACCEPT, pdfOnly } from "../app/pdfOnly";
import { API_BASE, ApiError, request } from "../app/api";
import { navigate } from "../app/nav";
import styles from "./onboarding/onboarding.module.css";

const sizeLabel = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
const errorText = (step: string, e: unknown) => `${step} failed: ${e instanceof Error ? e.message : String(e)}`;

/** Drop a PDF on the box, or click it to choose one. Keyboard users reach the hidden input through the label. */
function DropZone({ testId, file, disabled, onFile }: {
  testId: string; file: File | null; disabled: boolean; onFile: (f: File | null) => void;
}) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pick = (files: File[]) => {
    const picked = pdfOnly(files.slice(0, 1));
    setError(picked.error);
    if (picked.files[0]) onFile(picked.files[0]);
  };
  return (
    <>
      <label className={[styles.drop, over && styles.dropOver, disabled && styles.dropDisabled].filter(Boolean).join(" ")}
             data-testid={`${testId}-drop`}
             onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
             onDragLeave={() => setOver(false)}
             onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) pick(Array.from(e.dataTransfer.files)); }}>
        <input type="file" accept={PDF_ACCEPT} className="visually-hidden" disabled={disabled}
               data-testid={`${testId}-file`}
               onChange={(e) => { pick(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
        {file
          ? <span className={styles.value}><b>{file.name}</b> <span className={styles.count}>{sizeLabel(file.size)}</span></span>
          : <span className={styles.muted}>Drop a PDF here, or click to choose one</span>}
        {file && !disabled && <span className={styles.muted}>Drop another PDF to replace it</span>}
      </label>
      {error && <p className={styles.error}>{error}</p>}
    </>
  );
}

/** What is running now, with the seconds since it started. */
function Working({ label, since }: { label: string; since: number }) {
  return (
    <p className={styles.status} role="status">
      {label} <Elapsed since={since} serverOffsetMs={0} format="mmss" className={styles.count} />
    </p>
  );
}

function Box({ title, note, testId, done, children }: {
  title: string; note: string; testId: string; done: boolean; children: ReactNode;
}) {
  return (
    <section className={[styles.block, done && styles.ok].filter(Boolean).join(" ")} data-testid={testId}>
      <h2 className={styles.blockTitle}>{title} {done && <Chip tone="ok">Done</Chip>}</h2>
      <p className={styles.muted}>{note}</p>
      {children}
    </section>
  );
}

type Uploaded = { product_id: string; file: string; bytes: number; gcs_uri: string };
type RegulationUploaded = { regulation_id: string; file: string; bytes: number; gcs_uri: string };

async function uploadPdf<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: form });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? "http_error", data?.error?.message ?? `HTTP ${res.status}`);
  return data;
}
const uploadProduct = (file: File) => uploadPdf<Uploaded>("/products", file);
const uploadRegulation = (file: File) => uploadPdf<RegulationUploaded>("/regulations", file);

type ProductInfo = { brand: string; product_name: string; category?: string; currency: string | null; list_price: string | null;
  live_price: string | null; points: { text: string; required: boolean }[] };
type ReadResult = { product_id: string; file: string; info: ProductInfo; seconds: number };

type HostLanguage = "en" | "ko";
const HOST_LANGUAGES: [HostLanguage, string][] = [["en", "ENG"], ["ko", "KR"]];
const readProduct = (productId: string, hostLanguage: HostLanguage) =>
  request<ReadResult>("POST", `/products/${encodeURIComponent(productId)}/read`, { host_language: hostLanguage });

type Approved = { product_id: string; approved_at: number; info: ProductInfo; warnings: string[] };
const approveProduct = (productId: string, info: ProductInfo) =>
  request<Approved>("POST", `/products/${encodeURIComponent(productId)}/approve`, { info });

/** The read as the person left it: blank prices and currency become null, blank points are dropped. */
const cleaned = (d: ProductInfo): ProductInfo => {
  const opt = (v: string | null) => v?.trim() || null;
  return { ...d, brand: d.brand.trim(), product_name: d.product_name.trim(),
    category: d.category?.trim() ?? "", currency: opt(d.currency),
    list_price: opt(d.list_price), live_price: opt(d.live_price),
    points: d.points.map((p) => ({ ...p, text: p.text.trim() })).filter((p) => p.text) };
};

/** One label: value row; the value reads as text and turns into an input on hover and focus. */
function FactRow({ label, value, onChange, disabled }: {
  label: string; value: string | null; onChange: (v: string) => void; disabled: boolean;
}) {
  return (
    <>
      <dt className={styles.factLabel}>{label}</dt>
      <dd className={styles.factValue}>
        <input className={styles.ghost} value={value ?? ""} placeholder="Not in the document" disabled={disabled}
               aria-label={label} onChange={(e) => onChange(e.target.value)} />
      </dd>
    </>
  );
}

/** The model's read, editable before approval: every value is edited in place, each point has its own
 * Required toggle. */
function ProductForm({ draft, onChange, disabled }: {
  draft: ProductInfo; onChange: (d: ProductInfo) => void; disabled: boolean;
}) {
  const set = (patch: Partial<ProductInfo>) => onChange({ ...draft, ...patch });
  const setPoint = (i: number, patch: Partial<ProductInfo["points"][number]>) =>
    set({ points: draft.points.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const required = draft.points.filter((p) => p.required).length;
  return (
    <div className={styles.sheet} data-testid="onb-product-form">
      <div>
        <input className={[styles.ghost, styles.brandInput].join(" ")} value={draft.brand} placeholder="Brand"
               aria-label="Brand" disabled={disabled} onChange={(e) => set({ brand: e.target.value })} />
        <input className={[styles.ghost, styles.nameInput].join(" ")} value={draft.product_name}
               placeholder="Product name" aria-label="Product name" disabled={disabled}
               onChange={(e) => set({ product_name: e.target.value })} />
      </div>
      <dl className={styles.facts}>
        <FactRow label="Category" value={draft.category ?? null} disabled={disabled} onChange={(v) => set({ category: v })} />
        <FactRow label="Currency" value={draft.currency} disabled={disabled} onChange={(v) => set({ currency: v })} />
        <FactRow label="Live price" value={draft.live_price} disabled={disabled} onChange={(v) => set({ live_price: v })} />
        <FactRow label="List price" value={draft.list_price} disabled={disabled} onChange={(v) => set({ list_price: v })} />
      </dl>
      <div className={styles.pointsHead}>
        <h4 className={styles.blockTitle}>Points</h4>
        <span className={styles.count}>{draft.points.length} · {required} required</span>
      </div>
      <ul className={styles.pointRows}>
        {draft.points.map((pt, i) => (
          <li key={i} className={styles.point}>
            <button type="button" className={[styles.reqToggle, pt.required && styles.reqOn].filter(Boolean).join(" ")}
                    aria-pressed={pt.required} disabled={disabled} title="Must the host say this?"
                    onClick={() => setPoint(i, { required: !pt.required })}>
              {pt.required ? "Required" : "Optional"}
            </button>
            <textarea className={[styles.ghost, styles.pointText].join(" ")} rows={Math.max(1, Math.ceil(pt.text.length / 70))} value={pt.text}
                      disabled={disabled} aria-label={`Point ${i + 1}`} placeholder="New point"
                      onChange={(e) => setPoint(i, { text: e.target.value })} />
            {!disabled && (
              <button type="button" className={styles.iconBtn} aria-label={`Remove point ${i + 1}`}
                      onClick={() => set({ points: draft.points.filter((_, j) => j !== i) })}><X size={14} aria-hidden /></button>
            )}
          </li>
        ))}
      </ul>
      {!disabled && (
        <button type="button" className={styles.addLink}
                onClick={() => set({ points: [...draft.points, { text: "", required: false }] })}>
          <Plus size={14} aria-hidden /> Add point
        </button>
      )}
    </div>
  );
}

type Busy = { label: string; since: number };

/** One product PDF: dropped → uploaded (POST /api/products) → read by one model call (POST .../read) → shown for
 * approval (POST .../approve). Upload and read run on their own; a person only approves. */
function ProductUpload({ title, onRead, onApproved, onRemove }: {
  title: string; onRead: (read: boolean) => void; onApproved: (productId: string | null) => void; onRemove?: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<Uploaded | null>(null);
  const [read, setRead] = useState<ReadResult | null>(null);
  const [draft, setDraft] = useState<ProductInfo | null>(null);
  const [approved, setApproved] = useState<Approved | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy | null>(null);
  const [hostLanguage, setHostLanguage] = useState<HostLanguage>("en");  // the STT terms are read for this language
  const step = async <T,>(label: string, fn: () => Promise<T>): Promise<T> => {
    setBusy({ label, since: Date.now() });
    try {
      return await fn();
    } finally {
      setBusy(null);
    }
  };
  // upload when not yet uploaded, then read; a failure stops here and "Try again" resumes from that step
  const uploadAndRead = async (f: File, up: Uploaded | null) => {
    setError(null);
    let current = "Upload";
    try {
      let u = up;
      if (!u) {
        u = await step("Uploading…", () => uploadProduct(f));
        setUploaded(u);
      }
      current = "Read";
      const productId = u.product_id;
      const r = await step("Reading the document (up to a minute)…", () => readProduct(productId, hostLanguage));
      setRead(r);
      setDraft(r.info);
      onRead(true);
    } catch (e) {
      setError(errorText(current, e));
    }
  };
  return (
    <Box title={title} note="One PDF of the product's information. It is read as soon as you drop it."
         testId="onb-product" done={approved !== null}>
      <div className={styles.actions}>
        {onRemove && <Button disabled={busy !== null} onClick={onRemove}>Remove product</Button>}
        <span className={styles.factLabel}>Host language</span>
        <div className={styles.segmented} role="radiogroup" aria-label="Host language">
          {HOST_LANGUAGES.map(([code, label]) => (
            <button key={code} type="button" role="radio" aria-checked={hostLanguage === code}
                    data-testid={`onb-host-lang-${code}`} disabled={busy !== null || approved !== null}
                    className={[styles.segment, hostLanguage === code && styles.segmentActive].filter(Boolean).join(" ")}
                    onClick={() => setHostLanguage(code)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <DropZone testId="onb-product" file={file} disabled={busy !== null || approved !== null}
                onFile={(f) => {
                  setFile(f); setUploaded(null); setRead(null); setDraft(null); setApproved(null);
                  onRead(false); onApproved(null);
                  if (f) void uploadAndRead(f, null);
                }} />
      {busy && <Working label={busy.label} since={busy.since} />}
      {error && (
        <div className={styles.actions}>
          <p className={styles.error}>{error}</p>
          {file && <Button disabled={busy !== null} data-testid="onb-product-retry"
                           onClick={() => void uploadAndRead(file, uploaded)}>Try again</Button>}
        </div>
      )}
      {read && draft && (
        <div className={styles.summary} data-testid="onb-product-info">
          <ProductForm draft={draft} onChange={setDraft} disabled={busy !== null || approved !== null} />
          <div className={styles.footer}>
            <Button variant="primary" disabled={busy !== null || approved !== null} data-testid="onb-product-approve"
                    onClick={() => {
                      setError(null);
                      step("Approving…", () => approveProduct(read.product_id, cleaned(draft))).then((a) => {
                        setApproved(a);
                        onApproved(a.product_id);
                      }).catch((e) => setError(errorText("Approve", e)));
                    }}>
              {approved ? "Approved" : "Approve"}
            </Button>
            {!approved && (
              <Button disabled={busy !== null} data-testid="onb-product-read"
                      onClick={() => file && void uploadAndRead(file, uploaded)}>
                Read again
              </Button>
            )}
            <span className={styles.footerNote}>Read in {read.seconds} s · click any text to edit</span>
          </div>
          {approved?.warnings.map((w) => <p key={w} className={styles.warning}>{w}</p>)}
        </div>
      )}
    </Box>
  );
}

/** One regulation PDF into the bucket (POST /api/regulations), uploaded as soon as it is dropped. */
function RegulationUpload({ onUploaded }: { onUploaded: (regulationId: string | null) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<RegulationUploaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [since, setSince] = useState<number | null>(null);
  const upload = async (f: File) => {
    setError(null);
    setSince(Date.now());
    try {
      const u = await uploadRegulation(f);
      setUploaded(u);
      onUploaded(u.regulation_id);
    } catch (e) {
      setError(errorText("Upload", e));
    } finally {
      setSince(null);
    }
  };
  return (
    <Box title="2 · Regulations" note="One PDF of the regulations that apply. Required for the show."
         testId="onb-regulation" done={uploaded !== null}>
      <DropZone testId="onb-regulation" file={file} disabled={since !== null}
                onFile={(f) => {
                  setFile(f); setUploaded(null); onUploaded(null);
                  if (f) void upload(f);
                }} />
      {since !== null && <Working label="Uploading…" since={since} />}
      {error && (
        <div className={styles.actions}>
          <p className={styles.error}>{error}</p>
          {file && <Button disabled={since !== null} data-testid="onb-regulation-retry"
                           onClick={() => void upload(file)}>Try again</Button>}
        </div>
      )}
    </Box>
  );
}

/** The four steps of a release, done or not, at the top of the page. */
function Steps({ items }: { items: [string, boolean][] }) {
  const next = items.findIndex(([, done]) => !done);
  return (
    <ol className={styles.steps} data-testid="onb-steps">
      {items.map(([label, done], i) => (
        <li key={label} className={[styles.step, done && styles.stepDone, i === next && styles.stepNext].filter(Boolean).join(" ")}
            aria-current={i === next ? "step" : undefined}>
          <span className={styles.stepMark}>{done ? "✓" : i + 1}</span> {label}
        </li>
      ))}
    </ol>
  );
}

type Slot = { key: number; read: boolean; productId: string | null };

export function Onboarding() {
  // several products share the one regulation PDF; each approved product becomes its own release
  const [slots, setSlots] = useState<Slot[]>([{ key: 0, read: false, productId: null }]);
  const setSlot = (key: number, patch: Partial<Slot>) =>
    setSlots((ss) => ss.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  const productIds = slots.map((s) => s.productId).filter((id): id is string => id !== null);
  const allApproved = productIds.length === slots.length;
  const [regulationId, setRegulationId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = [!allApproved && "approve every product", !regulationId && "upload the regulation PDF"].filter(Boolean);
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · PRODUCT ONBOARDING
        </Eyebrow>
        <Steps items={[
          ["Products read", slots.every((s) => s.read)],
          ["Products approved", allApproved],
          ["Regulations uploaded", regulationId !== null],
          ["Release created", false],
        ]} />
      </header>
      <div className={styles.grid}>
        <div className={styles.column}>
          {slots.map((s, i) => (
            <ProductUpload key={s.key} title={`1 · Product ${slots.length > 1 ? i + 1 : "information"}`}
                           onRead={(read) => setSlot(s.key, { read })}
                           onApproved={(productId) => setSlot(s.key, { productId })}
                           onRemove={slots.length > 1 ? () => setSlots((ss) => ss.filter((x) => x.key !== s.key)) : undefined} />
          ))}
          <button type="button" className={styles.addLink} data-testid="onb-product-add"
                  onClick={() => setSlots((ss) => [...ss, { key: Math.max(...ss.map((x) => x.key)) + 1, read: false, productId: null }])}>
            <Plus size={14} aria-hidden /> Add product
          </button>
        </div>
        <RegulationUpload onUploaded={setRegulationId} />
      </div>
      {/* a release needs both (the server checks the same); the show starts from the hub's Pick products */}
      <section className={styles.block} data-testid="onb-ready">
        <h2 className={styles.blockTitle}>3 · Release</h2>
        <p className={styles.muted}>
          {missing.length ? `To create the release, ${missing.join(" and ")}.` : `Ready. ${productIds.length > 1 ? `${productIds.length} releases appear` : "The release appears"} in the hub's Pick products.`}
        </p>
        <div className={styles.actions}>
          <Button variant="primary" disabled={starting || !allApproved || !regulationId} data-testid="onb-release"
                  onClick={async () => {
                    setStarting(true);
                    setError(null);
                    try {
                      for (const id of productIds)  // one release per product, all on the same regulation
                        await request("POST", `/products/${encodeURIComponent(id)}/release`,
                          { regulation_id: regulationId });
                      navigate("/");  // the hub's Pick products lists the release
                    } catch (e) {
                      setError(errorText("Release", e));
                    } finally {
                      setStarting(false);
                    }
                  }}>
            {starting ? "Creating…" : productIds.length > 1 ? `Create ${productIds.length} releases` : "Create release"}
          </Button>
        </div>
        {error && <p className={styles.error}>{error}</p>}
      </section>
    </div>
  );
}

export default Onboarding;
