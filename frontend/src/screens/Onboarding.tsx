// Product onboarding: rebuilt from scratch. Product documents and regulation documents are uploaded in separate
// boxes, one PDF each. Product: uploaded to the bucket (new API, step 1). Regulations: picking only.
import { useState, type ReactNode } from "react";

import { Button, Eyebrow, HubLink } from "../components";
import { PDF_ACCEPT, pdfOnly } from "../app/pdfOnly";
import { API_BASE, ApiError } from "../app/api";
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

/** Step 1 of the rebuilt onboarding: one product PDF into the onboarding bucket (POST /api/products). */
function ProductUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<Uploaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <UploadBox title="Product information" note="One PDF of the product's information." testId="onb-product"
               onFile={(f) => { setFile(f); setUploaded(null); setError(null); }}>
      <div className={styles.actions}>
        <Button variant="primary" disabled={busy || !file || uploaded !== null} data-testid="onb-product-upload"
                onClick={async () => {
                  setBusy(true);
                  setError(null);
                  try {
                    setUploaded(await uploadProduct(file!));
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
        <p className={styles.value} data-testid="onb-product-uploaded">
          Uploaded <b>{uploaded.file}</b> as {uploaded.product_id}
        </p>
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
