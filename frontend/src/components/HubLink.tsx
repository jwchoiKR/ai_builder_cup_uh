// Back to the Hub from any screen (user report 10/5: no way home). The brand at the top left is the link, with
// the session kept. During a live show the host and operator screens ask once before leaving; a Ctrl/Cmd-click
// (a new tab) never asks.
import { LayoutGrid } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useT } from "../app/i18n";
import { navigate, withSession } from "../app/nav";
import styles from "./ui.module.css";

export function HubLink({
  sessionId,
  live = false,
  className,
  children,
}: {
  sessionId: string | null | undefined;
  /** the show is live and leaving this screen matters: ask first */
  live?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const t = useT();
  const href = withSession("/", sessionId ?? null);
  const [asking, setAsking] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!asking) return;
    const down = (e: PointerEvent) => !wrap.current?.contains(e.target as Node) && setAsking(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setAsking(false);
    window.addEventListener("pointerdown", down);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerdown", down);
      window.removeEventListener("keydown", key);
    };
  }, [asking]);

  return (
    <span className={styles.hubLinkWrap} ref={wrap}>
      <a
        href={href}
        className={[styles.hubLink, className].filter(Boolean).join(" ")}
        aria-label={t("Back to hub")}
        data-testid="hub-link"
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // a new tab or window
          e.preventDefault();
          if (live) setAsking(true);
          else navigate(href);
        }}
      >
        {children ?? (
          <>
            <LayoutGrid aria-hidden className={styles.hubLinkIcon} />
            LIVE / Studio
          </>
        )}
      </a>
      {asking && (
        <span className={styles.hubConfirm} role="alertdialog" aria-label={t("Back to hub")} data-testid="hub-link-confirm">
          <span>{t("Leave this screen? The show keeps running.")}</span>
          <span className={styles.hubConfirmActions}>
            <button type="button" className={styles.settingsAction} autoFocus onClick={() => setAsking(false)}>
              {t("Stay")}
            </button>
            <button type="button" className={`${styles.settingsAction} ${styles.hubConfirmLeave}`} onClick={() => navigate(href)}>
              {t("Leave")}
            </button>
          </span>
        </span>
      )}
    </span>
  );
}
