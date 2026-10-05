// Plain words for record paths, and the edits the approval screen makes (D-231).
import type { ProductRecord } from "./onboardingApi";

const LABELS: Record<string, string> = {
  brand: "Brand",
  product_name: "Product name",
  short_names: "Short names viewers use",
  generic_word: "Category word (e.g. serum)",
  category: "Product category",
  language: "Document language",
  variants: "Sizes and prices",
  offers: "Offers",
  ingredients: "Ingredients",
  approved_claims: "Approved claims",
  not_approved_claims: "Claims not approved",
  avoid_saying: "Avoid-saying pairs",
  qualified_results: "Test results",
  cautions: "Cautions",
  how_to_use: "How to use",
  key_facts: "Key facts",
  size_value: "size",
  minor: "amount",
  percent: "percent",
  amount: "amount",
  amount_value: "amount",
};

type Step = string | number;

/** "variants[0].prices[1].minor" -> ["variants", 0, "prices", 1, "minor"]; "variants[LMN-30].size_value" keeps the id. */
export function pathSteps(path: string): Step[] {
  const out: Step[] = [];
  for (const m of path.matchAll(/([A-Za-z_]+)|\[([^\]]+)\]/g)) {
    if (m[1]) out.push(m[1]);
    else out.push(/^\d+$/.test(m[2]) ? Number(m[2]) : m[2]);
  }
  return out;
}

function at(record: ProductRecord, steps: Step[]): unknown {
  let cur: unknown = record;
  for (const s of steps) {
    if (cur == null) return undefined;
    if (typeof s === "number") cur = (cur as unknown[])[s];
    else if (Array.isArray(cur)) cur = cur.find((x) => x?.variant_id === s || x?.offer_id === s || x?.name === s);
    else cur = (cur as Record<string, unknown>)[s];
  }
  return cur;
}

/** "variants[0].prices[1].minor" -> "Night Serum 30 ml · live price SG". Unknown paths come back in plain words. */
export function plainField(record: ProductRecord, path: string): string {
  const steps = pathSteps(path);
  if (steps[0] === "variants" && steps.length > 1) {
    const v = at(record, steps.slice(0, 2)) as ProductRecord["variants"][number] | undefined;
    const name = v ? v.name : String(steps[1]);
    if (steps[2] === "prices" && steps.length > 3) {
      const m = at(record, steps.slice(0, 4)) as ProductRecord["variants"][number]["prices"][number] | undefined;
      return m ? `${name} · ${m.kind} price${m.market ? ` ${m.market}` : ""}` : `${name} · price`;
    }
    return `${name}${steps[2] ? ` · ${LABELS[String(steps[2])] ?? String(steps[2]).replace(/_/g, " ")}` : ""}`;
  }
  if (typeof steps[0] !== "string" || !(steps[0] in LABELS)) return path; // the model's own words ("30 ml SG live price")
  const words = steps.filter((s) => typeof s === "string").map((s) => LABELS[s as string] ?? (s as string).replace(/_/g, " "));
  return words.join(" · ") || path;
}

/** A conflict value as an amount in minor units, for a money path ("S$46.00" or "4600" -> 4600). */
function minorOf(value: string): number | null {
  const m = value.replace(/,/g, "").match(/\d+(\.\d+)?/);
  if (!m) return null;
  return m[1] ? Math.round(Number(m[0]) * 100) : /[$€£¥]|RM|S\$/i.test(value) ? Number(m[0]) * 100 : Number(m[0]);
}

/** Set one value by path; returns a new record, or null when the path is not an editable value. */
export function setAt(record: ProductRecord, path: string, value: string): ProductRecord | null {
  const steps = pathSteps(path);
  const next = structuredClone(record);
  const parent = at(next, steps.slice(0, -1)) as Record<string, unknown> | undefined;
  const key = steps[steps.length - 1];
  if (!parent || typeof key !== "string" || !(key in parent)) return null;
  if (key === "minor") {
    const n = minorOf(value);
    if (n === null) return null;
    parent[key] = n;
  } else {
    parent[key] = value;
  }
  return next;
}

/** The option to preselect: the newest effective date, else the first. */
export function newestIndex(dates: (string | null)[]): number {
  let best = 0;
  dates.forEach((d, i) => {
    if (d && (!dates[best] || d > (dates[best] as string))) best = i;
  });
  return best;
}

// D-243: currencies without a minor unit (KRW, JPY, VND, ...) store the whole amount
const ZERO_DECIMAL = new Set(["BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND",
  "VUV", "XAF", "XOF", "XPF"]);
export const money = (m: { currency: string; minor: number }) =>
  ZERO_DECIMAL.has(m.currency) ? `${m.currency} ${m.minor.toLocaleString("en")}` : `${m.currency} ${(m.minor / 100).toFixed(2)}`;

/** A conflict value in words: a money path's minor units as an amount in its currency ("4600" -> "SGD 46.00"). */
export function conflictValue(record: ProductRecord, path: string, value: string): string {
  const steps = pathSteps(path);
  if (steps[steps.length - 1] !== "minor" || !/^\d+$/.test(value.trim())) return value;
  const m = at(record, steps.slice(0, -1)) as { currency?: string } | undefined;
  return `${m?.currency ?? ""} ${(Number(value) / 100).toFixed(2)}`.trim();
}
