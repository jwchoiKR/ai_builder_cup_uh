// Studio (§12.6): Host, Operator and Viewer side by side for screen recording at 1920x1080,
// with a toggle per screen, recording mode (R) and the Demo Console drawer (D, demo tools only).
import { Fragment, useEffect, useRef, useState, type ComponentType } from "react";

import type { ScreenProps } from "../app/nav";
import { useHealth } from "../app/store";
import { useTheme, type ScreenKey } from "../app/theme";
import { Eyebrow, HubLink, PanelBoundary, SettingsButton, Splitter } from "../components";
import { Host } from "./Host";
import { Operator } from "./Operator";
import styles from "./studio.module.css";
import { DemoConsole } from "./DemoConsole";
import { Viewer } from "./Viewer";

type PaneScreen = Extract<ScreenKey, "host" | "operator" | "viewer">;
// Each shown screen takes width in proportion to its weight; the splitters between them change the weights.
const SCREENS: PaneScreen[] = ["host", "operator", "viewer"];
const WEIGHT: Record<PaneScreen, number> = { host: 50, operator: 32, viewer: 18 };
const PANE_LABEL: Record<PaneScreen, string> = { host: "Host", operator: "Operator", viewer: "Viewer" };
const PANE_COMPONENT: Record<PaneScreen, ComponentType<ScreenProps>> = { host: Host, operator: Operator, viewer: Viewer };
const PANES_KEY = "ls.studio.panes";
const WEIGHTS_KEY = "ls.studio.weights";
// the narrowest each screen gets before its content breaks (the viewer is a 390px phone frame)
const MIN_PX: Record<PaneScreen, number> = { host: 640, operator: 400, viewer: 390 };

function readWeights(): Record<PaneScreen, number> {
  try {
    const v = JSON.parse(window.localStorage.getItem(WEIGHTS_KEY) ?? "null");
    return SCREENS.every((s) => typeof v?.[s] === "number" && v[s] > 0) ? v : WEIGHT;
  } catch {
    return WEIGHT;
  }
}
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
    <section className={styles.pane} style={{ flexGrow: width, flexShrink: 1, flexBasis: 0, minWidth: MIN_PX[screen] }} aria-label={PANE_LABEL[screen]}>
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
  const [weights, setWeights] = useState(readWeights);
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
  useEffect(() => {
    try {
      window.localStorage.setItem(WEIGHTS_KEY, JSON.stringify(weights));
    } catch {
      /* storage unavailable: keep the widths in memory */
    }
  }, [weights]);
  // the splitter after shown[i] moves the edge between shown[i] and shown[i + 1]; the other panes keep their width
  const panes = useRef<HTMLDivElement>(null);
  // read on every render (each drag step renders); 0 before the first layout, then no limit
  const minShare = (s: PaneScreen) => MIN_PX[s] / (panes.current?.clientWidth || Infinity);
  const total = shown.reduce((n, s) => n + weights[s], 0);
  const edge = (i: number) => shown.slice(0, i + 1).reduce((n, s) => n + weights[s], 0) / total;
  const moveEdge = (i: number, at: number) => {
    const [a, b] = [shown[i], shown[i + 1]];
    const pair = weights[a] + weights[b];
    const wa = at * total - (edge(i) * total - weights[a]);
    setWeights((w) => ({ ...w, [a]: wa, [b]: pair - wa }));
  };
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
      <div className={styles.panes} ref={panes}>
        {shown.map((s, i) => (
          <Fragment key={s}>
            {i > 0 && !recording && (
              <Splitter
                orientation="vertical"
                value={edge(i - 1)}
                min={edge(i - 1) - weights[shown[i - 1]] / total + minShare(shown[i - 1])}
                max={edge(i) - minShare(s)}
                onChange={(v) => moveEdge(i - 1, v)}
                onReset={() => setWeights(WEIGHT)}
                label={`Resize ${PANE_LABEL[shown[i - 1]]} and ${PANE_LABEL[s]}`}
                testId={`studio-split-${i - 1}`}
              />
            )}
            <Pane
              screen={s}
              width={weights[s]}
              sessionId={sessionId}
              recording={recording}
              onSessionChange={onSessionChange}
            />
          </Fragment>
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
