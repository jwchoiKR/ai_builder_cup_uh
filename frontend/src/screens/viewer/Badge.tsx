// The tag of a reply in the viewer's chat ("AI answer", "Host answer", the brand); D-485: also on the answer bubble
// over a character.
import { BadgeCheck, Mic, Sparkles } from "lucide-react";

import type { MessageKind } from "../../app/types";
import styles from "./viewer.module.css";

const BADGE: Record<MessageKind, { label: string; icon: "ai" | "host" | "brand" | null }> = {
  ai_answer: { label: "AI answer", icon: "ai" },
  host_answer: { label: "Host answer", icon: "host" },
  brand_answer: { label: "Brand", icon: "brand" },  // the label is the catalog's brand (Badge)
  notice: { label: "Brand", icon: "brand" },
  correction_notice: { label: "Correction", icon: null },
};

export function Badge({ kind, brand }: { kind: MessageKind; brand: string }) {
  const b = BADGE[kind];
  const label = b.icon === "brand" ? brand : b.label;
  return (
    <span className={[styles.badge, styles[`badge_${kind}`]].filter(Boolean).join(" ")}>
      {b.icon === "ai" && <Sparkles size={12} aria-hidden />}
      {b.icon === "host" && <Mic size={12} aria-hidden />}
      {b.icon === "brand" && <BadgeCheck size={12} aria-hidden />}
      {label}
    </span>
  );
}
