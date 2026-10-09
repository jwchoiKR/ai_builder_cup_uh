// Product onboarding: rebuilt from scratch. Product documents and regulation documents are uploaded in separate
// boxes, one PDF each. Product: uploaded to the bucket, then read by one model call (new API, steps 1-3).
// Regulations: picking only.
import { useState, type ReactNode } from "react";

import { Button, Chip, Eyebrow, HubLink } from "../components";
import { PDF_ACCEPT, pdfOnly } from "../app/pdfOnly";
import { API_BASE, ApiError, request } from "../app/api";
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

async function uploadProduct(file: File): Promise<Uploaded> {
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await fetch(`${API_BASE}/products`, { method: "POST", body: form });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? "http_error", data?.error?.message ?? `HTTP ${res.status}`);
  return data;
}

type ProductInfo = { brand: string; product_name: string; currency: string | null; list_price: string | null;
  live_price: string | null; points: { text: string; required: boolean }[] };
type ReadResult = { product_id: string; file: string; info: ProductInfo; seconds: number };

const readProduct = (productId: string) =>
  request<ReadResult>("POST", `/products/${encodeURIComponent(productId)}/read`, {});

/** The rebuilt onboarding, steps 1-3: one product PDF into the bucket (POST /api/products), one model read
 * (POST /api/products/{id}/read), and what it found. */
function ProductUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<Uploaded | null>(null);
  const [read, setRead] = useState<ReadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"upload" | "read" | null>(null);
  const run = async (kind: "upload" | "read", fn: () => Promise<void>) => {
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
               onFile={(f) => { setFile(f); setUploaded(null); setRead(null); setError(null); }}>
      <div className={styles.actions}>
        <Button variant="primary" disabled={busy !== null || !file || uploaded !== null} data-testid="onb-product-upload"
                onClick={() => run("upload", async () => setUploaded(await uploadProduct(file!)))}>
          {busy === "upload" ? "Uploading…" : "Upload"}
        </Button>
        <Button variant="primary" disabled={busy !== null || !uploaded} data-testid="onb-product-read"
                onClick={() => run("read", async () => setRead(await readProduct(uploaded!.product_id)))}>
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
        </div>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </UploadBox>
  );
}

export function Onboarding() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · PRODUCT ONBOARDING
        </Eyebrow>
      </header>
      <ProductUpload />
      <UploadBox title="Regulations" note="One PDF of the regulations that apply." testId="onb-regulation" />
    </div>
  );
}

export default Onboarding;
