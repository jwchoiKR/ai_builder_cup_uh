// Prompter card (§12.3.3, D-091): the on-air product's information for the host to refer to, as a
// plain list in no particular order. Points already said get a check and turn light grey.
import { Check, CircleDot, ListChecks } from "lucide-react";

import type { PriceView, PrompterViewModel } from "../../app/selectors";
import type { Product } from "../../app/types";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

export function Prompter({
  view,
  product,
  price,
  checking,
}: {
  view: PrompterViewModel;
  product: Product | null;
  price: PriceView | null;
  checking: boolean;
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
        <span className={`${styles.cardMeta} tabular`} data-testid="host-required-count">
          {view.requiredCovered} / {view.requiredTotal} required points
        </span>
      </header>
      {product && (
        <div className={styles.product}>
          <div>
            <div className={styles.productEyebrow}>{product.eyebrow}</div>
            <div className={styles.productName}>{product.name}</div>
          </div>
          {price && (
            <div className={styles.price}>
              <span className={cx(styles.priceLabel, price.label === "TIME SALE" && styles.priceSale)}>{price.label}</span>
              <span className={styles.priceRow}>
                <span className={`${styles.priceStruck} tabular`}>{price.struck}</span>
                <span className={`${styles.priceBig} tabular`}>{price.current}</span>
              </span>
            </div>
          )}
        </div>
      )}
      {view.points.length ? (
        <ul className={styles.points}>
          {view.points.map((p) => (
            <li
              key={p.point_id}
              className={cx(styles.point, p.covered && styles.said)}
              data-testid={`host-point-${p.point_id}`}
              data-state={p.covered ? "said" : "todo"}
            >
              <span className={styles.pointIcon} aria-label={p.covered ? "Said" : undefined}>
                {p.covered ? <Check /> : <span className={styles.bullet} />}
              </span>
              <span>
                {p.text}
                {p.required && !p.covered && <span className={styles.required}>REQUIRED POINT</span>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.emptyPrompter}>No prompter points.</p>
      )}
    </section>
  );
}
