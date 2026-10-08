// Prompter card (§12.3.3, D-091, D-106): the on-air product's information for the host to refer to.
// One fixed box with three columns (price and offers | ingredients | points to say) and two guard
// blocks (caution | avoid saying), as in the earlier prototype. Facts already said turn grey; the price
// never does. Compliance alerts take this same box while they are active, so nothing else moves.
import { Ban, Check, CircleDot, ListChecks, TriangleAlert } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { useT, type Translate } from "../../app/i18n";
import type { PriceView, PrompterPointRow, PrompterViewModel } from "../../app/selectors";
import type { Product } from "../../app/types";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");
const PERCENT = /^\d+(\.\d+)?\s*(%|mg|mcg|µg|g|iu)$/i; // D-233: a share or a mass (supplements)
const MAX_INGREDIENTS = 4;

/** "ceramide_np" -> "Ceramide NP", "sodium_hyaluronate" -> "Sodium Hyaluronate". */
const ingredientName = (key: string) =>
  key
    .split("_")
    .map((w) => (w.length <= 2 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)))
    .join(" ");

/** The product's ingredient amounts (key facts with a percentage), in sheet order. */
export function ingredientsOf(product: Product): { key: string; name: string; value: string }[] {
  return Object.entries(product.key_facts)
    .filter(([, v]) => PERCENT.test(v))
    .slice(0, MAX_INGREDIENTS)
    .map(([key, value]) => ({ key, name: ingredientName(key), value }));
}

const MIN_ZOOM = 0.8; // below this the text gets too small to read
const CAUTIONS_SHOWN = 4; // D-332: the first cautions (the record's order); the rest behind "+N more"
const LATE_SHARE = 0.8; // D-107: from here an unsaid required point is emphasised once

/** Planned time of the on-air segment, for the status line and the late emphasis. */
export interface SegmentTiming {
  elapsedMs: number;
  plannedMs: number;
}

const mmss = (ms: number) => {
  const t = Math.floor(Math.abs(ms) / 1000);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

/** "2 required points left · 0:30", or "+0:15 over" past the planned time. */
export function pointsStatus(t: Translate, left: number, timing: SegmentTiming | null, total = 1): string {
  // D-332: a product with no required points says nothing about them
  const points = left
    ? t(left === 1 ? "{n} required point left" : "{n} required points left", { n: left })
    : total > 0 ? t("All required points said") : "";
  if (!timing || !timing.plannedMs) return points;
  const rest = timing.plannedMs - timing.elapsedMs;
  const time = rest >= 0 ? mmss(rest) : t("+{time} over", { time: mmss(rest) });
  return points ? `${points} · ${time}` : time;
}

/** D-107 (the prototype's fitSlot): when the box content is taller than the box, shrink it step by
 *  step down to MIN_ZOOM; if it still does not fit, the card grows downward (its top never moves and
 *  the questions below get less room). Nothing is ever clipped. */
function useFit(box: RefObject<HTMLDivElement>, fit: RefObject<HTMLDivElement>) {
  const run = useRef(() => {});
  run.current = () => {
    const s = box.current;
    const f = fit.current;
    const card = s?.parentElement;
    if (!s || !f || !card) return;
    f.style.zoom = "1";
    f.style.minHeight = "";
    card.style.minHeight = "";
    const cs = getComputedStyle(s);
    const room = s.clientHeight - parseFloat(cs.paddingTop || "0") - parseFloat(cs.paddingBottom || "0");
    if (!(room > 0)) return; // no layout (tests, hidden pane)
    const fits = () => f.getBoundingClientRect().height <= room + 1;
    let z = 1;
    while (!fits() && z > MIN_ZOOM) {
      z = Math.round((z - 0.05) * 100) / 100;
      f.style.zoom = String(z);
    }
    if (!fits()) {
      card.style.minHeight = `${Math.ceil(card.clientHeight + f.getBoundingClientRect().height - room)}px`;
      return;
    }
    f.style.minHeight = `${room / z}px`; // keeps the guard blocks at the bottom and fills the box with alerts
  };
  useLayoutEffect(() => run.current());
  useEffect(() => {
    if (!box.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => run.current());
    ro.observe(box.current);
    return () => ro.disconnect();
  }, [box]);
}

export function Prompter({
  view,
  product,
  price,
  checking,
  degraded = [],
  alerts,
  notice,
  status,
  timing = null,
}: {
  view: PrompterViewModel;
  product: Product | null;
  price: PriceView | null;
  checking: boolean;
  /** D-137: judges that failed on the last finals: the health dot turns amber */
  degraded?: string[];
  /** Compliance alerts or the green Corrected bar: they take the product box while present. */
  alerts?: ReactNode;
  /** D-115: a compact green "Corrected" line at the top of the box; the product info stays below */
  notice?: ReactNode;
  /** D-115: the reserved status line at the bottom (switch countdown, PD cue, or points and time) */
  status?: ReactNode;
  timing?: SegmentTiming | null;
}) {
  const t = useT();
  const box = useRef<HTMLDivElement>(null);
  const fit = useRef<HTMLDivElement>(null);
  useFit(box, fit);
  return (
    <section className={styles.card} data-testid="host-prompter" aria-label={t("Your prompter")}>
      {checking && (
        <span className={styles.checking} data-testid="host-checking-chip" role="status">
          <CircleDot aria-hidden />
          {t("Checking a phrase…")}
        </span>
      )}
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>
          <ListChecks aria-hidden />
          {t("YOUR PROMPTER")}
        </span>
        {product && (
          <span className={styles.prompterKicker}>
            {product.eyebrow} · {product.name}
          </span>
        )}
        <span className={`${styles.cardMeta} tabular`} data-testid="host-required-count">
          {t("{a} / {b} required points", { a: view.requiredCovered, b: view.requiredTotal })}
        </span>
        {/* D-137: silence must not look like safety. Neutral while every judge answers; amber when one
            failed on the last finals in a row. */}
        <span
          className={degraded.length ? `${styles.healthDot} ${styles.healthDotWarn}` : styles.healthDot}
          data-testid="host-judge-health"
          data-state={degraded.length ? "degraded" : "ok"}
          role="status"
          title={degraded.length ? t("AI check slow: alerts may be missing") : t("AI checks running")}
          aria-label={degraded.length ? t("AI check slow: alerts may be missing") : t("AI checks running")}
        >
          <span className={styles.healthDotMark} aria-hidden />
          {degraded.length > 0 && t("AI check slow")}
        </span>
      </header>
      <div className={styles.prompterBox} ref={box}>
        <div className={styles.fit} ref={fit}>
          {notice}
          {alerts ? (
            <div className={styles.prompterAlerts} data-testid="host-prompter-alerts">
              {alerts}
            </div>
          ) : product ? (
            <ProductPanel
              product={product}
              price={price}
              points={view.points}
              late={Boolean(timing?.plannedMs && timing.elapsedMs >= timing.plannedMs * LATE_SHARE)}
            />
          ) : (
            <p className={styles.emptyPrompter}>{t("No product on air.")}</p>
          )}
        </div>
      </div>
      <div className={styles.prompterStatus} data-testid="host-prompter-status">
        {status}
      </div>
    </section>
  );
}

function ProductPanel({
  product,
  price,
  points,
  late,
}: {
  product: Product;
  price: PriceView | null;
  points: PrompterPointRow[];
  late: boolean;
}) {
  const t = useT();
  const cautions = product.cautions ?? [];
  const [showAll, setShowAll] = useState(false);
  const saidText = points
    .filter((p) => p.covered)
    .map((p) => p.text.toLowerCase())
    .join(" ");
  // The price column already shows prices; a price point is listed only when it is required.
  const rows = points.filter((p) => p.required || !price || !p.text.includes(price.symbol));
  const lead = rows.find((p) => p.required && !p.covered) ?? null;
  const sale = price?.label === "TIME SALE";
  return (
    <>
      <div className={styles.facts}>
        <div>
          <h4 className={styles.factsLabel}>{t("Price & offers")}</h4>
          {price && (
            <>
              <div className={styles.pfPrice}>
                <small className={cx(sale && styles.priceSale)}>{t(price.label)}</small>
                <span className="tabular">{price.current}</span>
              </div>
              <div className={styles.pfLine}>
                {sale ? t("Live price") : t("List price")} <s className="tabular">{price.struck}</s>
              </div>
              {price.set && (
                <div className={styles.pfLine}>
                  {t("Set")} {price.set}
                </div>
              )}
            </>
          )}
        </div>
        <div>
          <h4 className={styles.factsLabel}>{t("Ingredients")}</h4>
          <div className={styles.nums}>
            {ingredientsOf(product).map((i) => (
              <div
                key={i.key}
                className={cx(styles.num, saidText.includes(i.name.toLowerCase()) && styles.said)}
                data-testid={`host-ing-${i.key}`}
              >
                <b className="tabular">{i.value}</b>
                <span>{i.name}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h4 className={styles.factsLabel}>{t("Points to say")}</h4>
          <ul className={styles.points}>
            {rows.map((p) => (
              <li
                key={p.point_id}
                className={cx(styles.point, p === lead && styles.leadPoint, p === lead && late && styles.leadLate,
                  p.covered && styles.said)}
                data-testid={`host-point-${p.point_id}`}
                data-state={p.covered ? "said" : "todo"}
                data-late={p === lead && late ? "true" : undefined}
              >
                <span className={styles.pointIcon} aria-label={p.covered ? t("Said") : undefined}>
                  {p.covered ? <Check /> : <span className={styles.bullet} />}
                </span>
                <span>{p.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className={styles.guards}>
        <div className={cx(styles.guard, styles.guardCare)} data-testid="host-cautions">
          <h5>
            <TriangleAlert aria-hidden />
            {t("Caution")}
          </h5>
          {(showAll ? cautions : cautions.slice(0, CAUTIONS_SHOWN)).map((c) => (
            <p key={c}>{c}</p>
          ))}
          {cautions.length > CAUTIONS_SHOWN && (
            <button type="button" className={styles.moreToggle} aria-expanded={showAll}
              onClick={() => setShowAll((v) => !v)} data-testid="host-cautions-more">
              {showAll ? t("Show fewer") : t("+{n} more", { n: cautions.length - CAUTIONS_SHOWN })}
            </button>
          )}
        </div>
        <div className={cx(styles.guard, styles.guardAvoid)} data-testid="host-avoid">
          <h5>
            <Ban aria-hidden />
            {t("Avoid saying")}
          </h5>
          {(product.avoid_saying ?? []).map((a) => (
            <p key={a.say_not}>
              <span className={styles.avoidNo}>✕ {a.say_not}</span>
              <span className={styles.avoidTo}>→</span>
              <b>{a.say}</b>
            </p>
          ))}
        </div>
      </div>
    </>
  );
}
