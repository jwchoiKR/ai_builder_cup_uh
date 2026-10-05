// Onboarding API (P0, D-217/218/224): upload a product's files, poll the read, approve, start a show on the release.
import { API_BASE, ApiError, request } from "../../app/api";
import type { Session } from "../../app/types";

export type Evidence = { file: string; locator: string; quote: string };
export type TextItem = { text: string; evidence: Evidence[] };
export type MoneyItem = { currency: string; minor: number; kind: string; market: string | null; evidence: Evidence[] };
export type ProductRecord = {
  brand: string;
  product_name: string;
  category: string;
  category_evidence: Evidence[];
  language: string;
  generic_word: string | null;
  short_names: string[];
  variants: { variant_id: string; name: string; size_value: string | null; size_unit: string | null;
    market: string | null; prices: MoneyItem[]; evidence: Evidence[] }[];
  offers: { offer_id: string; kind: string; title: string; percent: string | null; amount: MoneyItem | null;
    rounding: string | null; duration_min: number | null; evidence: Evidence[] }[];
  ingredients: { name: string; amount_value: string | null; amount_unit: string | null; evidence: Evidence[] }[];
  ingredient_list_complete: boolean;
  approved_claims: TextItem[];
  not_approved_claims: TextItem[];
  avoid_saying: { say_not: string; say: string; evidence: Evidence[] }[];
  qualified_results: { statement: string; provenance: string; qualifier: string; marker: string | null;
    evidence: Evidence[] }[];
  cautions: TextItem[];
  how_to_use: TextItem[];
  key_facts: TextItem[];
  missing: string[];
  conflicts: { field: string; values: string[]; effective_dates: (string | null)[]; note: string;
    evidence: Evidence[] }[];
};
export type OnboardingResult = { record: ProductRecord; method: string; models: Record<string, string>;
  seconds: number; notes: string[]; files: { name: string; bytes: number }[] };
export type Line = { text?: string; say_not?: string; say?: string; reviewed: boolean };
export type Translations = Record<string, { approved_claims: Line[]; cautions: Line[]; avoid_saying: Line[] }>;
export type Job = { job_id: string; status: "queued" | "reading" | "done" | "failed"; files: string[];
  result: OnboardingResult | null; error: string | null };

export const onboardingApi = {
  async upload(files: File[], hints: string): Promise<{ job_id: string }> {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    form.append("hints", hints);
    const res = await fetch(`${API_BASE}/onboarding/jobs`, { method: "POST", body: form });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? "http_error", data?.error?.message ?? `HTTP ${res.status}`);
    return data;
  },
  job: (jobId: string) => request<Job>("GET", `/onboarding/jobs/${encodeURIComponent(jobId)}`),
  approve: (jobId: string, record?: ProductRecord, translations?: Translations) =>
    request<{ release_id: string; warnings: string[]; live?: { law: string; price: string; cautions: number;
      approved_claims: number; not_approved_claims: number; promos: number };
      translations?: Translations }>(
      "POST", `/onboarding/jobs/${encodeURIComponent(jobId)}/approve`,
      { ...(record ? { record } : {}), ...(translations ? { translations } : {}) }),
  // D-233: translations for review before approval, and what the show would get
  preview: (jobId: string, record?: ProductRecord) =>
    request<{ translations: Translations; live: { law?: string; price?: string; error?: string } }>(
      "POST", `/onboarding/jobs/${encodeURIComponent(jobId)}/preview`, record ? { record } : {}),
  startShow: (releaseId: string) => request<Session>("POST", "/sessions", { release_id: releaseId }),
};
