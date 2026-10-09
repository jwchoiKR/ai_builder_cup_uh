// The hub's picker: approved releases (a product with its regulation file) and starting a show from them.
import { request } from "../../app/api";
import type { Session } from "../../app/types";

export type ReleaseRow = { release_id: string; product_name: string; brand: string; category: string;
  markets: string[]; approved_at: number; version: number; brief: string };

export const onboardingApi = {
  // D-279: one release, or 2-3 in segment order
  startShow: (releaseIds: string[]) => request<Session>("POST", "/sessions",
    releaseIds.length === 1 ? { release_id: releaseIds[0] } : { release_ids: releaseIds }),
  // newest first (also after a cold start: they live in the bucket)
  releases: () => request<ReleaseRow[]>("GET", "/products/releases"),
};
