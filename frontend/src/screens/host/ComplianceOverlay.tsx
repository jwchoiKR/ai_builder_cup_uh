// HIGH-risk compliance alert (§12.3.7). D-106: shown at the top of the prompter card, where the host
// is already looking, until the correction is confirmed; the prompter points stay visible below.
// On mount it acknowledges the render once per alert (metrics, §8.16).
import { ShieldAlert, ShieldQuestionMark } from "lucide-react";
import { useEffect } from "react";

import type { HighAlertView } from "../../app/selectors";
import type { Catalog } from "../../app/types";
import { Elapsed } from "../../components";
import { ruleInfo } from "./hostSelectors";
import styles from "./host.module.css";

export function ComplianceOverlay({
  view,
  catalog,
  serverOffsetMs,
  onRendered,
}: {
  view: HighAlertView;
  catalog: Catalog | null;
  serverOffsetMs: number;
  onRendered: (alertId: string) => void;
}) {
  const { alert, position, total } = view;
  const rule = ruleInfo(catalog, alert.rule_id);

  useEffect(() => {
    onRendered(alert.alert_id);
  }, [alert.alert_id, onRendered]);

  return (
    <div className={`${styles.alertBlock} ${styles.alertHigh}`} data-testid="host-compliance-overlay" role="alert"
      aria-live="assertive" aria-label="High-risk claim">
      <div className={styles.alertTop}>
        <span className={styles.riskBadge}>
          <ShieldAlert aria-hidden />
          HIGH-RISK CLAIM
        </span>
        {alert.unverified && (
          <span className={`${styles.riskBadge} ${styles.unverifiedBadge}`} data-testid="host-unverified">
            <ShieldQuestionMark aria-hidden />
            AI check unavailable
          </span>
        )}
        <span className={styles.alertSaid}>Heard: "{alert.span}"</span>
        {total > 1 && (
          <span className={`${styles.ofN} tabular`} data-testid="host-overlay-count">
            {position} of {total}
          </span>
        )}
      </div>
      <span className={styles.alertSayLabel}>Say this instead.</span>
      <span className={styles.alertSay}>“{alert.say_instead}”</span>
      <div className={styles.alertMeta}>
        <span className={styles.statusDot} aria-hidden />
        Waiting for your correction
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
