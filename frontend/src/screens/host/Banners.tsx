// Cue strip (§12.3.2), fact note (§12.3.5), MEDIUM banner (§12.3.6), switch banner (§12.3.9) and
// the green "Corrected" confirmation (§12.3.7).
import { ArrowLeftRight, Check, CircleAlert, Headphones, ShieldAlert } from "lucide-react";
import { useEffect } from "react";

import { useT } from "../../app/i18n";
import { TEST_QUALIFIER_RULE } from "../../app/selectors";
import type { Alert, Catalog, HostCue } from "../../app/types";
import { factContext, factSayLine, factSourceLabel, fieldLabel, ruleInfo } from "./hostSelectors";
import styles from "./host.module.css";

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

/** D-402 (user): red and orange at the same level: a large text label says which, so colour alone never carries it */
export function KindLabel({ law = false }: { law?: boolean }) {
  const t = useT();
  return (
    <span className={styles.kindLabel} data-testid="host-alert-kind">
      {law ? t("Regulation") : t("Product info")}
    </span>
  );
}

/** D-402: at most two alert boxes show; the last one shown carries "+N", the active alerts not shown */
export function AlertMore({ n }: { n: number }) {
  return n > 0 ? <span className={styles.alertCount} data-testid="host-alert-more">+{n}</span> : null;
}

export function FactNote({ alert, catalog, onRendered, count = 1, more = 0 }: {
  alert: Alert;
  catalog: Catalog | null;
  onRendered?: (alertId: string) => void;
  /** D-399: how many active notes cite this note's passage (this one is the newest) */
  count?: number;
  /** D-402: active alerts the stack does not show */
  more?: number;
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
        <KindLabel />
        <span className={styles.warnBadge}>
          <CircleAlert aria-hidden />
          {alert.heard_check ? t("CHECK WHAT WAS SAID") : `${t(label).toUpperCase()} ${t("CORRECTION")}`}
        </span>
        {count > 1 && <span className={styles.alertCount} data-testid="host-alert-count">×{count}</span>}
        <AlertMore n={more} />
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
  factFixed = null,
  onRendered,
  count = 1,
  more = 0,
  factCount = 1,
}: {
  alert: Alert;
  catalog: Catalog | null;
  /** D-105: the fact note on the same sentence, shown in this card instead of its own. */
  fact?: Alert | null;
  /** D-418: that note once corrected: its right line stays on the card */
  factFixed?: Alert | null;
  onRendered?: (alertId: string) => void;
  /** D-399: how many unresolved MEDIUM alerts cite this rule (this one is the newest) */
  count?: number;
  /** D-402: active alerts the stack does not show */
  more?: number;
  /** D-403: how many active notes cite the merged note's passage (the note shown is the newest) */
  factCount?: number;
}) {
  // D-106: a block at the top of the prompter card, yellow, with the replacement as the biggest text.
  const t = useT();
  useEffect(() => {
    onRendered?.(alert.alert_id);
    if (fact) onRendered?.(fact.alert_id);
  }, [alert.alert_id, fact?.alert_id, onRendered]);
  const rule = ruleInfo(catalog, alert.rule_id, alert.product_id);
  const qualifier = alert.rule_id === TEST_QUALIFIER_RULE;
  // D-418: with the line's fact note, the card says the note's line once (its say, else its value), and the qualifier
  // becomes the top instruction; without one, the model's say_instead
  const factLine = fact ?? factFixed;
  return (
    <div className={cx(styles.alertBlock, styles.alertMedium)} data-testid="host-medium-banner" role="alert">
      <div className={styles.alertTop}>
        <KindLabel />
        <span className={styles.warnBadge}>
          <ShieldAlert aria-hidden />
          {/* D-355: a suggestion; any wording that says where the result comes from corrects it */}
          {!qualifier ? t("CHECK WORDING")
            : factLine ? t("Also say where the result comes from (e.g. 'in our in-house test')")
              : t("Say where the result comes from (e.g. 'in our in-house test')")}
        </span>
        {count > 1 && <span className={styles.alertCount} data-testid="host-alert-count">×{count}</span>}
        <AlertMore n={more} />
        {alert.unverified && (
          <span className={`${styles.riskBadge} ${styles.unverifiedBadge}`} data-testid="host-unverified">
            {alert.unverified_reason ? t("Unverified (AI response delayed)") : t("AI check unavailable")}
          </span>
        )}
        <span className={styles.alertSaid}>
          {t("Heard:")} "{alert.span}"
        </span>
      </div>
      <span className={styles.alertSayLabel}>{t("Say this instead.")}</span>
      {factLine ? (
        <span className={styles.alertSay} data-testid="host-medium-fact">
          {/* D-401: the note's own say line, as on a fact note (D-396); else its correct value */}
          “{factLine.say?.trim() || factLine.correct_value}”{/* D-422: a blank say is a missing one */}
          {fact && factCount > 1 && <span className={styles.alertCount} data-testid="host-medium-fact-count"> ×{factCount}</span>}
        </span>
      ) : (
        <span className={styles.alertSay}>
          {alert.say_instead ? `“${alert.say_instead}”` : t("Say the result with where it comes from (e.g. 'in our in-house test').")}
        </span>
      )}
      <span className={styles.alertMeta}>
        <span className={styles.alertRule}>{rule.title}</span>
      </span>
    </div>
  );
}

/** D-412: the host's words for a failed check (no codes) */
const UNCHECKED_CAUSE: Record<string, string> = { busy: "AI busy", timeout: "AI slow", invalid: "AI error", error: "AI error" };

/** D-412: every line no judge could check, as one compact strip outside the alert boxes; it goes away when the judges
 *  answer normally again */
export function UncheckedStrip({ count, cause }: { count: number; cause: string | null }) {
  const t = useT();
  if (count === 0) return null;
  const word = t(UNCHECKED_CAUSE[cause ?? "error"] ?? "AI error");
  return (
    <span className={styles.previewTag} data-testid="host-unchecked" role="status">
      <CircleAlert aria-hidden />
      {count === 1 ? t("{cause}: 1 line unchecked", { cause: word }) : t("{cause}: {n} lines unchecked", { cause: word, n: count })}
    </span>
  );
}

/** D-349: the prompter already switched; the host can take it back for a few seconds. */
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
