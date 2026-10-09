// Product onboarding. Product documents and regulation documents go in separate boxes, one PDF each.
// Dropping a file is the only manual step before approval: the product PDF is uploaded and read on its own,
// the regulation PDF is uploaded on its own. A person approves the product and creates the release.
import { useState, type ReactNode } from "react";

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

type ProductInfo = { brand: string; product_name: string; currency: string | null; list_price: string | null;
  live_price: string | null; points: { text: string; required: boolean }[] };
type ReadResult = { product_id: string; file: string; info: ProductInfo; seconds: number };

const readProduct = (productId: string) =>
  request<ReadResult>("POST", `/products/${encodeURIComponent(productId)}/read`, {});
type Approved = { product_id: string; approved_at: number; info: ProductInfo; warnings: string[] };
const approveProduct = (productId: string) =>
  request<Approved>("POST", `/products/${encodeURIComponent(productId)}/approve`, {});

type Busy = { label: string; since: number };

/** One product PDF: dropped → uploaded (POST /api/products) → read by one model call (POST .../read) → shown for
 * approval (POST .../approve). Upload and read run on their own; a person only approves. */
function ProductUpload({ onRead, onApproved }: {
  onRead: (read: boolean) => void; onApproved: (productId: string | null) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<Uploaded | null>(null);
  const [read, setRead] = useState<ReadResult | null>(null);
  const [approved, setApproved] = useState<Approved | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy | null>(null);
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
      setRead(await step("Reading the document (up to a minute)…", () => readProduct(productId)));
      onRead(true);
    } catch (e) {
      setError(errorText(current, e));
    }
  };
  const info = read?.info;
  return (
    <Box title="1 · Product information" note="One PDF of the product's information. It is read as soon as you drop it."
         testId="onb-product" done={approved !== null}>
      <DropZone testId="onb-product" file={file} disabled={busy !== null || approved !== null}
                onFile={(f) => {
                  setFile(f); setUploaded(null); setRead(null); setApproved(null);
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
      {info && (
        <div className={styles.summary} data-testid="onb-product-info">
          <h3 className={styles.product}>{info.brand} · {info.product_name}</h3>
          <p className={styles.value}>
            {info.live_price ? `${info.currency ?? ""} ${info.live_price} live` : "No price in the document"}
            {info.list_price && info.list_price !== info.live_price ? ` · ${info.list_price} list` : ""}
          </p>
          <h4 className={styles.blockTitle}>
            Points <span className={styles.count}>{info.points.length}</span>
          </h4>
          <ul className={styles.rows}>
            {info.points.map((pt, i) => (
              <li key={i} className={styles.inline}>
                {pt.required && <Chip tone="risk">Required</Chip>}
                <span className={styles.value}>{pt.text}</span>
              </li>
            ))}
          </ul>
          <p className={styles.muted}>Read in {read!.seconds} s. Check the points, then approve.</p>
          <div className={styles.actions}>
            <Button variant="primary" disabled={busy !== null || approved !== null} data-testid="onb-product-approve"
                    onClick={() => {
                      setError(null);
                      step("Approving…", () => approveProduct(read!.product_id)).then((a) => {
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
      {uploaded && (
        <p className={styles.value} data-testid="onb-regulation-uploaded">
          Uploaded <b>{uploaded.file}</b> ({sizeLabel(uploaded.bytes)})
        </p>
      )}
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

export function Onboarding() {
  const [productRead, setProductRead] = useState(false);
  const [productId, setProductId] = useState<string | null>(null);
  const [regulationId, setRegulationId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = [!productId && "approve the product", !regulationId && "upload the regulation PDF"].filter(Boolean);
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · PRODUCT ONBOARDING
        </Eyebrow>
        <Steps items={[
          ["Product read", productRead],
          ["Product approved", productId !== null],
          ["Regulations uploaded", regulationId !== null],
          ["Release created", false],
        ]} />
      </header>
      <div className={styles.grid}>
        <ProductUpload onRead={setProductRead} onApproved={setProductId} />
        <RegulationUpload onUploaded={setRegulationId} />
      </div>
      {/* a release needs both (the server checks the same); the show starts from the hub's Pick products */}
      <section className={styles.block} data-testid="onb-ready">
        <h2 className={styles.blockTitle}>3 · Release</h2>
        <p className={styles.muted}>
          {missing.length ? `To create the release, ${missing.join(" and ")}.` : "Ready. The release appears in the hub's Pick products."}
        </p>
        <div className={styles.actions}>
          <Button variant="primary" disabled={starting || !productId || !regulationId} data-testid="onb-release"
                  onClick={async () => {
                    setStarting(true);
                    setError(null);
                    try {
                      await request("POST", `/products/${encodeURIComponent(productId!)}/release`,
                        { regulation_id: regulationId });
                      navigate("/");  // the hub's Pick products lists the release
                    } catch (e) {
                      setError(errorText("Release", e));
                    } finally {
                      setStarting(false);
                    }
                  }}>
            {starting ? "Creating…" : "Create release"}
          </Button>
        </div>
        {error && <p className={styles.error}>{error}</p>}
      </section>
    </div>
  );
}

export default Onboarding;
