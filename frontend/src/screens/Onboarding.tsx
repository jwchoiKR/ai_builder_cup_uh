// Product onboarding: rebuilt from scratch. Product documents and regulation documents are uploaded in separate
// boxes, one PDF each. Product: uploaded to the bucket, read by one model call, approved (new API, steps 1-4).
// Regulations: one PDF uploaded to the bucket. A show needs both.
import { useState, type ReactNode } from "react";

import { Button, Chip, Eyebrow, HubLink } from "../components";
import { PDF_ACCEPT, pdfOnly } from "../app/pdfOnly";
import { API_BASE, ApiError, request } from "../app/api";
import { navigate } from "../app/nav";
import styles from "./onboarding/onboarding.module.css";

function UploadBox({ title, note, testId, onFile, children }: {
  title: string; note: string; testId: string; onFile?: (f: File | null) => void; children?: ReactNode;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <section className={styles.block} data-testid={testId}>
      <h2 className={styles.blockTitle}>{title}</h2>
      <p className={styles.muted}>{note}</p>
      <input type="file" accept={PDF_ACCEPT} data-testid={`${testId}-file`}
             onChange={(e) => {
               const pick = pdfOnly(Array.from(e.target.files ?? []).slice(0, 1));
               setError(pick.error);
               setFile(pick.files[0] ?? null);
               onFile?.(pick.files[0] ?? null);
               if (pick.error) e.target.value = "";
             }} />
      {file && <p className={styles.value}>{file.name}</p>}
      {error && <p className={styles.error}>{error}</p>}
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

/** The rebuilt onboarding, steps 1-3: one product PDF into the bucket (POST /api/products), one model read
 * (POST /api/products/{id}/read), and what it found. */
function ProductUpload({ onApproved }: { onApproved: (productId: string | null) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<Uploaded | null>(null);
  const [read, setRead] = useState<ReadResult | null>(null);
  const [approved, setApproved] = useState<Approved | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"upload" | "read" | "approve" | null>(null);
  const run = async (kind: "upload" | "read" | "approve", fn: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const info = read?.info;
  return (
    <UploadBox title="Product information" note="One PDF of the product's information." testId="onb-product"
               onFile={(f) => { setFile(f); setUploaded(null); setRead(null); setApproved(null); setError(null); onApproved(null); }}>
      <div className={styles.actions}>
        <Button variant="primary" disabled={busy !== null || !file || uploaded !== null} data-testid="onb-product-upload"
                onClick={() => run("upload", async () => setUploaded(await uploadProduct(file!)))}>
          {busy === "upload" ? "Uploading…" : "Upload"}
        </Button>
        <Button variant="primary" disabled={busy !== null || !uploaded} data-testid="onb-product-read"
                onClick={() => run("read", async () => {
                  setRead(await readProduct(uploaded!.product_id));
                  setApproved(null);
                  onApproved(null);
                })}>
          {busy === "read" ? "Reading… up to a minute" : read ? "Read again" : "Read"}
        </Button>
      </div>
      {uploaded && (
        <p className={styles.value} data-testid="onb-product-uploaded">
          Uploaded <b>{uploaded.file}</b> as {uploaded.product_id}
        </p>
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
          <p className={styles.muted}>Read in {read!.seconds} s</p>
          <div className={styles.actions}>
            <Button variant="primary" disabled={busy !== null || approved !== null} data-testid="onb-product-approve"
                    onClick={() => run("approve", async () => {
                      const a = await approveProduct(read!.product_id);
                      setApproved(a);
                      onApproved(a.product_id);
                    })}>
              {busy === "approve" ? "Approving…" : approved ? "Approved" : "Approve"}
            </Button>
          </div>
          {approved?.warnings.map((w) => <p key={w} className={styles.warning}>{w}</p>)}
        </div>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </UploadBox>
  );
}

/** One regulation PDF into the bucket (POST /api/regulations). A show needs one. */
function RegulationUpload({ onUploaded }: { onUploaded: (regulationId: string | null) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<RegulationUploaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <UploadBox title="Regulations" note="One PDF of the regulations that apply. Required for the show."
               testId="onb-regulation"
               onFile={(f) => { setFile(f); setUploaded(null); setError(null); onUploaded(null); }}>
      <div className={styles.actions}>
        <Button variant="primary" disabled={busy || !file || uploaded !== null} data-testid="onb-regulation-upload"
                onClick={async () => {
                  setBusy(true);
                  setError(null);
                  try {
                    const u = await uploadRegulation(file!);
                    setUploaded(u);
                    onUploaded(u.regulation_id);
                  } catch (e) {
                    setError(e instanceof Error ? e.message : String(e));
                  } finally {
                    setBusy(false);
                  }
                }}>
          {busy ? "Uploading…" : "Upload"}
        </Button>
      </div>
      {uploaded && (
        <p className={styles.value} data-testid="onb-regulation-uploaded">
          Uploaded <b>{uploaded.file}</b> as {uploaded.regulation_id}
        </p>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </UploadBox>
  );
}

export function Onboarding() {
  const [productId, setProductId] = useState<string | null>(null);
  const [regulationId, setRegulationId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · PRODUCT ONBOARDING
        </Eyebrow>
      </header>
      <ProductUpload onApproved={setProductId} />
      <RegulationUpload onUploaded={setRegulationId} />
      {/* a release needs both (the server checks the same); the show starts from the hub's Pick products */}
      <section className={styles.block} data-testid="onb-ready">
        <h2 className={styles.blockTitle}>Before the show</h2>
        <ul className={styles.rows}>
          <li className={styles.value}>{productId ? "✓" : "○"} Product approved</li>
          <li className={styles.value}>{regulationId ? "✓" : "○"} Regulation file uploaded</li>
        </ul>
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
                      setError(e instanceof Error ? e.message : String(e));
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
