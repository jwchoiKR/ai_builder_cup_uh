import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import type { ConnectionStatus } from "../app/sse";
import { useT } from "../app/i18n";
import styles from "./ui.module.css";

const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");

export type ButtonVariant = "secondary" | "primary" | "danger" | "ghost";

export function Button({
  variant = "secondary",
  size = "md",
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md" }) {
  return (
    <button
      type={type}
      className={cx(styles.button, variant !== "secondary" && styles[variant], size === "sm" && styles.sm, className)}
      {...rest}
    />
  );
}

export type ChipTone = "neutral" | "accent" | "fact" | "risk" | "ok" | "live";

export function Chip({
  tone = "neutral",
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: ChipTone }) {
  return (
    <span className={cx(styles.chip, tone !== "neutral" && styles[`chip_${tone}`], className)} {...rest}>
      {children}
    </span>
  );
}

export function Card({ padded = true, className, ...rest }: HTMLAttributes<HTMLDivElement> & { padded?: boolean }) {
  return <div className={cx(styles.card, padded && styles.cardPadded, className)} {...rest} />;
}

export function Eyebrow({ className, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cx("eyebrow", className)} {...rest} />;
}

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx(styles.card, styles.panel, className)}>
      <header className={styles.panelHeader}>
        <div>{title}</div>
        {actions && <div>{actions}</div>}
      </header>
      <div className={cx(styles.panelBody, bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatusDot({
  tone = "off",
  pulse = false,
  label,
}: {
  tone?: "live" | "ok" | "off" | "error";
  pulse?: boolean;
  label?: string;
}) {
  return (
    <span
      className={cx(styles.dot, styles[`dot_${tone}`], pulse && styles.pulse)}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}

/** "• Connected" / "Reconnecting…" (§12.9). */
export function ConnectionLabel({ status }: { status: ConnectionStatus }) {
  const t = useT();
  const ok = status === "connected";
  return (
    <span className={styles.connection} aria-live="polite">
      <StatusDot tone={ok ? "ok" : "off"} pulse={!ok} />
      {ok ? t("Connected") : t("Reconnecting…")}
    </span>
  );
}
