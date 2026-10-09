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
export type CheckItem = { group: string; label: string; reason: string };
export type OnboardingResult = { record: ProductRecord; method: string; models: Record<string, string>;
  seconds: number; notes: string[]; files: { name: string; bytes: number }[];
  verify_mode?: string; checks?: CheckItem[];
  check_summary?: { to_check: number; by_group: Record<string, number>; before?: number; collapsed?: number;
    auto_accepted?: number };
  // D-254 lean: the rest of the risk items (folded) and the caution-pass cautions accepted with a verified source
  checks_collapsed?: CheckItem[]; auto_accepted?: { label: string; source: string }[] };
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
      approved_claims: number; not_approved_claims: number; promos: number; brief?: { status: string } };
      translations?: Translations }>(
      "POST", `/onboarding/jobs/${encodeURIComponent(jobId)}/approve`,
      { ...(record ? { record } : {}), ...(translations ? { translations } : {}) }),
  // D-233: translations for review before approval, and what the show would get
  preview: (jobId: string, record?: ProductRecord) =>
    request<{ translations: Translations; live: { law?: string; price?: string; error?: string } }>(
      "POST", `/onboarding/jobs/${encodeURIComponent(jobId)}/preview`, record ? { record } : {}),
  // D-279: one release, or 2-3 in segment order
  startShow: (releaseIds: string[]) => request<Session>("POST", "/sessions",
    releaseIds.length === 1 ? { release_id: releaseIds[0] } : { release_ids: releaseIds }),
  // D-264: approved products a show can start from, newest first (also after a cold start)
  // rebuilt onboarding: its releases (an approved product with a regulation file) first, then the old ones
  releases: async () => {
    const [fresh, old] = await Promise.all([request<ReleaseRow[]>("GET", "/products/releases").catch(() => []),
      request<ReleaseRow[]>("GET", "/onboarding/releases")]);
    return [...fresh, ...old];
  },
  // D-266: the release's brief (STT names, prompter points) runs after approval: done, running, failed (...), none
  briefStatus: (releaseId: string) =>
    request<{ status: string }>("GET", `/onboarding/releases/${encodeURIComponent(releaseId)}/brief`),
};
// D-359: regulation packs (read-only list), and the existing law-pack upload, job and approval endpoints
export type LawJob = { job_id: string; status: "queued" | "reading" | "done" | "failed"; files: string[];
  error: string | null; market?: string; category?: string;
  result: { record: { covers: string[] } } | null };
export type RegPack = { pack_id: string; market: string; covers: string[];
  approved_at: number; job_id: string; files: string[]; active_for: string[] };
export type RegRelease = { release_id: string; product_name: string; category: string;
  originals: { name: string; source_id: string; kind: "law" | "brand" }[]; missing: string[]; warning: boolean;
  error?: string };
export type Regulations = { market: string; markets: string[]; categories: string[];
  market_law: { name: string; covers: string[]; files: string[] }; packs: RegPack[]; releases: RegRelease[] };

export const regulationsApi = {
  list: () => request<Regulations>("GET", "/onboarding/regulations"),
  async upload(files: File[], market: string, category: string): Promise<{ job_id: string }> {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    form.append("market", market);
    form.append("category", category);
    const res = await fetch(`${API_BASE}/onboarding/lawpacks/jobs`, { method: "POST", body: form });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? "http_error", data?.error?.message ?? `HTTP ${res.status}`);
    return data;
  },
  job: (jobId: string) => request<LawJob>("GET", `/onboarding/jobs/${encodeURIComponent(jobId)}`),
  approve: (jobId: string) =>
    request<{ pack_id: string }>("POST", `/onboarding/jobs/${encodeURIComponent(jobId)}/approve-lawpack`, {}),
};

export type ReleaseRow = { release_id: string; product_name: string; brand: string; category: string;
  markets: string[]; approved_at: number; version: number; brief: string };
export const BRIEF_RUNNING_NOTE = "The brief (speech-recognition names, prompter points) is still running, about 30 s. "
  + "A show started now uses the approved claims as points; wait for the full prompter.";
