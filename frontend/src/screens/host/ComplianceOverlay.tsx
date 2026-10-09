// HIGH-risk compliance alert (§12.3.7). D-106: shown at the top of the prompter card, where the host
// is already looking, until the correction is confirmed; the prompter points stay visible below.
// On mount it acknowledges the render once per alert (metrics, §8.16).
import { useEffect } from "react";

import { useT } from "../../app/i18n";
import { type HighAlertView } from "../../app/selectors";
import type { Alert, Catalog } from "../../app/types";
import { Elapsed } from "../../components";
import { AlertMore, KindLabel } from "./Banners";
import { citedTitle, factSayLine, ruleInfo } from "./hostSelectors";
import styles from "./host.module.css";

export function ComplianceOverlay({
  view,
  fresh = false,
  catalog,
  serverOffsetMs,
  onRendered,
  more = 0,
  retraction = "",
  timing = null,
  then = [],
  cleared = 0,
  timingOf = () => null,
}: {
  view: HighAlertView;
  /** D-177: within RED_BLOCK_MS of the alert: highlighted (a repeat is a new alert, so it highlights again) */
  fresh?: boolean;
  catalog: Catalog | null;
  serverOffsetMs: number;
  onRendered: (alertId: string) => void;
  /** D-402: active alerts the stack does not show (on the last box shown) */
  more?: number;
  /** D-436: the language pack's retraction phrase, said before say_instead */
  retraction?: string;
  /** D-439: "Shown in 4.2 s" (null: not known) */
  timing?: string | null;
  /** D-442: the line's other active alerts (reds, then fact notes), each said after the red's line */
  then?: Alert[];
  /** D-442: how many of the line's alerts are no longer active */
  cleared?: number;
  /** D-439: each member's own "Shown in" label */
  timingOf?: (a: Alert) => string | null;
}) {
  const t = useT();
  const { alert, position, total } = view;
  const cited = citedTitle(alert);  // D-433: the cited document and section (the rule id is a slug since D-358)
  const rule = cited ? { title: cited, ref: "" } : ruleInfo(catalog, alert.rule_id, alert.product_id);

  const thenIds = then.map((a) => a.alert_id).join(",");
  useEffect(() => {
    onRendered(alert.alert_id);
    for (const id of thenIds ? thenIds.split(",") : []) onRendered(id);  // D-442: the grouped members are shown too
  }, [alert.alert_id, thenIds, onRendered]);
  // D-442: "2 issues: Regulation + Product info", or "1 left" once a member of the line is cleared
  const kinds = [...new Set(["Regulation", ...then.map((a) => (a.kind === "fact" ? "Product info" : "Regulation"))])];
  const members = 1 + then.length;
  const group = cleared > 0 ? t("{n} left", { n: members })
    : members > 1 ? t("{n} issues: {kinds}", { n: members, kinds: kinds.map((k) => t(k)).join(" + ") }) : null;

  return (
    <div className={`${styles.alertBlock} ${styles.alertHigh} ${fresh ? styles.alertHighFresh : ""}`}
      data-testid="host-compliance-overlay" data-fresh={fresh} role="alert"
      aria-live="assertive" aria-label={t("High-risk claim")}>
      <div className={styles.alertTop}>
        <KindLabel law />
        {group && <span className={styles.alertGroup} data-testid="host-alert-group">{group}</span>}
        <span className={styles.alertSaid}>
          {t("Heard:")} "{alert.span}"
        </span>
        {total > 1 && (
          <span className={`${styles.ofN} tabular`} data-testid="host-overlay-count">
            {t("{a} of {b}", { a: position, b: total })}
          </span>
        )}
        <AlertMore n={more} />
      </div>
      <span className={styles.alertSayLabel}>{t("Take it back, then say:")}</span>
      <span className={styles.alertSay}>“{[retraction, alert.say_instead].filter(Boolean).join(" ")}”</span>
      {then.map((a) => {
        const line = a.kind === "fact" ? factSayLine(catalog, a) : a.say_instead ?? "";
        const when = timingOf(a);
        return (
          <div key={a.alert_id} className={styles.alertThen} data-testid="host-alert-then" data-kind={a.kind}>
            <span className={styles.alertSayLabel}>{t("Then:")}</span>
            {line && <span className={styles.alertThenSay}>“{line}”</span>}
            {when && <span className={styles.alertTiming} data-testid="host-alert-timing">{when}</span>}
          </div>
        );
      })}
      <div className={styles.alertMeta}>
        <span className={styles.statusDot} aria-hidden />
        <span>{t("Waiting for your correction")}</span>
        {alert.shown_at && (
          <Elapsed since={alert.shown_at} serverOffsetMs={serverOffsetMs} format="mmss" className={styles.statusTimer} />
        )}
        <span className={styles.alertRule}>
          {rule.title}
          {rule.ref ? ` · ${rule.ref}` : ""}
        </span>
        {timing && <span className={styles.alertTiming} data-testid="host-alert-timing">{timing}</span>}
      </div>
    </div>
  );
}
