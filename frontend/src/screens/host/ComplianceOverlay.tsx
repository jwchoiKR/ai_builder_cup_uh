// HIGH-risk compliance alert (§12.3.7). D-106: shown at the top of the prompter card, where the host
// is already looking, until the correction is confirmed; the prompter points stay visible below.
// On mount it acknowledges the render once per alert (metrics, §8.16).
import { ShieldAlert, ShieldQuestionMark } from "lucide-react";
import { useEffect } from "react";

import { useT } from "../../app/i18n";
import { shortSay, type HighAlertView } from "../../app/selectors";
import type { Catalog } from "../../app/types";
import { Elapsed } from "../../components";
import { ruleInfo } from "./hostSelectors";
import styles from "./host.module.css";

export function ComplianceOverlay({
  view,
  fresh = false,
  catalog,
  serverOffsetMs,
  onRendered,
}: {
  view: HighAlertView;
  /** D-177: within RED_BLOCK_MS of the alert: highlighted (a repeat is a new alert, so it highlights again) */
  fresh?: boolean;
  catalog: Catalog | null;
  serverOffsetMs: number;
  onRendered: (alertId: string) => void;
}) {
  const t = useT();
  const { alert, position, total } = view;
  const rule = ruleInfo(catalog, alert.rule_id, alert.product_id);

  useEffect(() => {
    onRendered(alert.alert_id);
  }, [alert.alert_id, onRendered]);

  return (
    <div className={`${styles.alertBlock} ${styles.alertHigh} ${fresh ? styles.alertHighFresh : ""}`}
      data-testid="host-compliance-overlay" data-fresh={fresh} role="alert"
      aria-live="assertive" aria-label={t("High-risk claim")}>
      <div className={styles.alertTop}>
        <span className={styles.riskBadge}>
          <ShieldAlert aria-hidden />
          {t("HIGH-RISK CLAIM")}
        </span>
        {alert.unverified && (
          <span className={`${styles.riskBadge} ${styles.unverifiedBadge}`} data-testid="host-unverified">
            <ShieldQuestionMark aria-hidden />
            {alert.unverified_reason ? t("Unverified (AI response delayed)") : t("AI check unavailable")}
          </span>
        )}
        <span className={styles.alertSaid}>
          {t("Heard:")} "{alert.span}"
        </span>
        {total > 1 && (
          <span className={`${styles.ofN} tabular`} data-testid="host-overlay-count">
            {t("{a} of {b}", { a: position, b: total })}
          </span>
        )}
      </div>
      <span className={styles.alertSayLabel}>{t("Say this instead.")}</span>
      <span className={styles.alertSay}>“{shortSay(alert.say_instead)}”</span>
      <div className={styles.alertMeta}>
        <span className={styles.statusDot} aria-hidden />
        {t("Waiting for your correction")}
        {alert.shown_at && (
          <Elapsed since={alert.shown_at} serverOffsetMs={serverOffsetMs} format="mmss" className={styles.statusTimer} />
        )}
        <span className={styles.alertRule}>
          {rule.title}
          {rule.ref ? ` · ${rule.ref}` : ""}
        </span>
      </div>
    </div>
  );
}
