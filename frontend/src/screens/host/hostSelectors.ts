// Host-only derived views (§12.3). Pure functions over ClientState + catalog; shared selectors live in
// app/selectors.ts and are reused where they fit.
import {
  activePromos,
  nextProduct,
  onAirProduct,
  onAirSegment,
  productById,
  productOrder,
  prompterView,
  runsheetOf,
  type ActivePromoView,
  type PrompterViewModel,
} from "../../app/selectors";
import type { ClientState } from "../../app/state";
import type { Alert, Answer, Catalog, Product } from "../../app/types";

/** NOW / NEXT. Before the broadcast starts the first run-sheet product is shown as NOW, so the host
 * can read the first prompter page while the show is READY. */
export function hostProducts(state: ClientState, catalog: Catalog | null): { now: Product | null; next: Product | null } {
  const seg = onAirSegment(state);
  if (seg) return { now: onAirProduct(state, catalog), next: nextProduct(state, catalog) };
  if (state.session?.status === "ended") return { now: null, next: null };
  const order = productOrder(state, catalog);
  return { now: productById(catalog, order[0]), next: productById(catalog, order[1]) };
}

/** The prompter page: the on-air product; before the start, the first product with nothing said. */
export function hostPrompterView(state: ClientState, catalog: Catalog | null, product: Product | null): PrompterViewModel {
  const v = prompterView(state, catalog);
  if (v.product || !product) return v;
  const item = runsheetOf(state, catalog)?.items.find((i) => i.product_id === product.product_id);
  const required = new Set(item?.required_point_ids ?? []);
  const points = product.prompter_points.map((p) => ({
    point_id: p.point_id,
    text: p.text,
    required: required.has(p.point_id),
    covered: false,
  }));
  return {
    product,
    points,
    requiredTotal: points.filter((p) => p.required).length,
    requiredCovered: 0,
  };
}

/** Up to two banner chips for running promos (§12.3.1). */
export function promoChips(state: ClientState, catalog: Catalog | null, now: number): ActivePromoView[] {
  return activePromos(state, catalog, now)
    .sort((a, b) => Number(b.promo.changes_prices) - Number(a.promo.changes_prices) || a.endsAt - b.endsAt)
    .slice(0, 2);
}

const capitalise = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** "price" -> "Price", "ingredient_amount" -> "Ingredient amount" (labels from notices.json). */
export function fieldLabel(catalog: Catalog | null, field: string | null): string {
  if (!field) return "Fact";
  const label = catalog?.notices?.field_labels?.[field] ?? field.replace(/_/g, " ");
  return capitalise(label);
}

/** "product sheet, Key facts" or "active promotion" (§8.5, §12.3.5). */
export function factSourceLabel(catalog: Catalog | null, alert: Alert): string {
  if (!alert.passage_id) return "active promotion";
  const section = catalog?.passages?.[alert.passage_id]?.section;
  return section ? `product sheet, ${section}` : "product sheet";
}

/** What the value is: the quoted passage label ("Live broadcast price", "Niacinamide"), else the
 * field label. */
export function factContext(catalog: Catalog | null, alert: Alert): string {
  const quote = alert.quote ?? "";
  const head = quote.includes(":") ? quote.split(":")[0].trim() : "";
  if (head && head.length <= 40) return head;
  return fieldLabel(catalog, alert.field);
}

export interface RuleInfo {
  title: string;
  ref: string;
}

/** "Appendix III, Section 3, Skin products" -> "Appendix III §3". */
export function shortRef(sourceRef: string): string {
  const parts = sourceRef
    .replace(/\s*\([^)]*\)\s*/g, " ")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (!parts.length) return sourceRef;
  const section = (p: string) => p.match(/^section\s+(.+)$/i);
  const second = parts[1] ? section(parts[1]) : null;
  if (second) return `${parts[0]} §${second[1]}`;
  return parts.slice(0, 2).join(", ");
}

export function ruleInfo(catalog: Catalog | null, ruleId: string | null): RuleInfo {
  const rule = catalog?.rules?.find((r) => r.rule_id === ruleId);
  if (!rule) return { title: ruleId ?? "Restricted claim", ref: "" };
  return { title: rule.title, ref: shortRef(rule.source_ref) };
}

/** Source chip under the suggested answer: "Product sheet · FAQ" style (§12.3.4). */
export function answerSource(catalog: Catalog | null, answer: Answer | null): string | null {
  const c = answer?.citations?.[0];
  if (!c) return null;
  if (c.passage_id.startsWith("PROMO#")) return "Active promotion";
  const section = c.section ?? catalog?.passages?.[c.passage_id]?.section;
  return section ? `Product sheet · ${section}` : "Product sheet";
}

/** Seconds left on a pending switch, 5…1 (§12.3.9). */
export function switchSecondsLeft(commitAt: number | null, now: number): number {
  if (!commitAt) return 0;
  return Math.max(0, Math.ceil((commitAt - now) / 1000));
}

export function initialOf(name: string): string {
  const t = name.trim();
  return t ? t[0].toUpperCase() : "?";
}

export function correctedToastMs(state: ClientState): number {
  const v = Number(state.session?.settings_snapshot?.CORRECTED_TOAST_MS);
  return Number.isFinite(v) && v > 0 ? v : 1500;
}
