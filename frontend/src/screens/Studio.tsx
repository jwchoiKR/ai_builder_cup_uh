// Studio (§12.6): Host, Operator and Viewer side by side for screen recording at 1920x1080,
// with layout presets, recording mode (R) and the Demo Console drawer (D).
import { Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState, type ComponentType } from "react";

import type { ScreenProps } from "../app/nav";
import { useHealth, useSession } from "../app/store";
import { useTheme, type ScreenKey } from "../app/theme";
import { Eyebrow, HubLink, SettingsButton } from "../components";
import { DemoConsole } from "./DemoConsole";
import { Host } from "./Host";
import { Operator } from "./Operator";
import styles from "./studio.module.css";
import { Viewer } from "./Viewer";

const VOICE_MUTE_KEY = "ls.testdrive.muted";

type PaneScreen = Extract<ScreenKey, "host" | "operator" | "viewer">;
export type PresetKey = "host_operator" | "host_viewer" | "all";

export const PRESETS: Record<PresetKey, { label: string; panes: { screen: PaneScreen; width: number }[] }> = {
  host_operator: { label: "Host + Operator", panes: [{ screen: "host", width: 60 }, { screen: "operator", width: 40 }] },
  host_viewer: { label: "Host + Viewer", panes: [{ screen: "host", width: 70 }, { screen: "viewer", width: 30 }] },
  all: {
    label: "All three",
    panes: [
      { screen: "host", width: 50 },
      { screen: "operator", width: 32 },
      { screen: "viewer", width: 18 },
    ],
  },
};

const PANE_LABEL: Record<PaneScreen, string> = { host: "Host screen", operator: "Operator", viewer: "Viewer" };
const PANE_COMPONENT: Record<PaneScreen, ComponentType<ScreenProps>> = { host: Host, operator: Operator, viewer: Viewer };
const PRESET_KEY = "ls.studio.preset";

function readPreset(): PresetKey {
  const fromUrl = new URLSearchParams(window.location.search).get("layout");
  const alias: Record<string, PresetKey> = { all: "all", host_viewer: "host_viewer", host_operator: "host_operator" };
  if (fromUrl && alias[fromUrl]) return alias[fromUrl];
  try {
    const v = window.localStorage.getItem(PRESET_KEY);
    return v && v in PRESETS ? (v as PresetKey) : "host_operator";
  } catch {
    return "host_operator";
  }
}

function isTyping(target: EventTarget | null): boolean {
  const t = target as HTMLElement | null;
  return Boolean(t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable));
}

function Pane({
  screen,
  width,
  sessionId,
  recording,
  onSessionChange,
}: {
  screen: PaneScreen;
  width: number;
  sessionId: string | null;
  recording: boolean;
  onSessionChange?: (sid: string) => void;
}) {
  const [theme] = useTheme(); // D-180: one theme; the Settings gear in the Studio header sets it
  const Screen = PANE_COMPONENT[screen];
  return (
    <section className={styles.pane} style={{ flexBasis: `${width}%`, flexGrow: 0, flexShrink: 0 }} aria-label={PANE_LABEL[screen]}>
      {!recording && (
        <div className={styles.paneLabel}>
          <Eyebrow>{PANE_LABEL[screen]}</Eyebrow>
        </div>
      )}
      <div className={styles.paneBody}>
        <Screen sessionId={sessionId} theme={theme} embedded onSessionChange={onSessionChange} />
      </div>
    </section>
  );
}

/** D-320: the test drive's host voice. Each line's audio plays when the server starts streaming it into
 * speech-to-text; a note says it is an AI voice, and a toggle mutes it (kept per browser). */
function TestDriveVoice({ sessionId }: { sessionId: string | null }) {
  const { state } = useSession(sessionId, "host");
  const line = state.voiceLine;
  const [muted, setMuted] = useState(() => {
    try {
      return window.localStorage.getItem(VOICE_MUTE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [blocked, setBlocked] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const played = useRef(0);
  useEffect(() => {
    if (!line || muted || line.seq === played.current) return;  // each line once; unmuting does not replay it
    played.current = line.seq;
    const a = new Audio(line.url);
    audio.current = a;
    a.play().then(() => setBlocked(false), () => setBlocked(true));  // autoplay may be refused until a click
    return () => a.pause();
  }, [line, muted]);
  if (!line) return null;
  const toggle = () => {
    if (blocked && !muted) {  // the click is the gesture the browser waited for
      audio.current?.play().then(() => setBlocked(false), () => undefined);
      return;
    }
    const next = !muted;
    setMuted(next);
    if (next) audio.current?.pause();
    try {
      window.localStorage.setItem(VOICE_MUTE_KEY, next ? "1" : "0");
    } catch {
      // not remembered
    }
  };
  return (
    <div className={styles.voice} data-testid="testdrive-voice">
      <span>AI voice (demo)</span>
      <button type="button" className={styles.voiceToggle} aria-pressed={muted} onClick={toggle}
        data-testid="testdrive-voice-mute">
        {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
        {muted ? "Unmute" : blocked ? "Sound blocked: click to allow" : "Mute"}
      </button>
    </div>
  );
}

export function Studio({ sessionId, onSessionChange }: ScreenProps) {
  const [chrome, , setTheme, themePref] = useTheme();
  const health = useHealth();
  const demoTools = health?.demo_tools_enabled ?? false;
  const [preset, setPreset] = useState<PresetKey>(readPreset);
  const [recording, setRecording] = useState(() => new URLSearchParams(window.location.search).get("recording") === "1");
  const [consoleOpen, setConsoleOpen] = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(PRESET_KEY, preset);
    } catch {
      /* storage unavailable: keep the preset in memory */
    }
  }, [preset]);

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "r" || e.key === "R") setRecording((r) => !r);
      if ((e.key === "d" || e.key === "D") && demoTools) setConsoleOpen((o) => !o);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [demoTools]);

  return (
    <div className={styles.root} data-theme={chrome}>
      <TestDriveVoice sessionId={sessionId} />
      {!recording && (
        <div className={styles.topbar}>
          <div className={styles.brand}>
            <Eyebrow>
              <HubLink sessionId={sessionId} />
            </Eyebrow>
            <span className="tabular">{sessionId ?? "…"}</span>
            <span className={styles.hint}>R recording mode{demoTools ? " · D demo console" : ""}</span>
          </div>
          <div className={styles.segmented} role="radiogroup" aria-label="Layout">
            {(Object.keys(PRESETS) as PresetKey[]).map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={preset === k}
                className={[styles.segment, preset === k && styles.segmentActive].filter(Boolean).join(" ")}
                onClick={() => setPreset(k)}
              >
                {PRESETS[k].label}
              </button>
            ))}
          </div>
          <SettingsButton themePref={themePref} onTheme={setTheme} />
        </div>
      )}
      <div className={styles.panes}>
        {PRESETS[preset].panes.map((p) => (
          <Pane
            key={p.screen}
            screen={p.screen}
            width={p.width}
            sessionId={sessionId}
            recording={recording}
            onSessionChange={onSessionChange}
          />
        ))}
      </div>
      {demoTools && !recording && (
        <DemoConsole
          sessionId={sessionId}
          open={consoleOpen}
          onToggle={() => setConsoleOpen((o) => !o)}
          onSessionChange={onSessionChange}
        />
      )}
    </div>
  );
}
