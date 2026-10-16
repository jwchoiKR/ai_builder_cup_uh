// D-477: the live viewer count ("N watching"), on every screen with the chat. Nothing while the count is unknown.
import { Users } from "lucide-react";

import { useT } from "../app/i18n";

export function Watching({ count, className }: { count: number | null; className?: string }) {
  const t = useT();
  if (count === null) return null;
  return (
    <span className={["tabular", className].filter(Boolean).join(" ")} data-testid="audience-count">
      <Users aria-hidden />
      {t("{n} watching", { n: count })}
    </span>
  );
}
