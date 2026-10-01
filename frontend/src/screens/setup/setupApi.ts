// /api/setup calls (DEV_SPEC §11.1, §12.7).
import { API_BASE, ApiError, request } from "../../app/api";
import type { PrompterPoint } from "../../app/types";

export type GlossaryKind = "brand" | "product" | "ingredient" | "technical" | "value";

export interface GlossaryTerm {
  term: string;
  kind: GlossaryKind;
  spoken_forms: string[];
  source_section: string;
}

export interface PointDraft {
  text: string;
  required: boolean;
  source_section: string;
}

export interface BriefRecord {
  product_id: string;
  status: "ok" | "timeout" | "error" | "invalid";
  output: { product_id: string; glossary: GlossaryTerm[]; prompter_points: PointDraft[]; reason: string } | null;
  error: string | null;
  latency_ms: number;
  ran_at: number;
}

export interface SetupDocument {
  name: string;
  product_id: string | null;
  pages: number;
  sha256: string;
  size: number | null;
  source: "shipped" | "upload";
  status: string;
  uploaded_at?: number;
}

export interface GlossaryState {
  version: number;
  terms: GlossaryTerm[];
  confirmed_at: number | null;
  confirmed_products: string[];
  prompter_points?: Record<string, PrompterPoint[]>;
}

export interface PointChoice {
  text: string;
  action: "replace" | "add";
  point_id?: string;
  source_section?: string;
}

export interface ConfirmProduct {
  glossary: (GlossaryTerm & { include: boolean })[];
  prompter_points: PointChoice[];
}

export interface UploadResult {
  status: "already_indexed" | "indexed" | "manual_import";
  message: string;
  name?: string;
  product_id?: string;
  passages?: number;
  doc_version?: number;
}

async function upload(file: Blob, name: string): Promise<UploadResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/setup/documents?filename=${encodeURIComponent(name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: file,
    });
  } catch (e) {
    throw new ApiError(0, "network_error", e instanceof Error ? e.message : "Network error");
  }
  const data = (await res.json().catch(() => null)) as (UploadResult & { error?: { code?: string; message?: string } }) | null;
  if (!res.ok) {
    throw new ApiError(res.status, data?.error?.code ?? "http_error", data?.error?.message ?? `HTTP ${res.status}`);
  }
  return data as UploadResult;
}

async function getBrief(productId: string): Promise<BriefRecord | null> {
  try {
    return await request<BriefRecord>("GET", `/setup/brief/${encodeURIComponent(productId)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const setupApi = {
  documents: () => request<{ documents: SetupDocument[]; doc_version: number }>("GET", "/setup/documents"),
  upload,
  runBrief: (productId: string) => request<BriefRecord>("POST", "/setup/brief/run", { product_id: productId }),
  getBrief,
  confirmAll: (products: Record<string, ConfirmProduct>) =>
    request<GlossaryState>("POST", "/setup/glossary/confirm", { products }),
  glossary: () => request<GlossaryState>("GET", "/setup/glossary"),
};

export type SetupClient = typeof setupApi;
