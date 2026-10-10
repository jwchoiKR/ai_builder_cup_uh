// Demo Console (§12.6; Studio, key D, demo tools only): drive a show by hand with no live host or viewers. Session
// controls, host lines (a pasted script, one line per row, and free text) injected as speech-to-text finals, viewer
// comments (one now, a pasted batch at once, or a pasted list as background chatter), the mic, and tools. Lines and
// comments take the show's normal path. Either list can be written by the model for the show's products ("Write with
// AI", with an optional instruction); it fills the box, nothing is sent until injected or posted. The pasted script
// and comments stay in this browser.
import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent } from "react";

import { api, request, userMessage } from "../app/api";
import { navigate, withSession } from "../app/nav";
import { useMic } from "../app/mic";
import { setMicLang, STT_LANGUAGES, useMicLang } from "../app/prefs";
import { useHealth, useSession } from "../app/store";
import type { Session } from "../app/types";
import { Button, Chip, Eyebrow } from "../components";
import styles from "./console.module.css";

const HEIGHT_KEY = "ls.console.height";
const SCRIPT_KEY = "ls.console.script";
const COMMENTS_KEY = "ls.console.comments";
const MIN_HEIGHT = 120;
const CHATTER_MS = 4000; // one background comment every 4 s
// D-348: at most the CSS cap (46vh), so the panes above keep a readable prompter
const maxHeight = () => Math.round(window.innerHeight * 0.46);
const clampHeight = (h: number) => Math.max(MIN_HEIGHT, Math.min(maxHeight(), Math.round(h)));

// Browser storage may throw (private mode): the console still works, nothing is remembered.
function load(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function save(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // not remembered
  }
}
export function readConsoleHeight(): number | null {
  const v = Number(load(HEIGHT_KEY));
  return v > 0 ? v : null;
}

const rows = (text: string) => text.split("\n").map((l) => l.trim()).filter(Boolean);
/** "Name: comment" names the viewer; a row without a name is from "Viewer". */
export function parseComment(row: string): { author: string; text: string } {
  const m = /^([^:]{1,30}):\s*(.+)$/.exec(row);
  return m ? { author: m[1].trim(), text: m[2].trim() } : { author: "Viewer", text: row };
}

/** Count and instruction for the model, and the button that fills a list with its lines. */
function AiWriter({ kind, sessionId, disabled, onLines, onError }: {
  kind: "host" | "comments";
  sessionId: string | null;
  disabled: boolean;
  onLines: (lines: string[]) => void;
  onError: (message: string) => void;
}) {
  const [count, setCount] = useState(10);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className={styles.inject}>
      <input className={styles.input} style={{ flex: "0 0 56px" }} type="number" min={1} max={30} value={count}
        onChange={(e) => setCount(Number(e.target.value) || 1)} aria-label="How many" data-testid={`console-ai-count-${kind}`} />
      <input className={styles.input} value={instruction} onChange={(e) => setInstruction(e.target.value)}
        placeholder={kind === "host" ? "Optional: e.g. two lines that overclaim" : "Optional: e.g. price questions"}
        aria-label="Instruction for the AI" data-testid={`console-ai-instruction-${kind}`} />
      <Button size="sm" disabled={disabled || busy || !sessionId} data-testid={`console-ai-${kind}`}
        onClick={async () => {
          setBusy(true);
          try {
            onLines((await api.generateLines(sessionId!, kind, count, instruction.trim())).lines);
          } catch (e) {
            onError(userMessage(e));
          } finally {
            setBusy(false);
          }
        }}>
        {busy ? "Writing…" : "Write with AI"}
      </Button>
    </div>
  );
}

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
  const { state } = useSession(sessionId, "operator");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [script, setScript] = useState("");
  const [comments, setComments] = useState("");
  // Lists are remembered per product set, so one product's lines never show on another's show.
  const s0 = state.session;
  const productKey = (s0?.release_ids?.length ? [...s0.release_ids] : s0?.release_id ? [s0.release_id] : [])
    .sort().join(",");
  const [loadedKey, setLoadedKey] = useState("");
  const [injected, setInjected] = useState<Set<number>>(new Set());
  const [freeText, setFreeText] = useState("");
  const [author, setAuthor] = useState("Viewer");
  const [comment, setComment] = useState("");
  const [chatter, setChatter] = useState(false);
  const mic = useMic();
  const micLang = useMicLang();
  const health = useHealth();
  const drawer = useRef<HTMLElement>(null);
  const [height, setHeight] = useState<number | null>(() => readConsoleHeight());
  const resizeTo = (h: number) => {
    const next = clampHeight(h);
    setHeight(next);
    save(HEIGHT_KEY, String(next));
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

  useEffect(() => {
    setScript(productKey ? load(`${SCRIPT_KEY}.${productKey}`) ?? "" : "");
    setComments(productKey ? load(`${COMMENTS_KEY}.${productKey}`) ?? "" : "");
    setLoadedKey(productKey);
  }, [productKey]);
  useEffect(() => { if (loadedKey) save(`${SCRIPT_KEY}.${loadedKey}`, script); }, [script, loadedKey]);
  useEffect(() => { if (loadedKey) save(`${COMMENTS_KEY}.${loadedKey}`, comments); }, [comments, loadedKey]);
  useEffect(() => {
    setInjected(new Set());
    setChatter(false);
  }, [sessionId]);

  const sid = sessionId ?? "";
  const post = (row: string) => {
    const c = parseComment(row);
    return api.scriptComment(sid, c.author, c.text);
  };
  // background chatter: the pasted comments in turn, one every CHATTER_MS, until stopped
  const next = useRef(0);
  useEffect(() => {
    const list = rows(comments);
    if (!chatter || !sessionId || !list.length) return;
    const t = window.setInterval(() => {
      const row = list[next.current % list.length];
      next.current += 1;
      post(row).catch((e) => setError(userMessage(e)));
    }, CHATTER_MS);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatter, sessionId, comments]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(null);
    }
  };
  const session = state.session;
  const status = session?.status ?? "ready";
  const mode = session?.show_mode ?? "solo";
  const [newMode, setNewMode] = useState<"solo" | "team">("solo");
  useEffect(() => setNewMode(mode), [mode]);
  const disabled = !sessionId || busy !== null;
  const lines = rows(script);
  // a new show of the same products (the hub's pick), in the chosen show mode
  const releases = session?.release_ids?.length ? { release_ids: session.release_ids }
    : session?.release_id ? { release_id: session.release_id } : null;

  return (
    <section
      ref={drawer}
      className={styles.drawer}
      aria-label="Demo console"
      style={open && height ? { height } : undefined}
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
        {chatter && <Chip tone="accent">Chatter on</Chip>}
        <Chip>{mode === "team" ? "Team show" : "Solo show"}</Chip>
        {error && <span className={styles.error}>{error}</span>}
      </button>
      {open && (
        <div className={styles.content}>
          <div className={styles.section}>
            <Eyebrow>Session</Eyebrow>
            <div className={styles.buttons}>
              <select
                className={styles.select}
                aria-label="Show mode of the new session"
                value={newMode}
                onChange={(e) => setNewMode(e.target.value as "solo" | "team")}
                data-testid="console-show-mode"
              >
                <option value="solo">Solo show</option>
                <option value="team">Team show</option>
              </select>
              <Button
                size="sm"
                disabled={busy !== null || !releases}
                title={releases ? undefined : "Start a show from the hub first"}
                onClick={() => run("new", async () => {
                  const s = await request<Session>("POST", "/sessions", { ...releases, show_mode: newMode });
                  onSessionChange?.(s.session_id);
                })}
                data-testid="console-new-show"
              >
                New show, same products
              </Button>
              <Button size="sm" variant="primary" disabled={disabled || status !== "ready"} onClick={() => run("start", () => api.start(sid))}>
                Start broadcast
              </Button>
              <Button size="sm" disabled={disabled || status !== "live"} onClick={() => run("end", () => api.end(sid))}>
                End broadcast
              </Button>
            </div>
            <span className={`${styles.muted} tabular`}>{sessionId ?? "No show: pick products on the hub"}</span>
          </div>

          <div className={styles.section}>
            <Eyebrow>Viewer comments</Eyebrow>
            <form
              className={styles.inject}
              onSubmit={(e) => {
                e.preventDefault();
                const text = comment.trim();
                if (text) void run("comment", async () => {
                  await api.scriptComment(sid, author.trim() || "Viewer", text);
                  setComment("");
                });
              }}
            >
              <input className={styles.input} style={{ flex: "0 0 100px" }} value={author} aria-label="Viewer name"
                onChange={(e) => setAuthor(e.target.value)} data-testid="console-author" />
              <input className={styles.input} value={comment} onChange={(e) => setComment(e.target.value)}
                placeholder="Type a viewer comment" aria-label="Viewer comment" data-testid="console-comment" />
              <Button size="sm" type="submit" disabled={disabled || !comment.trim()} data-testid="console-post">Post</Button>
            </form>
            <textarea className={styles.input} rows={4} value={comments} onChange={(e) => setComments(e.target.value)}
              placeholder={"Paste comments, one per line (\"Name: comment\" names the viewer)"}
              aria-label="Comments to send" data-testid="console-comments" />
            <AiWriter kind="comments" sessionId={sessionId} disabled={busy !== null} onError={setError}
              onLines={(l) => setComments(l.join("\n"))} />
            <div className={styles.buttons}>
              <Button size="sm" disabled={disabled || !rows(comments).length} data-testid="console-burst"
                onClick={() => run("burst", () => Promise.all(rows(comments).map(post)))}>
                Send all now
              </Button>
              <Button size="sm" disabled={!sessionId || chatter || !rows(comments).length} data-testid="console-chatter"
                onClick={() => setChatter(true)}>
                Start background chatter
              </Button>
              <Button size="sm" disabled={!chatter} onClick={() => setChatter(false)}>
                Stop
              </Button>
            </div>
          </div>

          <div className={styles.section}>
            <Eyebrow>Host lines</Eyebrow>
            <textarea className={styles.input} rows={3} value={script}
              onChange={(e) => { setScript(e.target.value); setInjected(new Set()); }}
              placeholder="Paste a host script, one line per row" aria-label="Host script" data-testid="console-script" />
            <AiWriter kind="host" sessionId={sessionId} disabled={busy !== null} onError={setError}
              onLines={(l) => { setScript(l.join("\n")); setInjected(new Set()); }} />
            <ul className={styles.lines}>
              {lines.map((text, i) => (
                <li key={i} className={[styles.line, injected.has(i) && styles.lineDone].filter(Boolean).join(" ")}>
                  <Chip>{i + 1}</Chip>
                  <span>{text}</span>
                  <Button
                    size="sm"
                    disabled={disabled}
                    data-testid={`console-line-${i + 1}`}
                    onClick={() =>
                      run(`line-${i}`, async () => {
                        await api.injectTranscript(sid, text);
                        setInjected((s) => new Set(s).add(i));
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
                data-testid="console-line"
              />
              <Button size="sm" type="submit" disabled={disabled || !freeText.trim()} data-testid="console-inject">
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
                title={health?.providers?.stt === "mock" ? "Speech-to-text is off in this environment" : undefined}
                onClick={() => sessionId && mic.start(sessionId)}
              >
                Start
              </Button>
              <Button size="sm" disabled={mic.state === "off"} onClick={() => mic.stop()}>
                Stop
              </Button>
              {/* D-348: Session default, English or Korean, for everyone */}
              <select value={micLang} onChange={(e) => setMicLang(e.target.value)} disabled={mic.state !== "off"}
                aria-label="Speech-recognition language" data-testid="console-mic-lang"
                title={mic.state !== "off" ? "Stop the mic to change the language" : undefined}>
                <option value="">Session default</option>
                {STT_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </select>
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
