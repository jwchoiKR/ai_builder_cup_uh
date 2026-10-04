// Modal dialogs and the citation side sheet. They are positioned inside the operator root, so in a
// Studio pane they cover only the operator pane.
import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { api } from "../../app/api";
import { useT } from "../../app/i18n";
import { Button, Eyebrow } from "../../components";
import { useAction, useOperator } from "./context";
import styles from "./operator.module.css";

export function Modal({ title, children, onClose, footer }: { title: string; children: ReactNode; onClose: () => void; footer: ReactNode }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  return (
    <div className={styles.scrim} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-label={title}>
        <h2 className={styles.dialogTitle}>{title}</h2>
        <div className={styles.dialogBody}>{children}</div>
        <div className={styles.dialogFooter}>{footer}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  text,
  confirmLabel,
  danger,
  onConfirm,
  onClose,
}: {
  title: string;
  text: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
}) {
  const t = useT();
  const { busy, error, run } = useAction();
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{t("Cancel")}</Button>
          <Button
            variant={danger ? "danger" : "primary"}
            disabled={busy}
            onClick={async () => {
              if (await run(onConfirm)) onClose();
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p>{text}</p>
      {error && <p className={styles.error}>{error}</p>}
    </Modal>
  );
}

/** "Post notice": editable text prefilled from templates/notices.json (§8.13). */
export function NoticeDialog({ alertId, onClose }: { alertId: string; onClose: () => void }) {
  const t = useT();
  const { sid } = useOperator();
  const [text, setText] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { busy, error, run } = useAction();
  useEffect(() => {
    let alive = true;
    api
      .noticeTemplate(sid, alertId)
      .then((r) => alive && setText(r.text))
      .catch(() => undefined)
      .finally(() => alive && setLoaded(true));
    return () => {
      alive = false;
    };
  }, [sid, alertId]);
  return (
    <Modal
      title={t("Post notice")}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{t("Cancel")}</Button>
          <Button
            variant="primary"
            disabled={busy || !text.trim()}
            onClick={async () => {
              if (await run(() => api.postNotice(sid, alertId, text.trim()))) onClose();
            }}
          >
            {t("Post notice")}
          </Button>
        </>
      }
    >
      <p className={styles.muted}>{t('Pinned in the viewer chat for 60 s, labelled "Correction".')}</p>
      <textarea
        className={styles.textarea}
        rows={4}
        value={text}
        placeholder={loaded ? "" : t("Loading template…")}
        onChange={(e) => setText(e.target.value)}
        aria-label={t("Notice text")}
      />
      {error && <p className={styles.error}>{error}</p>}
    </Modal>
  );
}

/** Passage text behind a citation chip (§12.4.7). */
export function CitationSheet({ passageId, quote, onClose }: { passageId: string; quote?: string; onClose: () => void }) {
  const t = useT();
  const { catalog } = useOperator();
  const p = catalog?.passages?.[passageId];
  const product = catalog?.products.find((x) => x.product_id === p?.product_id);
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  return (
    <aside className={styles.sheet} role="dialog" aria-label={t("Source passage")}>
      <header className={styles.sheetHeader}>
        <div>
          <Eyebrow>{passageId.startsWith("PROMO#") ? t("Active promotion") : t("Product sheet")}</Eyebrow>
          <h2 className={styles.dialogTitle}>{p?.section ?? passageId}</h2>
          {product && <span className={styles.muted}>{product.name} · {p?.doc}</span>}
        </div>
        <button type="button" className={styles.iconBtn} onClick={onClose} aria-label={t("Close source")}>
          <X size={16} aria-hidden />
        </button>
      </header>
      <p className={styles.sheetText}>{p?.text ?? quote ?? t("Passage text is not available.")}</p>
      {quote && p && (
        <>
          <Eyebrow>{t("Quoted")}</Eyebrow>
          <blockquote className={styles.quote}>{quote}</blockquote>
        </>
      )}
    </aside>
  );
}
