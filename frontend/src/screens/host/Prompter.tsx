// Prompter card (§12.3.3, D-091, D-106): the on-air product's information for the host to refer to.
// One fixed box with two columns (price and offers | points to say); ingredients, cautions and wording to avoid are
// no longer shown (user, 10/10). Facts already said turn grey; the price never does. Compliance alerts take this same box while they are active, so nothing else moves.
import { Check, ListChecks } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";

import { useT, type Translate } from "../../app/i18n";
import type { PrompterPointRow, PrompterViewModel } from "../../app/selectors";
import type { Product, PrompterItem } from "../../app/types";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

const MIN_ZOOM = 0.8; // below this the text gets too small to read
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
  degraded = [],
  alerts,
  notice,
  status,
  timing = null,
}: {
  view: PrompterViewModel;
  product: Product | null;
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
          title={degraded.length ? t("AI check is slow. Some alerts may be late or skipped.") : t("AI checks running")}
          aria-label={degraded.length ? t("AI check is slow. Some alerts may be late or skipped.") : t("AI checks running")}
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
              items={view.items}
              points={view.points}
              ticked={view.ticked}
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
  items,
  points,
  ticked,
  late,
}: {
  /** D-423: the server's item list for this product, rendered as is: nothing chosen or cut here */
  items: PrompterItem[];
  points: PrompterPointRow[];
  ticked: string[];
  late: boolean;
}) {
  const t = useT();
  // D-372: an item is ticked only when the server lists its id (the fact checker's verdict); no text matching
  const said = (i: PrompterItem) => ticked.includes(i.id);
  const state = (i: PrompterItem) => (said(i) ? "said" : "todo");
  const mark = (on: boolean) => on && <span className={styles.saidMark} aria-label={t("Said")}><Check /></span>;
  const of = (kind: PrompterItem["kind"]) => items.filter((i) => i.kind === kind);
  const rows = points; // D-388 (user): every point, as the fact checker's snapshot has them
  const lead = rows.find((p) => p.required && !p.covered) ?? null;
  return (
    <>
      <div className={styles.facts}>
        <div>
          <h4 className={styles.factsLabel}>{t("Price & offers")}</h4>
          {of("price").map((i) =>
            i.main ? (
              <div key={i.id} className={cx(styles.pfPrice, said(i) && styles.said)} data-testid="host-price-current"
                data-state={state(i)}>
                <small className={cx(i.label === "TIME SALE" && styles.priceSale)}>{mark(said(i))}{t(i.label ?? "")}</small>
                <span className="tabular">{i.value}</span>
              </div>
            ) : (
              <div key={i.id} className={cx(styles.pfLine, said(i) && styles.said)} data-testid="host-price-struck"
                data-state={state(i)}>
                {mark(said(i))}
                {t(i.label ?? "")} <s className="tabular">{i.value}</s>
              </div>
            ),
          )}
          {of("set").map((i) => (
            <div key={i.id} className={cx(styles.pfLine, said(i) && styles.said)} data-testid="host-price-set"
              data-state={state(i)}>
              {mark(said(i))}
              {t("Set")} {i.label} <span className="tabular">{i.value}</span>
            </div>
          ))}
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
    </>
  );
}
