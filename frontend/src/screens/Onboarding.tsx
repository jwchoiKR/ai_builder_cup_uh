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
const MAX_PDF_BYTES = 20 * 1024 * 1024;  // same per-file cap as the server (backend/app/api/products.py MAX_BYTES)
const errorText = (step: string, e: unknown) => `${step} failed: ${e instanceof Error ? e.message : String(e)}`;

/** Drop a PDF on the box, or click it to choose one. Keyboard users reach the hidden input through the label. */
function DropZone({ testId, file, disabled, onFile }: {
  testId: string; file: File | null; disabled: boolean; onFile: (f: File | null) => void;
}) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pick = (files: File[]) => {
    const picked = pdfOnly(files.slice(0, 1));
    const f = picked.files[0];
    if (f && f.size > MAX_PDF_BYTES) {
      setError(`${f.name}: larger than ${MAX_PDF_BYTES / 1024 / 1024} MB`);
      return;
    }
    setError(picked.error);
    if (f) onFile(f);
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

function Box({ title, note, testId, done, onRemove, children }: {
  title: string; note: string; testId: string; done: boolean; onRemove?: () => void; children: ReactNode;
}) {
  return (
    <section className={[styles.block, done && styles.ok].filter(Boolean).join(" ")} data-testid={testId}>
      <h2 className={styles.blockTitle}>{title} {done && <Chip tone="ok">Done</Chip>}
        {onRemove && <button type="button" className={styles.cardClose} aria-label={`Remove ${title}`}
                             onClick={onRemove}><X size={16} aria-hidden /></button>}
      </h2>
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

type ProductInfo = { brand: string; product_name: string; category?: string; currency: string | null;
  points: { text: string; required: boolean }[]; variants: PriceOption[] };
type PriceOption = { label: string; list_price: string | null; live_price: string | null };
type ReadResult = { product_id: string; file: string; info: ProductInfo; seconds: number };

type HostLanguage = "en" | "ko";
const HOST_LANGUAGES: [HostLanguage, string][] = [["en", "ENG"], ["ko", "KR"]];
const readProduct = (productId: string, hostLanguage: HostLanguage) =>
  request<ReadResult>("POST", `/products/${encodeURIComponent(productId)}/read`, { host_language: hostLanguage });

type Approved = { product_id: string; approved_at: number; info: ProductInfo; warnings: string[] };
const approveProduct = (productId: string, info: ProductInfo) =>
  request<Approved>("POST", `/products/${encodeURIComponent(productId)}/approve`, { info });

/** The read as the person left it: blank currency becomes null, blank prices become null, blank points and
 * options are dropped. */
const cleaned = (d: ProductInfo): ProductInfo => {
  const opt = (v: string | null) => v?.trim() || null;
  return { ...d, brand: d.brand.trim(), product_name: d.product_name.trim(),
    category: d.category?.trim() ?? "", currency: opt(d.currency),
    variants: d.variants.map((v) => ({ label: v.label.trim(), list_price: opt(v.list_price), live_price: opt(v.live_price) }))
      .filter((v) => v.label || v.list_price || v.live_price),
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
  const variants = draft.variants;
  const cur = draft.currency?.trim() ? ` (${draft.currency.trim()})` : "";
  const setVariant = (i: number, patch: Partial<PriceOption>) =>
    set({ variants: variants.map((v, j) => (j === i ? { ...v, ...patch } : v)) });
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
      </dl>
      <div className={styles.pointsHead}>
        <h4 className={styles.blockTitle}>Prices</h4>
        <span className={styles.count}>{variants.length} {variants.length === 1 ? "option" : "options"}</span>
      </div>
      <div className={styles.priceTable} data-testid="onb-price-options">
        <div className={styles.priceHead}>
          <span>Option</span><span className={styles.num}>Live price{cur}</span><span className={styles.num}>List price{cur}</span><span />
        </div>
        {variants.map((v, i) => (
          <div key={i} className={styles.priceRow}>
            <input className={styles.ghost} value={v.label} placeholder="One price" aria-label={`Option ${i + 1}`}
                   disabled={disabled} onChange={(e) => setVariant(i, { label: e.target.value })} />
            <input className={[styles.ghost, styles.num, styles.live].join(" ")} value={v.live_price ?? ""} placeholder="—"
                   aria-label={`Option ${i + 1} live price`} disabled={disabled} inputMode="decimal"
                   onChange={(e) => setVariant(i, { live_price: e.target.value })} />
            <input className={[styles.ghost, styles.num].join(" ")} value={v.list_price ?? ""} placeholder="—"
                   aria-label={`Option ${i + 1} list price`} disabled={disabled} inputMode="decimal"
                   onChange={(e) => setVariant(i, { list_price: e.target.value })} />
            {disabled ? <span /> : (
              <button type="button" className={styles.iconBtn} aria-label={`Remove option ${i + 1}`}
                      onClick={() => set({ variants: variants.filter((_, j) => j !== i) })}><X size={14} aria-hidden /></button>
            )}
          </div>
        ))}
      </div>
      {!disabled && (
        <button type="button" className={styles.addLink}
                onClick={() => set({ variants: [...variants, { label: "", list_price: null, live_price: null }] })}>
          <Plus size={14} aria-hidden /> Add option
        </button>
      )}
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
  const [rejected, setRejected] = useState<string | null>(null);  // the file the read found no product in
  const [busy, setBusy] = useState<Busy | null>(null);
  const [hostLanguage, setHostLanguage] = useState<HostLanguage>("en");  // the points and STT terms are read for this language
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
    setRejected(null);
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
      if (e instanceof ApiError && e.code === "not_product_document") setRejected(f.name);  // a retry would read it the same
      else setError(errorText(current, e));
    }
  };
  return (
    <Box title={title} note="One PDF of the product's information. It is read as soon as you drop it."
         testId="onb-product" done={approved !== null} onRemove={onRemove}>
      <div className={styles.actions}>
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
      {rejected && (
        <div className={styles.rejected} role="alert" data-testid="onb-product-rejected">
          <p className={styles.rejectedTitle}>This is not a product document</p>
          <p className={styles.muted}>
            No product to sell was found in <strong>{rejected}</strong>, so it cannot be used.
            Drop the product's own PDF (product sheet, spec, label or catalog page) in the box above.
          </p>
        </div>
      )}
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
    <Box title="Regulations" note="One PDF of the regulations that apply. Required for the show."
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

/** One stage of the page on the left rail (products, regulations, release, done): its mark, then the line down to the next stage. */
function Stage({ mark, done, next, last, children }: {
  mark: string; done: boolean; next: boolean; last?: boolean; children?: ReactNode;
}) {
  return (
    <div className={[styles.stage, done && styles.stageDone, last && styles.stageLast].filter(Boolean).join(" ")}
         aria-current={next ? "step" : undefined}>
      <span className={[styles.stageMark, next && styles.stageNext].filter(Boolean).join(" ")}>{done ? "✓" : mark}</span>
      <div className={styles.stageBody}>{children}</div>
    </div>
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
      </header>
      <Stage mark="1" done={allApproved} next={!allApproved}>
        {slots.map((s, i) => (
          <ProductUpload key={s.key} title={`Product ${slots.length > 1 ? i + 1 : "information"}`}
                         onRead={(read) => setSlot(s.key, { read })}
                         onApproved={(productId) => setSlot(s.key, { productId })}
                         onRemove={slots.length > 1 ? () => setSlots((ss) => ss.filter((x) => x.key !== s.key)) : undefined} />
        ))}
        <button type="button" className={styles.addLink} data-testid="onb-product-add"
                onClick={() => setSlots((ss) => [...ss, { key: Math.max(...ss.map((x) => x.key)) + 1, read: false, productId: null }])}>
          <Plus size={14} aria-hidden /> Add product
        </button>
      </Stage>
      <Stage mark="2" done={regulationId !== null} next={allApproved && regulationId === null}>
        <RegulationUpload onUploaded={setRegulationId} />
      </Stage>
      <Stage mark="3" done={false} next={!missing.length}>
        {/* a release needs both (the server checks the same); the show starts from the hub's Pick products */}
        <section className={styles.block} data-testid="onb-ready">
          <h2 className={styles.blockTitle}>Release</h2>
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
      </Stage>
      <Stage mark="" done={false} next={false} last>
        <span className={styles.stageEnd}>Done</span>
      </Stage>
    </div>
  );
}

export default Onboarding;
