// Alert stack (§12.4.2-§12.4.4): compliance cards (red), fact cards (amber), system cards (neutral).
import { AlertTriangle, CircleAlert, Info, ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import { api } from "../../app/api";
import type { Alert } from "../../app/types";
import { Button, Chip } from "../../components";
import { useAction, useOperator } from "./context";
import { NoticeDialog } from "./Dialogs";
import {
  alertCardState,
  complianceTitle,
  correctedLine,
  fieldLabel,
  missingPointsCue,
  PURCHASE_FIELDS,
  ruleInfo,
  sentenceCase,
  sourceLabel,
  stackAlerts,
  systemCards,
  type SystemCard,
} from "./model";
import styles from "./operator.module.css";

export function AlertStack() {
  const { state, catalog, now } = useOperator();
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());
  const alerts = stackAlerts(state, now);
  const system = systemCards(state, catalog, now).filter((c) => !dismissed.has(c.key));
  if (!alerts.length && !system.length) return null;
  return (
    <section className={styles.alertStack} aria-label="Alert stack">
      {alerts.map((a) =>
        a.kind === "compliance" ? <ComplianceCard key={a.alert_id} alert={a} /> : <FactCard key={a.alert_id} alert={a} />,
      )}
      {system.map((c) => (
        <SystemAlertCard key={c.key} card={c} onDismiss={() => setDismissed((d) => new Set(d).add(c.key))} />
      ))}
    </section>
  );
}

function ComplianceCard({ alert: a }: { alert: Alert }) {
  const { sid, catalog, now } = useOperator();
  const [notice, setNotice] = useState(false);
  const act = useAction();
  const state = alertCardState(a);
  const rule = ruleInfo(catalog, a.rule_id);
  const corrected = correctedLine(a);
  const cls = [styles.alertCard, styles.riskCard, state === "escalated" && styles.escalated, state === "corrected" && styles.correctedCard]
    .filter(Boolean)
    .join(" ");
  return (
    <article className={cls} data-testid={`op-alert-${a.alert_id}`} data-kind="compliance" data-state={state}>
      <header className={styles.alertHead}>
        <ShieldAlert size={16} aria-hidden />
        <span className={styles.alertTitle}>{complianceTitle(a, now)}</span>
        <Chip tone="risk">{a.severity ?? "HIGH"}</Chip>
        {a.unverified && <Chip tone="fact">AI check unavailable</Chip>}
      </header>
      {corrected ? (
        <p className={styles.alertText}>{corrected}</p>
      ) : (
        <>
          <blockquote className={styles.span}>“{a.span}”</blockquote>
          <p className={styles.alertMeta}>
            Rule:{" "}
            {catalog?.policy_pdf_url ? (
              <a href={catalog.policy_pdf_url} target="_blank" rel="noreferrer">
                {rule?.title ?? a.rule_id}
                {rule?.source_ref ? ` · ${rule.source_ref}` : ""}
              </a>
            ) : (
              <>
                {rule?.title ?? a.rule_id}
                {rule?.source_ref ? ` · ${rule.source_ref}` : ""}
              </>
            )}
          </p>
          {a.say_instead && <p className={styles.alertMeta}>Say: “{a.say_instead}”</p>}
          <p className={styles.helper}>
            {a.severity === "MEDIUM"
              ? "The host is seeing a correction banner above the prompter."
              : "The host is seeing a full-screen correction prompt."}
          </p>
          <div className={styles.actions}>
            <Button size="sm" variant="danger" disabled={act.busy} onClick={() => act.run(() => api.alertCue(sid, a.alert_id))}>
              Send correction cue
            </Button>
            <Button size="sm" onClick={() => setNotice(true)}>
              Post notice
            </Button>
            <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => act.run(() => api.dismissAlert(sid, a.alert_id))}>
              Dismiss false alert
            </Button>
          </div>
          {act.error && <p className={styles.error}>{act.error}</p>}
        </>
      )}
      {notice && <NoticeDialog alertId={a.alert_id} onClose={() => setNotice(false)} />}
    </article>
  );
}

function FactCard({ alert: a }: { alert: Alert }) {
  const { sid, catalog } = useOperator();
  const [notice, setNotice] = useState(false);
  const act = useAction();
  const state = alertCardState(a);
  const label = fieldLabel(catalog, a.field);
  const corrected = correctedLine(a);
  const cls = [styles.alertCard, styles.factCard, state === "corrected" && styles.correctedCard].filter(Boolean).join(" ");
  return (
    <article className={cls} data-testid={`op-alert-${a.alert_id}`} data-kind="fact" data-state={state}>
      <header className={styles.alertHead}>
        <CircleAlert size={16} aria-hidden />
        <span className={styles.alertTitle}>
          {sentenceCase(label)} correction · {a.stated_value} → {a.correct_value}
        </span>
        {state === "hidden_from_host" && <Chip tone="risk">Not corrected</Chip>}
      </header>
      {corrected ? (
        <p className={styles.alertText}>{corrected}</p>
      ) : (
        <>
          <p className={styles.alertMeta}>The {label} differs from the host's statement.</p>
          <p className={styles.alertMeta}>Source: {sourceLabel(catalog, a.passage_id)}</p>
          <div className={styles.actions}>
            <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.resendFactNote(sid, a.alert_id))}>
              Resend to host
            </Button>
            {a.field && PURCHASE_FIELDS.has(a.field) && (
              <Button size="sm" onClick={() => setNotice(true)}>
                Post notice
              </Button>
            )}
            <Button size="sm" variant="ghost" disabled={act.busy} onClick={() => act.run(() => api.dismissAlert(sid, a.alert_id))}>
              Dismiss
            </Button>
          </div>
          {act.error && <p className={styles.error}>{act.error}</p>}
        </>
      )}
      {notice && <NoticeDialog alertId={a.alert_id} onClose={() => setNotice(false)} />}
    </article>
  );
}

function SystemAlertCard({ card, onDismiss }: { card: SystemCard; onDismiss: () => void }) {
  const { sid, catalog } = useOperator();
  const act = useAction();
  const Icon = card.kind === "overtime" ? Info : AlertTriangle;
  return (
    <article className={[styles.alertCard, styles.systemCard].join(" ")} data-testid={`op-system-${card.key}`} data-kind={card.kind}>
      <header className={styles.alertHead}>
        <Icon size={16} aria-hidden />
        <span className={styles.alertTitle}>{card.text}</span>
        <button type="button" className={styles.iconBtn} onClick={onDismiss} aria-label="Dismiss">
          <X size={14} aria-hidden />
        </button>
      </header>
      {card.kind === "missing_points" && card.missingTexts && (
        <div className={styles.actions}>
          <Button
            size="sm"
            disabled={act.busy}
            onClick={() => act.run(() => api.sendCue(sid, { text: missingPointsCue(catalog, card.missingTexts ?? []) }))}
          >
            Send cue
          </Button>
        </div>
      )}
      {act.error && <p className={styles.error}>{act.error}</p>}
    </article>
  );
}
