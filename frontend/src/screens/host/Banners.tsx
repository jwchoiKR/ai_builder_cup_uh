// Cue strip (§12.3.2), fact note (§12.3.5), MEDIUM banner (§12.3.6), switch banner (§12.3.9) and
// the green "Corrected" confirmation (§12.3.7).
import { ArrowLeftRight, Check, CircleAlert, Headphones, ShieldAlert } from "lucide-react";
import { useEffect } from "react";

import { useT } from "../../app/i18n";
import { useNow } from "../../app/store";
import { TEST_QUALIFIER_RULE } from "../../app/selectors";
import type { LineCheck } from "../../app/state";
import type { Alert, Catalog, HostCue } from "../../app/types";
import { factContext, factSayLine, factSourceLabel, fieldLabel, ruleInfo } from "./hostSelectors";
import styles from "./host.module.css";

/** D-341: the backend's LATE_QUALIFIER_MS: a qualifier add-on fixes the alert only this long after it. */
const QUALIFIER_ADDON_MS = 10_000;

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

export function CueStrip({ cue }: { cue: HostCue }) {
  const t = useT();
  const done = cue.status === "done";
  return (
    <div className={cx(styles.cue, done && styles.cueDone)} data-testid="host-cue" data-state={cue.status} role="status">
      <span className={styles.cueLabel}>
        <Headphones aria-hidden />
        {t("FROM YOUR PD")}
      </span>
      <span className={styles.cueText}>{cue.text}</span>
      {done && <Check className={styles.cueCheck} aria-label={t("Done")} />}
    </div>
  );
}

export function FactNote({ alert, catalog, onRendered, count = 1 }: {
  alert: Alert;
  catalog: Catalog | null;
  onRendered?: (alertId: string) => void;
  /** D-399: how many active notes cite this note's passage (this one is the newest) */
  count?: number;
}) {
  // D-107: wrong product information is as urgent as a compliance alert, so it takes the prompter's
  // product box too: what was heard small, the right value as the biggest text.
  const t = useT();
  // D-133: every alert on the host screen acknowledges its render (latency of fact notes too)
  useEffect(() => {
    onRendered?.(alert.alert_id);
  }, [alert.alert_id, onRendered]);
  const label = fieldLabel(catalog, alert.field);
  const source = factSourceLabel(catalog, alert);
  const context = alert.passage_id ? factContext(catalog, alert) : null;
  return (
    <div className={cx(styles.alertBlock, styles.alertFact)} data-testid="host-fact-note" role="alert">
      <div className={styles.alertTop}>
        <span className={styles.warnBadge}>
          <CircleAlert aria-hidden />
          {alert.heard_check ? t("CHECK WHAT WAS SAID") : `${t(label).toUpperCase()} ${t("CORRECTION")}`}
        </span>
        {count > 1 && <span className={styles.alertCount} data-testid="host-alert-count">×{count}</span>}
        {alert.unverified && (
          <span className={`${styles.riskBadge} ${styles.unverifiedBadge}`} data-testid="host-unverified">
            {alert.unverified_reason ? t("Unverified (AI response delayed)") : t("AI check unavailable")}
          </span>
        )}
        <span className={styles.alertSaid} data-testid="host-fact-wrong">
          {/* D-303: a possibly misheard number is shown as heard, without the wrong mark */}
          {t("Heard:")} {alert.heard_check ? "" : "✕ "}{alert.stated_value}
        </span>
      </div>
      {/* D-136: one line the host can read out, with the product and the promo condition */}
      <span className={styles.alertSay} data-testid="host-fact-right">
        ○ {factSayLine(catalog, alert)}
      </span>
      <span className={styles.alertMeta}>
        <span className={styles.alertRule}>
          {context ? `${context} · ` : ""}
          {t("Source:")} {source}
        </span>
      </span>
    </div>
  );
}

export function MediumBanner({
  alert,
  catalog,
  fact = null,
  onRendered,
  serverOffsetMs = 0,
  count = 1,
}: {
  alert: Alert;
  catalog: Catalog | null;
  /** D-341: server time, for the qualifier add-on's 10 s */
  serverOffsetMs?: number;
  /** D-105: the fact note on the same sentence, shown in this card instead of its own. */
  fact?: Alert | null;
  onRendered?: (alertId: string) => void;
  /** D-399: how many unresolved MEDIUM alerts cite this rule (this one is the newest) */
  count?: number;
}) {
  // D-106: a block at the top of the prompter card, yellow, with the replacement as the biggest text.
  const t = useT();
  useEffect(() => {
    onRendered?.(alert.alert_id);
    if (fact) onRendered?.(fact.alert_id);
  }, [alert.alert_id, fact?.alert_id, onRendered]);
  const rule = ruleInfo(catalog, alert.rule_id, alert.product_id);
  const qualifier = alert.rule_id === TEST_QUALIFIER_RULE;
  // D-341 (review H16): the qualifier alone fixes the alert only within 10 s; after that, say the result again with it
  const now = useNow(1000) + serverOffsetMs;
  const late = qualifier && now - alert.created_at > QUALIFIER_ADDON_MS;
  return (
    <div className={cx(styles.alertBlock, styles.alertMedium)} data-testid="host-medium-banner" role="alert">
      <div className={styles.alertTop}>
        <span className={styles.warnBadge}>
          <ShieldAlert aria-hidden />
          {/* D-355: a suggestion; any wording that says where the result comes from corrects it */}
          {qualifier ? (late ? t("Say the result again with where it comes from (e.g. 'in our in-house test')") : t("Say where the result comes from (e.g. 'in our in-house test')"))
            : t("CHECK WORDING")}
        </span>
        {count > 1 && <span className={styles.alertCount} data-testid="host-alert-count">×{count}</span>}
        {alert.unverified && (
          <span className={`${styles.riskBadge} ${styles.unverifiedBadge}`} data-testid="host-unverified">
            {alert.unverified_reason ? t("Unverified (AI response delayed)") : t("AI check unavailable")}
          </span>
        )}
        <span className={styles.alertSaid}>
          {t("Heard:")} "{alert.span}"
        </span>
        {fact && (
          <span className={styles.factValues} data-testid="host-medium-fact">
            <span className={styles.factRight}>○ {fact.correct_value}</span>
            <span className={styles.factWrong}>{t("(not {value})", { value: fact.stated_value ?? "" })}</span>
          </span>
        )}
      </div>
      <span className={styles.alertSayLabel}>{t("Say this instead.")}</span>
      <span className={styles.alertSay}>
        {alert.say_instead ? `“${alert.say_instead}”` : t("Say the result with where it comes from (e.g. 'in our in-house test').")}
      </span>
      <span className={styles.alertMeta}>
        <span className={styles.alertRule}>{rule.title}</span>
      </span>
    </div>
  );
}

/** D-288: the judge could not check a line with a risky phrase; neutral, not a rule alert */
export function LineCheckCard({ check }: { check: LineCheck }) {
  const t = useT();
  return (
    <div className={cx(styles.alertBlock, styles.alertCheck)} data-testid="host-line-check" role="status">
      <div className={styles.alertTop}>
        <span className={styles.warnBadge}>
          <CircleAlert aria-hidden />
          {t("CHECK THIS LINE")}
        </span>
        <span className={styles.alertSaid}>
          {t("Heard:")} "{check.text}"
        </span>
      </div>
      <span className={styles.alertMeta}>
        {t("The check did not finish. Keep to approved wording.")}
        {check.phrases.length ? ` (${check.phrases.join(", ")})` : ""}
      </span>
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
  const t = useT();
  return (
    <div className={cx(styles.banner, styles.switch)} data-testid="host-switch-banner" role="status">
      <span className={styles.bannerIcon} aria-hidden>
        <ArrowLeftRight />
      </span>
      <div className={styles.bannerBody}>
        <span className={styles.switchTitle}>{t("Switching to {name}", { name: productName })}</span>
      </div>
      <span className={cx(styles.switchCount, "tabular")} aria-label={t("{n} seconds", { n: secondsLeft })}>
        {Math.max(1, secondsLeft)}
      </span>
      <button type="button" className={styles.switchCancel} onClick={onCancel}>
        {t("Cancel switch (Esc)")}
      </button>
    </div>
  );
}

/** D-349 SWITCH_MODE=immediate: the prompter already switched; the host can take it back for a few seconds. */
export function SwitchedBar({ productName, onUndo }: { productName: string; onUndo: () => void }) {
  const t = useT();
  return (
    <div className={cx(styles.banner, styles.switch)} data-testid="host-switched-bar" role="status">
      <span className={styles.bannerIcon} aria-hidden>
        <ArrowLeftRight />
      </span>
      <div className={styles.bannerBody}>
        <span className={styles.switchTitle}>{t("Switched to {name}", { name: productName })}</span>
      </div>
      <button type="button" className={styles.switchCancel} onClick={onUndo}>
        {t("Undo (Esc)")}
      </button>
    </div>
  );
}

/** D-106: in the prompter card, where the alert was. */
export function CorrectedBar() {
  const t = useT();
  return (
    <div className={styles.corrected} data-testid="host-corrected" role="status">
      <Check aria-hidden />
      {t("Corrected")}
    </div>
  );
}
