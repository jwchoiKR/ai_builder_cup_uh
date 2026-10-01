// Shared state for the operator screen parts: session id, client state, catalog, server-clock now,
// and the focused question group (comment stream -> question desk).
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import { ApiError } from "../../app/api";
import type { ClientState } from "../../app/state";
import type { Catalog } from "../../app/types";

export interface OperatorCtx {
  sid: string;
  state: ClientState;
  catalog: Catalog | null;
  now: number; // server-clock now
  focusedGroup: string | null;
  focusGroup: (gid: string | null) => void;
}

const Ctx = createContext<OperatorCtx | null>(null);

export function OperatorProvider({ value, children }: { value: Omit<OperatorCtx, "focusedGroup" | "focusGroup">; children: ReactNode }) {
  const [focusedGroup, setFocused] = useState<string | null>(null);
  const focusGroup = useCallback((gid: string | null) => setFocused(gid), []);
  return <Ctx.Provider value={{ ...value, focusedGroup, focusGroup }}>{children}</Ctx.Provider>;
}

export function useOperator(): OperatorCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useOperator outside OperatorProvider");
  return v;
}

/** Run an API call with busy and error state. Returns true on success. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const run = useCallback(async (fn: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true);
    setError(null);
    setErrorCode(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
      setErrorCode(e instanceof ApiError ? e.code : null);
      return false;
    } finally {
      setBusy(false);
    }
  }, []);
  const clear = useCallback(() => {
    setError(null);
    setErrorCode(null);
  }, []);
  return { busy, error, errorCode, run, clear };
}
