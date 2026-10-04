// Left column: viewer preview (§12.4.5) and run of show with switch / undo (§12.4.6).
import { Check, ChevronDown, ChevronRight, Circle } from "lucide-react";
import { useState } from "react";

import { api } from "../../app/api";
import { useT } from "../../app/i18n";
import { formatMmSs, nextProduct, onAirProduct, priceView, runOfShow, type RunOfShowItem } from "../../app/selectors";
import { Button, Chip, Eyebrow, StatusDot } from "../../components";
import { Viewer } from "../Viewer";
import { useAction, useOperator } from "./context";
import { ConfirmDialog } from "./Dialogs";
import { switchSecondsLeft, undoRemainingMs } from "./model";
import styles from "./operator.module.css";

export function ViewerPreview() {
  const t = useT();
  const { sid, state, catalog } = useOperator();
  const product = onAirProduct(state, catalog);
  const price = priceView(state, catalog, product);
  return (
    <section className={styles.block} aria-label={t("Viewer preview")}>
      <h2 className={styles.blockTitle}>{t("Viewer preview")}</h2>
      <div className={styles.phoneFrame}>
        <div className={styles.phoneScaled}>
          <Viewer sessionId={sid} embedded />
        </div>
      </div>
      <div className={styles.previewProduct}>
        <span className={styles.previewName}>{product?.name ?? t("No product on air")}</span>
        {price && <span className={["tabular", styles.previewPrice].join(" ")}>{price.current}</span>}
      </div>
    </section>
  );
}

const STATUS_LABEL: Record<RunOfShowItem["status"], string> = {
  on_air: "On air now",
  next: "Up next",
  done: "Done",
  planned: "Planned",
};

export function RunOfShow() {
  const t = useT();
  const { sid, state, catalog, now } = useOperator();
  const items = runOfShow(state, catalog, now);
  const next = nextProduct(state, catalog);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [confirm, setConfirm] = useState(false);
  const act = useAction();
  const live = state.session?.status === "live";
  const sw = state.session?.switch;
  const pendingLeft = switchSecondsLeft(state, now);
  const undoLeft = undoRemainingMs(state, now);
  const target = catalog?.products.find((p) => p.product_id === sw?.target_product_id);

  return (
    <section className={styles.block} data-testid="op-run-of-show" aria-label={t("Run of show")}>
      <div className={styles.blockHeader}>
        <h2 className={styles.blockTitle}>{t("Run of show")}</h2>
        <span className={styles.muted}>{t("{n} products", { n: items.length })}</span>
      </div>
      <ol className={styles.runList}>
        {items.map((item) => {
          const pid = item.product?.product_id ?? String(item.order);
          const expanded = open.has(pid);
          const pct = item.plannedMs ? Math.min(100, (item.elapsedMs / item.plannedMs) * 100) : 0;
          const covered = new Set([...(item.segment?.covered_point_ids ?? []), ...(state.session?.pre_covered[pid] ?? [])]);
          return (
            <li key={pid} className={[styles.runItem, item.status === "on_air" && styles.runOnAir].filter(Boolean).join(" ")}>
              <div className={styles.runHead}>
                <span className={["tabular", styles.runOrder].join(" ")}>{String(item.order).padStart(2, "0")}</span>
                <span className={styles.runName}>{item.product?.name ?? pid}</span>
                {item.overtimeMs > 0 && item.status === "on_air" && (
                  <Chip tone="fact" className="tabular">
                    {t("Overtime +{time}", { time: formatMmSs(item.overtimeMs).replace(/^0(\d:)/, "$1") })}
                  </Chip>
                )}
              </div>
              <div className={styles.runStatus}>
                {item.status === "on_air" && <StatusDot tone="ok" />}
                <span>{t(STATUS_LABEL[item.status])}</span>
                <span className={["tabular", styles.muted].join(" ")}>
                  {t("{elapsed} / {planned} planned", { elapsed: formatMmSs(item.elapsedMs), planned: formatMmSs(item.plannedMs) })}
                </span>
                {item.status === "on_air" && (
                  <Button size="sm" data-testid="op-extend" disabled={act.busy} onClick={() => act.run(() => api.extendSegment(sid))}>
                    {t("+2 min")}
                  </Button>
                )}
              </div>
              <div className={styles.progress} aria-hidden>
                <span className={item.overtimeMs > 0 ? styles.progressOver : undefined} style={{ width: `${pct}%` }} />
              </div>
              <button
                type="button"
                className={styles.pointsToggle}
                aria-expanded={expanded}
                onClick={() => setOpen((s) => {
                  const n = new Set(s);
                  if (n.has(pid)) n.delete(pid);
                  else n.add(pid);
                  return n;
                })}
              >
                {expanded ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
                {t("{covered} / {total} required points covered", { covered: item.coveredRequired, total: item.requiredIds.length })}
              </button>
              {expanded && (
                <ul className={styles.pointList}>
                  {(item.product?.prompter_points ?? []).map((p) => (
                    <li key={p.point_id} className={covered.has(p.point_id) ? styles.pointDone : undefined}>
                      {covered.has(p.point_id) ? <Check size={14} aria-hidden /> : <Circle size={10} aria-hidden />}
                      <span>{p.text}</span>
                      {item.requiredIds.includes(p.point_id) && <Eyebrow>{t("Required")}</Eyebrow>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      {sw?.status === "pending" && pendingLeft !== null && (
        <div className={styles.switchPending} role="status">
          <span className="tabular">{t("Switching in {n}s", { n: pendingLeft })}</span>
          {target && <span className={styles.muted}>→ {target.name}</span>}
          <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.cancelSwitch(sid, "operator"))}>
            {t("Cancel switch")}
          </Button>
        </div>
      )}
      {sw?.status === "counting" && (
        <p className={styles.muted}>
          {t("Switch cue {n} heard", { n: sw.cue_count })}
          {target ? ` · ${target.name}` : ""}
        </p>
      )}
      <div className={styles.actions}>
        <Button
          data-testid="op-switch"
          disabled={!live || !next || sw?.status === "pending" || act.busy}
          onClick={() => setConfirm(true)}
        >
          {t("Switch product")}
        </Button>
        {undoLeft > 0 && (
          <Button data-testid="op-undo" disabled={act.busy} onClick={() => act.run(() => api.undoSwitch(sid))}>
            {t("Undo switch")} <span className="tabular">({formatMmSs(undoLeft)})</span>
          </Button>
        )}
      </div>
      {act.error && <p className={styles.error}>{act.error}</p>}
      <p className={styles.footerNote}>{t("AI prepares and checks. You stay in control.")}</p>
      {confirm && next && (
        <ConfirmDialog
          title={t("Switch product")}
          text={t("Switch to {product} now? The host prompter moves to the next product.", { product: next.name })}
          confirmLabel={t("Switch product")}
          onConfirm={() => api.switchProduct(sid, next.product_id)}
          onClose={() => setConfirm(false)}
        />
      )}
    </section>
  );
}
