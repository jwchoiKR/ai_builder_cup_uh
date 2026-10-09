// Studio (§12.6): Host, Operator and Viewer side by side for screen recording at 1920x1080,
// with a toggle per screen, recording mode (R) and the Demo Console drawer (D, demo tools only).
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
// Each shown screen takes width in proportion to its weight.
const SCREENS: PaneScreen[] = ["host", "operator", "viewer"];
const WEIGHT: Record<PaneScreen, number> = { host: 50, operator: 32, viewer: 18 };
const PANE_LABEL: Record<PaneScreen, string> = { host: "Host", operator: "Operator", viewer: "Viewer" };
const PANE_COMPONENT: Record<PaneScreen, ComponentType<ScreenProps>> = { host: Host, operator: Operator, viewer: Viewer };
const PANES_KEY = "ls.studio.panes";
const DEFAULT_PANES: PaneScreen[] = ["host", "operator"];

/** ?layout=host_operator|host_viewer|all (recording links), else the last choice, else Host + Operator. */
function readPanes(): PaneScreen[] {
  const fromUrl = new URLSearchParams(window.location.search).get("layout");
  if (fromUrl === "all") return SCREENS;
  if (fromUrl === "host_viewer") return ["host", "viewer"];
  if (fromUrl === "host_operator") return DEFAULT_PANES;
  try {
    const v = JSON.parse(window.localStorage.getItem(PANES_KEY) ?? "null");
    const panes = Array.isArray(v) ? SCREENS.filter((s) => v.includes(s)) : [];
    return panes.length ? panes : DEFAULT_PANES;
  } catch {
    return DEFAULT_PANES;
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
    <section className={styles.pane} style={{ flex: `${width} 1 0` }} aria-label={PANE_LABEL[screen]}>
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
  const [shown, setShown] = useState<PaneScreen[]>(readPanes);
  const demoTools = useHealth()?.demo_tools_enabled ?? false;
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [recording, setRecording] = useState(() => new URLSearchParams(window.location.search).get("recording") === "1");

  useEffect(() => {
    try {
      window.localStorage.setItem(PANES_KEY, JSON.stringify(shown));
    } catch {
      /* storage unavailable: keep the choice in memory */
    }
  }, [shown]);
  // the last shown screen cannot be turned off
  const toggle = (s: PaneScreen) =>
    setShown((cur) => (cur.includes(s) ? (cur.length > 1 ? cur.filter((x) => x !== s) : cur) : SCREENS.filter((x) => x === s || cur.includes(x))));

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
          <div className={styles.segmented} role="group" aria-label="Screens">
            {SCREENS.map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={shown.includes(s)}
                className={[styles.segment, shown.includes(s) && styles.segmentActive].filter(Boolean).join(" ")}
                onClick={() => toggle(s)}
              >
                {PANE_LABEL[s]}
              </button>
            ))}
          </div>
          <SettingsButton themePref={themePref} onTheme={setTheme} />
        </div>
      )}
      <div className={styles.panes}>
        {shown.map((s) => (
          <Pane
            key={s}
            screen={s}
            width={WEIGHT[s]}
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
