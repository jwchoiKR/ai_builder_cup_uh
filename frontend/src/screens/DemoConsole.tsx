// Demo Console (§12.6): session controls, feed and bursts, host-line injection, mic, tools.
import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent } from "react";

import { api } from "../app/api";
import { navigate, withSession } from "../app/nav";
import { useMic } from "../app/mic";
import { onAirSegment } from "../app/selectors";
import { useDemoScript, useHealth, useSession } from "../app/store";
import type { FeedState } from "../app/types";
import { Button, Chip, Eyebrow } from "../components";
import styles from "./console.module.css";

export const BURST_BUTTONS: { id: string; label: string }[] = [
  { id: "B1", label: "B1 Price questions" },
  { id: "B2", label: "B2 Oily skin & makeup" },
  { id: "B3", label: "B3 Sensitive & spam" },
  { id: "B4", label: "B4 Time sale questions" },
];

// The open console's height, remembered per browser. Storage may throw (private mode): fall back.
const HEIGHT_KEY = "ls.console.height";
const MIN_HEIGHT = 120;
const maxHeight = () => Math.round(window.innerHeight * 0.85);
const clampHeight = (h: number) => Math.max(MIN_HEIGHT, Math.min(maxHeight(), Math.round(h)));

export function readConsoleHeight(): number | null {
  try {
    const v = Number(window.localStorage.getItem(HEIGHT_KEY));
    return v > 0 ? v : null;
  } catch {
    return null;
  }
}

function writeConsoleHeight(h: number): void {
  try {
    window.localStorage.setItem(HEIGHT_KEY, String(h));
  } catch {
    // not remembered; the console still resizes
  }
}

const isArmed = (feed: FeedState | null, id: string) =>
  Boolean(feed?.armed.some((k) => k === id || k.startsWith(`${id}_`)));

export function DemoConsole({
  sessionId,
  open,
  onToggle,
  onSessionChange,
}: {
  sessionId: string | null;
  open: boolean;
  onToggle: () => void;
  onSessionChange?: (sid: string) => void;
}) {
  const { state, store } = useSession(sessionId, "operator");
  const steps = useDemoScript() ?? [];
  const lines = steps.filter((s) => s.action === "host_line");
  const [feed, setFeed] = useState<FeedState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [injected, setInjected] = useState<Set<number>>(new Set());
  const [freeText, setFreeText] = useState("");
  const mic = useMic();
  const health = useHealth();
  const drawer = useRef<HTMLElement>(null);
  const [height, setHeight] = useState<number | null>(() => readConsoleHeight());
  const resizeTo = (h: number) => {
    const next = clampHeight(h);
    setHeight(next);
    writeConsoleHeight(next);
  };
  const startResize = (e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = drawer.current?.getBoundingClientRect().height ?? 300;
    const move = (ev: globalThis.PointerEvent) => setHeight(clampHeight(startH + startY - ev.clientY));
    const up = (ev: globalThis.PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      resizeTo(startH + startY - ev.clientY);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const resizeByKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowUp" ? 24 : e.key === "ArrowDown" ? -24 : 0;
    if (!step) return;
    e.preventDefault();
    resizeTo((height ?? drawer.current?.getBoundingClientRect().height ?? 300) + step);
  };

  useEffect(() => setFeed(state.feed), [state.feed]);
  useEffect(() => setInjected(new Set()), [sessionId]);

  // B5 fires server-side at the next switch: refresh the feed state when a new segment starts.
  const segId = onAirSegment(state)?.segment_id;
  const firstSeg = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!segId) return;
    if (firstSeg.current === undefined) {
      firstSeg.current = segId;
      return;
    }
    void store?.resync();
  }, [segId, store]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const sid = sessionId ?? "";
  const status = state.session?.status ?? "ready";
  const disabled = !sessionId || busy !== null;
  const b5Armed = isArmed(feed, "B5");

  return (
    <section
      ref={drawer}
      className={styles.drawer}
      aria-label="Demo console"
      style={open && height ? { height, maxHeight: "none" } : undefined}
    >
      {open && (
        <div
          className={styles.grip}
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize demo console"
          aria-valuenow={height ?? undefined}
          tabIndex={0}
          onPointerDown={startResize}
          onKeyDown={resizeByKey}
          data-testid="console-grip"
        />
      )}
      <button type="button" className={styles.handle} onClick={onToggle} aria-expanded={open}>
        {open ? <ChevronDown size={16} aria-hidden /> : <ChevronUp size={16} aria-hidden />}
        Demo console
        <Chip tone={status === "live" ? "live" : "neutral"}>{status === "live" ? "LIVE" : status === "ended" ? "Ended" : "READY"}</Chip>
        {feed?.pool_running && <Chip tone="accent">Chatter on</Chip>}
        {b5Armed && <Chip tone="fact">B5 armed</Chip>}
        {error && <span className={styles.error}>{error}</span>}
      </button>
      {open && (
        <div className={styles.content}>
          <div className={styles.section}>
            <Eyebrow>Session</Eyebrow>
            <div className={styles.buttons}>
              <Button size="sm" disabled={busy !== null} onClick={() => run("new", async () => onSessionChange?.((await api.createSession()).session_id))}>
                New demo session
              </Button>
              <Button size="sm" variant="primary" disabled={disabled || status !== "ready"} onClick={() => run("start", () => api.start(sid))}>
                Start broadcast
              </Button>
              <Button size="sm" disabled={disabled || status !== "live"} onClick={() => run("end", () => api.end(sid))}>
                End broadcast
              </Button>
              <Button size="sm" variant="danger" disabled={busy !== null} onClick={() => run("reset", async () => onSessionChange?.((await api.demoReset()).session_id))}>
                Reset demo
              </Button>
            </div>
            <span className={`${styles.muted} tabular`}>{sessionId}</span>
          </div>

          <div className={styles.section}>
            <Eyebrow>Feed</Eyebrow>
            <div className={styles.buttons}>
              <Button size="sm" disabled={disabled || feed?.pool_running} onClick={() => run("pool", async () => setFeed(await api.feedStart(sid, { pool: true, bursts: false })))}>
                Start background chatter
              </Button>
              <Button size="sm" disabled={disabled || !feed?.pool_running} onClick={() => run("stop", async () => setFeed(await api.feedStop(sid)))}>
                Stop
              </Button>
            </div>
            <div className={styles.buttons}>
              {BURST_BUTTONS.map((b) => (
                <Button key={b.id} size="sm" disabled={disabled} onClick={() => run(b.id, async () => setFeed((await api.burst(sid, b.id)).feed))}>
                  {b.label}
                </Button>
              ))}
              <Button size="sm" disabled={disabled || b5Armed} onClick={() => run("B5", async () => setFeed((await api.burst(sid, "B5")).feed))}>
                {b5Armed ? "B5 armed" : "Arm B5 Switch boundary"}
              </Button>
            </div>
          </div>

          <div className={styles.section}>
            <Eyebrow>Host lines</Eyebrow>
            <ul className={styles.lines}>
              {lines.length === 0 && <li className={styles.muted}>No host script available.</li>}
              {lines.map((l) => (
                <li key={l.index} className={[styles.line, injected.has(l.index) && styles.lineDone].filter(Boolean).join(" ")}>
                  <Chip>{l.scene}</Chip>
                  <span>{l.text}</span>
                  <Button
                    size="sm"
                    disabled={disabled}
                    onClick={() =>
                      run(`line-${l.index}`, async () => {
                        await api.injectTranscript(sid, l.text, l.scene);
                        setInjected((s) => new Set(s).add(l.index));
                      })
                    }
                  >
                    Inject
                  </Button>
                </li>
              ))}
            </ul>
            <form
              className={styles.inject}
              onSubmit={(e) => {
                e.preventDefault();
                const text = freeText.trim();
                if (!text) return;
                void run("free", async () => {
                  await api.injectTranscript(sid, text);
                  setFreeText("");
                });
              }}
            >
              <input
                className={styles.input}
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
                placeholder="Type a host line to inject"
                aria-label="Host line"
              />
              <Button size="sm" type="submit" disabled={disabled || !freeText.trim()}>
                Inject
              </Button>
            </form>
          </div>

          <div className={styles.section}>
            <Eyebrow>Mic</Eyebrow>
            <div className={styles.buttons}>
              <Button
                size="sm"
                disabled={!sessionId || !health?.providers || health.providers.stt === "mock" || mic.state === "listening"}
                title={health?.providers?.stt === "mock" ? "Speech-to-text is off (STT_PROVIDER=mock)" : undefined}
                onClick={() => sessionId && mic.start(sessionId)}
              >
                Start
              </Button>
              <Button size="sm" disabled={mic.state === "off"} onClick={() => mic.stop()}>
                Stop
              </Button>
              <span className={styles.micState} data-testid="console-mic">
                {mic.state === "listening" ? "Listening" : mic.state === "connecting" ? "Connecting…" : mic.state === "error" ? (mic.message ?? "Error") : "Off"}
                {mic.lastFinal ? ` · "${mic.lastFinal}"` : ""}
              </span>
            </div>
            <Eyebrow>Tools</Eyebrow>
            <div className={styles.buttons}>
              <Button size="sm" disabled={disabled || status !== "live"} onClick={() => run("overtime", () => api.simulateOvertime(sid))}>
                Simulate overtime
              </Button>
              <Button size="sm" disabled={!sessionId} onClick={() => navigate(withSession("/summary", sessionId))}>
                Open summary
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
