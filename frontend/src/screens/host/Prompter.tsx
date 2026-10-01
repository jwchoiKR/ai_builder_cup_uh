// Prompter card (§12.3.3): one page per product; said points turn light grey, the first unsaid point
// is the focus row and stays in view.
import { ArrowRight, Check, CircleDot, ListChecks } from "lucide-react";
import { useEffect, useRef } from "react";

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
  const focusRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    focusRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [view.focusPointId]);

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
        <ol className={styles.points}>
          {view.points.map((p) => {
            const state = p.covered ? "said" : p.focus ? "focus" : "todo";
            return (
              <li
                key={p.point_id}
                ref={p.focus ? focusRef : undefined}
                className={cx(styles.point, p.covered && styles.said, p.focus && styles.focus)}
                data-testid={`host-point-${p.point_id}`}
                data-state={state}
                aria-current={p.focus ? "step" : undefined}
              >
                <span className={styles.pointIcon} aria-label={p.covered ? "Said" : undefined}>
                  {p.covered ? <Check /> : p.focus ? <ArrowRight /> : <span className={styles.bullet} />}
                </span>
                <span>{p.text}</span>
                {p.required && !p.covered && <span className={styles.required}>REQUIRED POINT</span>}
              </li>
            );
          })}
        </ol>
      ) : (
        <p className={styles.emptyPrompter}>No prompter points.</p>
      )}
      <footer className={styles.cardFooter}>
        <span>• Focus on your next point</span>
        <span>Keep it natural.</span>
      </footer>
    </section>
  );
}
