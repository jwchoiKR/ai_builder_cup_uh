// Prompter card (§12.3.3, D-091, D-106): the on-air product's information for the host to refer to.
// One fixed box with three columns (price and offers | ingredients | points to say) and two guard
// blocks (caution | avoid saying), as in the earlier prototype. Facts already said turn grey; the price
// never does. Compliance alerts take this same box while they are active, so nothing else moves.
import { Ban, Check, CircleDot, ListChecks, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { PriceView, PrompterPointRow, PrompterViewModel } from "../../app/selectors";
import type { Product } from "../../app/types";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");
const PERCENT = /^\d+(\.\d+)?%$/;
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

export function Prompter({
  view,
  product,
  price,
  checking,
  alerts,
}: {
  view: PrompterViewModel;
  product: Product | null;
  price: PriceView | null;
  checking: boolean;
  /** Compliance alerts or the green Corrected bar: they take the product box while present. */
  alerts?: ReactNode;
}) {
  return (
    <section className={styles.card} data-testid="host-prompter" aria-label="Your prompter">
      {checking && (
        <span className={styles.checking} data-testid="host-checking-chip" role="status">
          <CircleDot aria-hidden />
          Checking a phrase…
        </span>
      )}
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>
          <ListChecks aria-hidden />
          YOUR PROMPTER
        </span>
        {product && (
          <span className={styles.prompterKicker}>
            {product.eyebrow} · {product.name}
          </span>
        )}
        <span className={`${styles.cardMeta} tabular`} data-testid="host-required-count">
          {view.requiredCovered} / {view.requiredTotal} required points
        </span>
      </header>
      <div className={styles.prompterBox}>
        {alerts ? (
          <div className={styles.prompterAlerts} data-testid="host-prompter-alerts">
            {alerts}
          </div>
        ) : product ? (
          <ProductPanel product={product} price={price} points={view.points} />
        ) : (
          <p className={styles.emptyPrompter}>No product on air.</p>
        )}
      </div>
    </section>
  );
}

function ProductPanel({ product, price, points }: { product: Product; price: PriceView | null; points: PrompterPointRow[] }) {
  const saidText = points
    .filter((p) => p.covered)
    .map((p) => p.text.toLowerCase())
    .join(" ");
  // The price column already shows prices; a price point is listed only when it is required.
  const rows = points.filter((p) => p.required || !p.text.includes("S$"));
  const lead = rows.find((p) => p.required && !p.covered) ?? null;
  const sale = price?.label === "TIME SALE";
  return (
    <>
      <div className={styles.facts}>
        <div>
          <h4 className={styles.factsLabel}>Price &amp; offers</h4>
          {price && (
            <>
              <div className={styles.pfPrice}>
                <small className={cx(sale && styles.priceSale)}>{price.label}</small>
                <span className="tabular">{price.current}</span>
              </div>
              <div className={styles.pfLine}>
                {sale ? "Live price" : "List price"} <s className="tabular">{price.struck}</s>
              </div>
              {price.set && <div className={styles.pfLine}>Set {price.set}</div>}
            </>
          )}
        </div>
        <div>
          <h4 className={styles.factsLabel}>Ingredients</h4>
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
          <h4 className={styles.factsLabel}>Points to say</h4>
          <ul className={styles.points}>
            {rows.map((p) => (
              <li
                key={p.point_id}
                className={cx(styles.point, p === lead && styles.leadPoint, p.covered && styles.said)}
                data-testid={`host-point-${p.point_id}`}
                data-state={p.covered ? "said" : "todo"}
              >
                <span className={styles.pointIcon} aria-label={p.covered ? "Said" : undefined}>
                  {p.covered ? <Check /> : <span className={styles.bullet} />}
                </span>
                <span>
                  {p.text}
                  {p.required && !p.covered && <span className={styles.required}>REQUIRED</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className={styles.guards}>
        <div className={cx(styles.guard, styles.guardCare)} data-testid="host-cautions">
          <h5>
            <TriangleAlert aria-hidden />
            Caution
          </h5>
          {(product.cautions ?? []).map((c) => (
            <p key={c}>{c}</p>
          ))}
        </div>
        <div className={cx(styles.guard, styles.guardAvoid)} data-testid="host-avoid">
          <h5>
            <Ban aria-hidden />
            Avoid saying
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
