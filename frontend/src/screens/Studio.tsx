// Studio (§12.6): Host, Operator and Viewer side by side for screen recording at 1920x1080,
// with layout presets, recording mode (R) and the Demo Console drawer (D, demo tools only).
import { useEffect, useState, type ComponentType } from "react";

import type { ScreenProps } from "../app/nav";
import { useHealth } from "../app/store";
import { useTheme, type ScreenKey } from "../app/theme";
import { Eyebrow, HubLink, PanelBoundary, SettingsButton } from "../components";
import { Host } from "./Host";
import { Operator } from "./Operator";
import styles from "./studio.module.css";
import { DemoConsole } from "./DemoConsole";
import { Viewer } from "./Viewer";

type PaneScreen = Extract<ScreenKey, "host" | "operator" | "viewer">;
export type PresetKey = "host_operator" | "host_viewer" | "all";

export const PRESETS: Record<PresetKey, { label: string; panes: { screen: PaneScreen; width: number }[] }> = {
  host_operator: { label: "Host + Operator", panes: [{ screen: "host", width: 68 }, { screen: "operator", width: 32 }] },
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
        <PanelBoundary name={screen}>
          <Screen sessionId={sessionId} theme={theme} embedded onSessionChange={onSessionChange} />
        </PanelBoundary>
      </div>
    </section>
  );
}

export function Studio({ sessionId, onSessionChange }: ScreenProps) {
  const [chrome, , setTheme, themePref] = useTheme();
  const [preset, setPreset] = useState<PresetKey>(readPreset);
  const demoTools = useHealth()?.demo_tools_enabled ?? false;
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [recording, setRecording] = useState(() => new URLSearchParams(window.location.search).get("recording") === "1");

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
        <PanelBoundary name="demo console">
          <DemoConsole
            sessionId={sessionId}
            open={consoleOpen}
            onToggle={() => setConsoleOpen((o) => !o)}
            onSessionChange={onSessionChange}
          />
        </PanelBoundary>
      )}
    </div>
  );
}
