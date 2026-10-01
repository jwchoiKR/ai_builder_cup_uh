// HIGH-risk compliance overlay (§12.3.7): covers everything below the top bar until the correction is
// confirmed. On mount it acknowledges the render once per alert (metrics, §8.16).
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
    <div className={styles.overlay} data-testid="host-compliance-overlay" role="alertdialog" aria-live="assertive"
      aria-label="High-risk claim">
      <div className={styles.overlayInner}>
        <div className={styles.overlayBadges}>
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
          {total > 1 && (
            <span className={`${styles.ofN} tabular`} data-testid="host-overlay-count">
              {position} of {total}
            </span>
          )}
        </div>
        <span className={styles.pause}>PAUSE. CORRECT YOUR LAST STATEMENT.</span>
        <span className={styles.headline}>Say this instead.</span>
        <span className={styles.sayInstead}>“{alert.say_instead}”</span>
        <div className={styles.overlayCols}>
          <div>
            <div className={styles.colLabel}>YOU SAID</div>
            <div className={styles.colValue}>"{alert.span}"</div>
          </div>
          <div>
            <div className={styles.colLabel}>POLICY REFERENCE</div>
            <div className={styles.colValue}>
              {rule.title}
              {rule.ref ? ` · ${rule.ref}` : ""}
            </div>
          </div>
        </div>
        <div className={styles.status}>
          <span className={styles.statusDot} aria-hidden />
          Waiting for your correction
          {alert.shown_at && (
            <Elapsed since={alert.shown_at} serverOffsetMs={serverOffsetMs} format="mmss" className={styles.statusTimer} />
          )}
        </div>
        <span className={styles.overlayFooter}>This screen clears when your correction is confirmed.</span>
      </div>
    </div>
  );
}
