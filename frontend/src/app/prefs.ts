// Host preferences set in the Settings gear (D-119): reading size and microphone input. One choice per
// browser in localStorage; storage errors are ignored (the screen still works with the defaults).
import { useSyncExternalStore } from "react";

export const READING_SIZES = [1, 1.25, 1.5] as const;
const SIZE_KEY = "ls.host.size";
const MIC_KEY = "ls.mic.device";

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
