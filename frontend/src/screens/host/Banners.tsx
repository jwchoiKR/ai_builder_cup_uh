// Cue strip (§12.3.2), fact note (§12.3.5), MEDIUM banner (§12.3.6), switch banner (§12.3.9) and
// the green "Corrected" confirmation (§12.3.7).
import { ArrowLeftRight, ArrowRight, Check, CircleAlert, Headphones, ShieldAlert } from "lucide-react";

import { TEST_QUALIFIER_RULE } from "../../app/selectors";
import type { Alert, Catalog, HostCue } from "../../app/types";
import { factContext, factSourceLabel, fieldLabel, ruleInfo } from "./hostSelectors";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

export function CueStrip({ cue }: { cue: HostCue }) {
  const done = cue.status === "done";
  return (
    <div className={cx(styles.cue, done && styles.cueDone)} data-testid="host-cue" data-state={cue.status} role="status">
      <span className={styles.cueLabel}>
        <Headphones aria-hidden />
        FROM YOUR PD
      </span>
      <span className={styles.cueText}>{cue.text}</span>
      {done && <Check className={styles.cueCheck} aria-label="Done" />}
    </div>
  );
}

export function FactNote({ alert, catalog }: { alert: Alert; catalog: Catalog | null }) {
  const label = fieldLabel(catalog, alert.field);
  const source = factSourceLabel(catalog, alert);
  const context = alert.passage_id ? factContext(catalog, alert) : null;
  return (
    <div className={cx(styles.banner, styles.fact)} data-testid="host-fact-note" role="alert">
      <span className={styles.bannerIcon} aria-hidden>
        <CircleAlert />
      </span>
      <div className={styles.bannerBody}>
        <div className={styles.bannerTitleRow}>
          <span className={styles.bannerTitle}>{label} correction</span>
          <span className={styles.factValues}>
            <span className={styles.factWrong} data-testid="host-fact-wrong">
              ✕ {alert.stated_value}
            </span>
            <ArrowRight className={styles.factArrow} aria-label="should be" />
            <span className={styles.factRight} data-testid="host-fact-right">
              ○ {alert.correct_value}
            </span>
          </span>
        </div>
        <span className={styles.bannerSub}>
          {context ? `${context} · ` : ""}Source: {source}
        </span>
      </div>
      <span className={styles.bannerAside}>SAY THE UPDATED {label.toUpperCase()}</span>
    </div>
  );
}

export function MediumBanner({
  alert,
  catalog,
  fact = null,
}: {
  alert: Alert;
  catalog: Catalog | null;
  /** D-105: the fact note on the same sentence, shown in this card instead of its own. */
  fact?: Alert | null;
}) {
  const rule = ruleInfo(catalog, alert.rule_id);
  const qualifier = alert.rule_id === TEST_QUALIFIER_RULE;
  return (
    <div className={cx(styles.banner, styles.medium)} data-testid="host-medium-banner" role="alert">
      <span className={styles.bannerIcon} aria-hidden>
        <ShieldAlert />
      </span>
      <div className={styles.bannerBody}>
        <div className={styles.bannerTitleRow}>
          <span className={styles.bannerTitle}>{qualifier ? "Add 'in our in-house test'" : "Avoid this claim"}</span>
          <span className={styles.mediumSpan}>"{alert.span}"</span>
          {fact && (
            <span className={styles.factValues} data-testid="host-medium-fact">
              <span className={styles.factRight}>○ {fact.correct_value}</span>
              <span className={styles.factWrong}>(not {fact.stated_value})</span>
            </span>
          )}
        </div>
        <span className={styles.mediumSay}>
          {alert.say_instead ? `Say: '${alert.say_instead}'` : "Say the result with 'in our in-house test'."}
        </span>
      </div>
      <span className={styles.bannerAside}>{rule.title}</span>
    </div>
  );
}

export function SwitchBanner({
  productName,
  secondsLeft,
  onCancel,
}: {
  productName: string;
  secondsLeft: number;
  onCancel: () => void;
}) {
  return (
    <div className={cx(styles.banner, styles.switch)} data-testid="host-switch-banner" role="status">
      <span className={styles.bannerIcon} aria-hidden>
        <ArrowLeftRight />
      </span>
      <div className={styles.bannerBody}>
        <span className={styles.switchTitle}>Switching to {productName}</span>
      </div>
      <span className={cx(styles.switchCount, "tabular")} aria-label={`${secondsLeft} seconds`}>
        {Math.max(1, secondsLeft)}
      </span>
      <button type="button" className={styles.switchCancel} onClick={onCancel}>
        Cancel switch (Esc)
      </button>
    </div>
  );
}

export function CorrectedBar() {
  return (
    <div className={styles.corrected} data-testid="host-corrected" role="status">
      <Check aria-hidden />
      Corrected
    </div>
  );
}
