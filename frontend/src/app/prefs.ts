// Host preferences set in the Settings gear (D-119): reading size and microphone input; D-181: the panel sizes.
// One choice per browser in localStorage; storage errors are ignored (the screen still works with the defaults).
import { useSyncExternalStore } from "react";

export const READING_SIZES = [1, 1.25, 1.5] as const;
const SIZE_KEY = "ls.host.size";
const MIC_KEY = "ls.mic.device";
const LAYOUT_KEY = "ls.layout.host";

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // not remembered
  }
}

let size: number | null = null;
let micDevice: string | null | undefined;

export function getReadingSize(): number {
  if (size === null) {
    const v = Number(read(SIZE_KEY));
    size = (READING_SIZES as readonly number[]).includes(v) ? v : 1;
  }
  return size;
}

export function setReadingSize(v: number): void {
  size = v;
  write(SIZE_KEY, String(v));
  notify();
}

export function getMicDevice(): string | null {
  if (micDevice === undefined) micDevice = read(MIC_KEY);
  return micDevice;
}

/** null = the system default microphone. */
export function setMicDevice(id: string | null): void {
  micDevice = id;
  write(MIC_KEY, id);
  notify();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

// ---- D-181: host panel sizes -----------------------------------------------------------------------

/** Fractions: `cols` is the left column's share of the width (prompter and questions | chat), `rows` the
 *  prompter's share of the left column's height (prompter | questions). */
export interface HostLayout {
  cols: number;
  rows: number;
}
export const HOST_LAYOUT_DEFAULT: HostLayout = { cols: 0.58, rows: 0.5 };
export const SPLIT_MIN = 0.25; // every panel keeps at least a quarter of its axis
export const SPLIT_MAX = 1 - SPLIT_MIN;
export const SPLIT_STEP = 0.05;

export const clampSplit = (v: number) => Math.round(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, v)) * 1000) / 1000;

/** The split for a pointer at `pos` over a container starting at `start`, `size` long, with a `gap` between
 *  its two panels (the splitter sits in the middle of the gap). */
export function splitAt(pos: number, start: number, size: number, gap: number): number {
  return clampSplit((pos - start - gap / 2) / Math.max(1, size - gap));
}

/** Arrow keys move the split by SPLIT_STEP, Home and End go to the limits; null for any other key. */
export function stepSplit(v: number, key: string): number | null {
  if (key === "ArrowLeft" || key === "ArrowUp") return clampSplit(v - SPLIT_STEP);
  if (key === "ArrowRight" || key === "ArrowDown") return clampSplit(v + SPLIT_STEP);
  if (key === "Home") return SPLIT_MIN;
  if (key === "End") return SPLIT_MAX;
  return null;
}

let layout: HostLayout | null = null;

export function getHostLayout(): HostLayout {
  if (layout === null) {
    try {
      const v = JSON.parse(read(LAYOUT_KEY) ?? "null") as Partial<HostLayout> | null;
      layout = v && Number.isFinite(v.cols) && Number.isFinite(v.rows)
        ? { cols: clampSplit(v.cols!), rows: clampSplit(v.rows!) }
        : HOST_LAYOUT_DEFAULT;
    } catch {
      layout = HOST_LAYOUT_DEFAULT;
    }
  }
  return layout;
}

export function setHostLayout(next: Partial<HostLayout>): void {
  const cur = getHostLayout();
  layout = { cols: clampSplit(next.cols ?? cur.cols), rows: clampSplit(next.rows ?? cur.rows) };
  write(LAYOUT_KEY, JSON.stringify(layout));
  notify();
}

export function resetHostLayout(): void {
  layout = HOST_LAYOUT_DEFAULT;
  write(LAYOUT_KEY, null);
  notify();
}

export function useHostLayout(): HostLayout {
  return useSyncExternalStore(subscribe, getHostLayout, () => HOST_LAYOUT_DEFAULT);
}

export function useReadingSize(): number {
  return useSyncExternalStore(subscribe, getReadingSize, () => 1);
}

export function useMicDevice(): string | null {
  return useSyncExternalStore(subscribe, getMicDevice, () => null);
}

/** The audio inputs. Labels are empty until the browser has granted microphone access once. */
export async function listMicDevices(): Promise<{ deviceId: string; label: string }[]> {
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    return all
      .filter((d) => d.kind === "audioinput" && d.deviceId && d.deviceId !== "default")
      .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Microphone ${i + 1}` }));
  } catch {
    return [];
  }
}
