// Post-broadcast summary page body (DEV_SPEC §12.8). Pure: renders the data it is given.
import { Button, Chip, Eyebrow, HubLink, SettingsButton } from "../../components";
import type { ThemeName, ThemePref } from "../../app/theme";
import {
  agentLabel,
  correctedIn,
  fieldLabel,
  formatDate,
  formatDuration,
  formatMsAsSeconds,
  formatOffset,
} from "./format";
import type { ProductStats, Recap, SummaryData, UnansweredGroup } from "./types";
import styles from "./summary.module.css";

const ANSWER_KIND_LABEL: Record<string, string> = {
  ai_answer: "AI answer",
  host_answer: "Host answer",
  brand_answer: "DAON LAB",
};

export interface SummaryViewProps {
  data: SummaryData;
  theme: ThemeName;
  /** the shared Settings gear (theme and UI language); absent in a Studio pane */
  themePref?: ThemePref;
  onSetTheme?: (t: ThemePref) => void;
  onExport: () => void;
  /** D-097: PDF report through the print dialog */
  onExportPdf?: () => void;
  onBack: () => void;
  embedded?: boolean;
}

/** D-202: a share as a whole percent, "–" when the server did not send it. */
const pctOrDash = (v: number | undefined) => (v === undefined ? "–" : `${Math.round(v * 100)}%`);

function UnansweredList({ items }: { items: UnansweredGroup[] }) {
  if (!items.length) return <p className={styles.muted}>No unanswered questions.</p>;
  return (
    <ul className={styles.list}>
      {items.map((g) => (
        <li key={g.group_id}>
          <span>{g.canonical_question}</span>
          <span className={styles.muted}> · {g.unique_askers} asking</span>
        </li>
      ))}
    </ul>
  );
}

function ProductCard({ p }: { p: ProductStats }) {
  const over = p.duration_sec > p.planned_duration_sec;
  return (
    <section className={styles.card} data-testid={`summary-product-${p.product_id}`}>
      <h3 className={styles.cardTitle}>{p.name}</h3>
      <dl className={styles.facts}>
        <div>
          <dt>Duration</dt>
          <dd className="tabular">
            {formatDuration(p.duration_sec)} <span className={styles.muted}>/ {formatDuration(p.planned_duration_sec)} planned</span>
            {over && <Chip tone="fact" className={styles.inlineChip}>Overtime</Chip>}
          </dd>
        </div>
        <div>
          <dt>Required points</dt>
          <dd className="tabular">
            {p.required_points_covered} / {p.required_points_total} covered
          </dd>
        </div>
        <div>
          <dt>Comments</dt>
          <dd className="tabular">{p.comments}</dd>
        </div>
        <div>
          <dt>Questions</dt>
          <dd className="tabular">{p.questions}</dd>
        </div>
        <div>
          <dt>Question groups</dt>
          <dd className="tabular">{p.groups}</dd>
        </div>
      </dl>
      {p.missing_points.length > 0 && (
        <div className={styles.block}>
          <Eyebrow>Missing required points</Eyebrow>
          <ul className={styles.list}>
            {p.missing_points.map((m) => (
              <li key={m.point_id}>
                <span className={styles.muted}>{m.point_id}</span> {m.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.block}>
        <Eyebrow>Answered groups</Eyebrow>
        <div className={styles.chips}>
          {(Object.keys(ANSWER_KIND_LABEL) as (keyof ProductStats["answered_groups"])[]).map((k) => (
            <Chip key={k} tone={p.answered_groups[k] ? "ok" : "neutral"}>
              {ANSWER_KIND_LABEL[k]} {p.answered_groups[k]}
            </Chip>
          ))}
        </div>
      </div>
      <div className={styles.block}>
        <Eyebrow>Unanswered</Eyebrow>
        <UnansweredList items={p.unanswered_groups} />
      </div>
    </section>
  );
}

function RecapBlock({ recap, status, error }: { recap: Recap | null; status: SummaryData["status"]; error: string | null }) {
  return (
    <section className={`${styles.card} ${styles.recap}`} data-testid="summary-recap">
      <header className={styles.recapHead}>
        <Eyebrow>AI recap</Eyebrow>
        <span className={styles.muted}>AI-written recap based on the numbers below</span>
      </header>
      {recap ? (
        <>
          <p className={styles.headline}>{recap.headline}</p>
          <div className={styles.recapGrid}>
            {(
              [
                ["Highlights", recap.highlights],
                ["Watch-outs", recap.watch_outs],
                ["Follow-ups", recap.follow_ups],
              ] as const
            ).map(([title, items]) => (
              <div key={title}>
                <h4 className={styles.recapTitle}>{title}</h4>
                {items.length ? (
                  <ul className={styles.list}>
                    {items.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.muted}>None.</p>
                )}
              </div>
            ))}
          </div>
        </>
      ) : status === "computing" ? (
        <p className={styles.muted}>Writing the recap…</p>
      ) : status === "not_ended" ? (
        <p className={styles.muted}>The recap is written when the broadcast ends.</p>
      ) : (
        <p className={styles.muted} title={error ?? undefined}>
          Recap unavailable. The numbers below are complete.
        </p>
      )}
    </section>
  );
}

export function SummaryView({ data, theme, themePref, onSetTheme, onExport, onExportPdf, onBack, embedded }: SummaryViewProps) {
  const s = data.stats;
  const start = s.started_at;
  return (
    <div className={styles.root} data-theme={theme} data-testid="summary">
      <header className={styles.header}>
        <div>
          <Eyebrow>
            {!embedded && (
              <>
                <HubLink sessionId={s.session_id} /> ·{" "}
              </>
            )}
            Broadcast summary
          </Eyebrow>
          <h1 className={styles.title}>{s.title}</h1>
          <p className={styles.subtitle}>
            {formatDate(s.started_at)} · <span className="tabular">{formatDuration(s.duration_sec)}</span> total
            {data.status === "not_ended" && <Chip tone="live" className={styles.inlineChip}>Live: numbers so far</Chip>}
          </p>
        </div>
        <div className={styles.actions}>
          {onExportPdf && (
            <Button
              onClick={onExportPdf}
              disabled={data.status === "computing"}
              title={data.status === "computing" ? "Waiting for the AI recap" : "Save the report as a PDF"}
            >
              Export PDF
            </Button>
          )}
          <Button onClick={onExport}>Export JSON</Button>
          <Button variant="primary" onClick={onBack}>
            Back to hub
          </Button>
          {!embedded && onSetTheme && <SettingsButton themePref={themePref} onTheme={onSetTheme} />}
        </div>
      </header>

      {/* D-092: the executive summary comes first; most readers stop here */}
      <RecapBlock recap={data.recap} status={data.status} error={data.error} />

      <section className={styles.totals} aria-label="Totals">
        {(
          [
            ["Comments", s.totals.comments],
            ["Questions", s.totals.questions],
            ["Question groups", s.totals.groups],
            ["Hidden", s.totals.hidden_comments],
            ["Instant answers", s.cache.instant_answers],
            ["Composed answers", s.cache.composed_answers],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className={styles.total}>
            <span className={styles.totalValue}>{value}</span>
            <span className={styles.muted}>{label}</span>
          </div>
        ))}
      </section>

      <div className={styles.products}>
        {s.products.map((p) => (
          <ProductCard key={p.product_id} p={p} />
        ))}
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>General questions</h3>
          <UnansweredList items={s.general_unanswered_groups} />
        </section>
      </div>

      {/* D-096: one box for both logs, same columns, each with its own heading */}
      <section className={styles.card} data-testid="summary-logs">
        <h3 className={styles.cardTitle}>Compliance and fact log</h3>
        <h4 className={styles.logTitle}>Compliance log</h4>
        {s.compliance_alerts.length ? (
          <table className={styles.table} data-testid="summary-compliance">
            <thead>
              <tr>
                <th>Time</th>
                <th>You said</th>
                <th>Rule</th>
                <th>Alert latency</th>
                <th>Corrected in</th>
                <th>Correction</th>
                <th>Unverified</th>
              </tr>
            </thead>
            <tbody>
              {s.compliance_alerts.map((a) => (
                <tr key={a.alert_id}>
                  <td className="tabular">{formatOffset(a.shown_at, start)}</td>
                  <td>“{a.span}”</td>
                  <td>
                    {a.rule_title ?? a.rule_id}
                    {a.severity && (
                      <Chip tone={a.severity === "HIGH" ? "risk" : "fact"} className={styles.inlineChip}>
                        {a.severity}
                      </Chip>
                    )}
                  </td>
                  <td className="tabular">{formatMsAsSeconds(a.speech_end_to_shown_ms)}</td>
                  <td className="tabular">{correctedIn(a.shown_to_corrected_ms)}</td>
                  <td>{a.corrected_text ?? "–"}</td>
                  <td>{a.unverified ? "Yes" : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className={styles.muted}>No compliance alerts.</p>
        )}

        <h4 className={styles.logTitle}>Fact log</h4>
        {s.fact_alerts.length ? (
          <table className={styles.table} data-testid="summary-facts">
            <thead>
              <tr>
                <th>Time</th>
                <th>You said</th>
                <th>Field</th>
                <th>Alert latency</th>
                <th>Corrected in</th>
                <th>Correction</th>
                <th>Unverified</th>
              </tr>
            </thead>
            <tbody>
              {s.fact_alerts.map((f) => (
                <tr key={f.alert_id}>
                  <td className="tabular">{f.shown_at != null ? formatOffset(f.shown_at, start) : "–"}</td>
                  <td>{f.span ? `“${f.span}”` : "–"}</td>
                  <td>
                    {fieldLabel(f.field)}
                    <span className={styles.factValues}>
                      {" "}
                      {f.stated_value ?? "–"} → {f.correct_value ?? "–"}
                    </span>
                  </td>
                  <td className="tabular">{formatMsAsSeconds(f.speech_end_to_shown_ms ?? null)}</td>
                  <td className="tabular">
                    {f.shown_to_corrected_ms !== undefined
                      ? correctedIn(f.shown_to_corrected_ms)
                      : f.corrected
                        ? formatMsAsSeconds(f.time_to_correction_ms)
                        : "Not corrected"}
                  </td>
                  <td>{f.corrected_text ?? "–"}</td>
                  <td>–</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className={styles.muted}>No fact corrections.</p>
        )}
      </section>

      <div className={styles.twoCol}>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>Promotions</h3>
          {s.promos.length ? (
            <table className={styles.table} data-testid="summary-promos">
              <thead>
                <tr>
                  <th>Promotion</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {s.promos.map((p, i) => (
                  <tr key={`${p.promo_id}-${i}`}>
                    <td>{p.title}</td>
                    <td className="tabular">{formatOffset(p.started_at, start)}</td>
                    <td className="tabular">{p.ended_at === null ? "Running at end" : formatOffset(p.ended_at, start)}</td>
                    <td className="tabular">{formatDuration(p.duration_sec)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={styles.muted}>No promotions ran.</p>
          )}
        </section>

      <section className={styles.card}>
        <h3 className={styles.cardTitle}>Agent latency</h3>
        <table className={styles.table} data-testid="summary-agents">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Calls</th>
              <th>Failed</th>
              <th>In time</th>
              <th>p50</th>
              <th>p95</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(s.agent_latency).map(([name, a]) => (
              <tr key={name}>
                <td>{agentLabel(name)}</td>
                <td className="tabular">{a.attempts ?? a.calls}</td>
                <td className="tabular">{pctOrDash(a.failure_rate)}</td>
                <td className="tabular">{pctOrDash(a.deadline_attainment)}</td>
                <td className="tabular">{formatMsAsSeconds(a.p50_ms)}</td>
                <td className="tabular">{formatMsAsSeconds(a.p95_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className={styles.muted}>
          Triage cache: {s.cache.triage_hits} hits, {s.cache.triage_misses} misses.
        </p>
      </section>
      </div>
    </div>
  );
}
