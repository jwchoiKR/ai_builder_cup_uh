// Start / End broadcast, the same control on every screen that runs a show (host, operator): a show is one session,
// so starting or ending it on one screen does it for all of them. Ending asks once more, in place.
import { useState } from "react";

import { api } from "../app/api";
import { useT } from "../app/i18n";
import { Button } from "./ui";

export function BroadcastControl({ sessionId, status, size = "md" }: {
  sessionId: string | null;
  status: "ready" | "live" | "ended" | string | undefined;
  size?: "sm" | "md";
}) {
  const t = useT();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!sessionId || !status) return null;

  const run = async (call: () => Promise<unknown>) => {
    setBusy(true);
    setFailed(false);
    try {
      await call();
      setConfirming(false);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  if (status === "ready") {
    return (
      <Button variant="primary" size={size} disabled={busy} data-testid="broadcast-start"
        title={failed ? t("That did not work. Try again.") : undefined}
        onClick={() => void run(() => api.start(sessionId))}>
        {t("Start broadcast")}
      </Button>
    );
  }
  if (status === "live") {
    return confirming ? (
      <span role="group" aria-label={t("End broadcast")} data-testid="broadcast-end-confirm"
        style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
        <Button variant="danger" size={size} disabled={busy} data-testid="broadcast-end-yes"
          title={failed ? t("That did not work. Try again.") : undefined}
          onClick={() => void run(() => api.end(sessionId))}>
          {t("End for everyone")}
        </Button>
        <Button size={size} disabled={busy} data-testid="broadcast-end-no" onClick={() => setConfirming(false)}>
          {t("Cancel")}
        </Button>
      </span>
    ) : (
      <Button variant="ghost" size={size} data-testid="broadcast-end" onClick={() => setConfirming(true)}>
        {t("End broadcast")}
      </Button>
    );
  }
  if (status === "ended") {
    return (
      <a data-testid="broadcast-summary" href={`/summary?session=${encodeURIComponent(sessionId)}`}>
        {t("Open summary")}
      </a>
    );
  }
  return null;
}
