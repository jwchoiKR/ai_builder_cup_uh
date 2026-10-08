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
import type { CommentInsights, ProductStats, Recap, SummaryData, UnansweredGroup } from "./types";
import styles from "./summary.module.css";

const ANSWER_KIND_LABEL: Record<string, string> = {
  ai_answer: "AI answer",
  host_answer: "Host answer",
  brand_answer: "Brand answer",
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

const APPROVAL_REASONS: Record<string, string> = {
  health: "Health or safety",
  claim: "What the product will do",
  test_results: "Test results",
  certification: "Certificates",
  personal: "Personal advice",
  outside: "Order, delivery or shop",
  host_line: "Follow-up on the host",
  unclear: "Unclear or two questions",
};

const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

/** When viewers asked: one bar per slice of the broadcast (questions dark, other comments light). */
function Timeline({ t }: { t: NonNullable<CommentInsights["timeline"]> }) {
  const top = Math.max(1, ...t.bins.map((b) => b.comments));
  const peak = t.peak;
  return (
    <div data-testid="summary-insights-timeline">
      <p className={styles.muted}>When viewers asked (time into the broadcast, {t.bin_sec / 60} min per bar)</p>
      <div className={styles.timeline} role="img" aria-label="Questions and comments over the broadcast">
        {t.bins.map((b) => (
          <div
            key={b.start_sec}
            className={styles.timelineBar}
            title={`${clock(b.start_sec)}: ${b.questions} questions, ${b.comments} comments${b.product ? ` · ${b.product}` : ""}`}
          >
            <span className={styles.timelineOther} style={{ height: `${((b.comments - b.questions) / top) * 100}%` }} />
            <span className={styles.timelineQuestions} style={{ height: `${(b.questions / top) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className={styles.timelineAxis}>
        <span>{clock(0)}</span>
        <span>{clock(t.bins[t.bins.length - 1].start_sec + t.bin_sec)}</span>
      </div>
      {peak && (
        <p data-testid="summary-insights-peak">
          Most questions: {clock(peak.start_sec)} to {clock(peak.start_sec + t.bin_sec)} ({peak.questions}{" "}
          {peak.questions === 1 ? "question" : "questions"}){peak.product ? `, while ${peak.product} was on air` : ""}.
        </p>
      )}
    </div>
  );
}

/** What viewers asked, from the stored comments: topics (busiest first) and how their questions ended. */
function InsightsCard({ c }: { c: CommentInsights }) {
  const o = c.outcomes;
  const pct = (n: number) => (c.questions ? `${Math.round((n / c.questions) * 100)}%` : "–");
  const reasons = Object.entries(c.waited_for_a_person_by_reason);
  const wait = (w: { n: number; p50: number | null; p95: number | null }) =>
    w.n && w.p50 !== null ? `${w.p50} s (95%: ${w.p95} s, ${w.n} replies)` : "no replies";
  const gaps = c.not_in_product_information;
  return (
    <section className={styles.card} data-testid="summary-insights">
      <h3 className={styles.cardTitle}>What viewers asked</h3>
      {c.questions === 0 ? (
        <p className={styles.muted}>No questions were asked.</p>
      ) : (
        <>
          <p data-testid="summary-insights-outcomes">
            {c.questions} questions: {o.auto_answered} answered automatically ({pct(o.auto_answered)}), {o.answered_by_person}{" "}
            answered by the host or the team ({pct(o.answered_by_person)}), {o.unanswered} left unanswered ({pct(o.unanswered)}).
          </p>
          <dl className={styles.facts} data-testid="summary-insights-facts">
            <div>
              <dt>Viewers in the chat</dt>
              <dd>
                {c.viewers} wrote, {c.askers} asked a question
              </dd>
            </div>
            <div>
              <dt>Wait for an automatic reply (median)</dt>
              <dd>{wait(c.reply_time_sec.auto)}</dd>
            </div>
            <div>
              <dt>Wait for the host or the team (median)</dt>
              <dd>{wait(c.reply_time_sec.person)}</dd>
            </div>
            <div>
              <dt>Buying questions (price, offers, delivery, payment)</dt>
              <dd>
                {c.buying.questions} asked, {c.buying.unanswered} left unanswered
              </dd>
            </div>
            {c.stream_reports > 0 && (
              <div>
                <dt>Stream problem reports</dt>
                <dd>{c.stream_reports}</dd>
              </div>
            )}
          </dl>
          {c.timeline && <Timeline t={c.timeline} />}
          {c.notes.length > 0 && (
            <ul data-testid="summary-insights-notes">
              {c.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Topic</th>
                <th>Questions</th>
                <th>Viewers</th>
                <th>Answered automatically</th>
                <th>Answered by a person</th>
                <th>Unanswered</th>
                <th>In viewers' words</th>
              </tr>
            </thead>
            <tbody>
              {c.topics.map((t) => (
                <tr key={t.label} data-testid="summary-insights-topic">
                  <td>
                    {t.label}
                    {t.buying && <span className={styles.muted}> · buying</span>}
                  </td>
                  <td className="tabular">{t.questions}</td>
                  <td className="tabular">{t.askers}</td>
                  <td className="tabular">{t.auto_answered}</td>
                  <td className="tabular">{t.answered_by_person}</td>
                  <td className="tabular">{t.unanswered}</td>
                  <td className={styles.muted}>{t.examples.map((e) => `"${e}"`).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {gaps.questions > 0 && (
            <div data-testid="summary-insights-gaps">
              <p>
                <b>
                  No answer could be written from the product information: {gaps.questions}{" "}
                  {gaps.questions === 1 ? "question" : "questions"}.
                </b>{" "}
                Check that the product sheet states these plainly, so they can be answered automatically next time.
              </p>
              <ul>
                {gaps.examples.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </div>
          )}
          {reasons.length > 0 && (
            <p className={styles.muted} data-testid="summary-insights-reasons">
              Why questions waited for a person: {reasons.map(([r, n]) => `${APPROVAL_REASONS[r] ?? r} ${n}`).join(" · ")}
            </p>
          )}
        </>
      )}
      <p className={styles.muted} data-testid="summary-insights-source">
        {c.topic_source === "analysis"
          ? "Topics: sorted by AI after the broadcast. Counts: from the stored comments."
          : c.topic_source === "labels"
            ? "Topics: the labels stored with each question (the analysis was not available). Counts: from the stored comments."
            : "Counts: from the stored comments."}
        {c.reactions + c.hidden > 0 && ` Also in the chat: ${c.reactions} reactions, ${c.hidden} hidden.`}
      </p>
    </section>
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
          // with the comment analysis: what happened to viewers' questions; without it, the recorded counters
          (data.comment_insights
            ? [
                ["Comments", data.comment_insights.comments],
                ["Viewers who wrote", data.comment_insights.viewers],
                ["Questions", data.comment_insights.questions],
                ["Answered automatically", data.comment_insights.outcomes.auto_answered],
                ["Answered by a person", data.comment_insights.outcomes.answered_by_person],
                ["Unanswered", data.comment_insights.outcomes.unanswered],
              ]
            : [
                ["Comments", s.totals.comments],
                ["Questions", s.totals.questions],
                ["Question groups", s.totals.groups],
                ["Hidden", s.totals.hidden_comments],
                ["Instant answers", s.cache.instant_answers],
                ["Composed answers", s.cache.composed_answers],
              ]) as [string, number][]
        ).map(([label, value]) => (
          <div key={label} className={styles.total}>
            <span className={styles.totalValue}>{value}</span>
            <span className={styles.muted}>{label}</span>
          </div>
        ))}
      </section>

      {data.comment_insights && <InsightsCard c={data.comment_insights} />}

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
                <th>Host said</th>
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
                <th>Host said</th>
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
