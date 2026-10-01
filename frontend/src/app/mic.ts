// Host microphone (DEV_SPEC §10.1): getUserMedia -> AudioWorklet (16 kHz mono PCM, 100 ms frames)
// -> WebSocket /api/sessions/{sid}/audio. One shared client per page, so the Studio host pane and the
// Demo Console show the same state. Reconnects automatically while the user wants it on.
import { useSyncExternalStore } from "react";

export type MicState = "off" | "connecting" | "listening" | "error";

export interface MicSnapshot {
  state: MicState;
  level: number; // 0..1 RMS of the last frame
  message: string | null;
  sessionId: string | null;
  lastFinal: string | null;
}

type Listener = () => void;

class MicClient {
  private snap: MicSnapshot = { state: "off", level: 0, message: null, sessionId: null, lastFinal: null };
  private listeners = new Set<Listener>();
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private wanted = false;
  private retries = 0;
  private retryTimer: number | null = null;

  subscribe = (l: Listener) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  getSnapshot = () => this.snap;

  private set(patch: Partial<MicSnapshot>) {
    this.snap = { ...this.snap, ...patch };
    this.listeners.forEach((l) => l());
  }

  async start(sessionId: string) {
    if (this.wanted && this.snap.sessionId === sessionId) return;
    await this.stop();
    this.wanted = true;
    this.retries = 0;
    this.set({ sessionId, state: "connecting", message: null });
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      this.ctx = new AudioContext();
      await this.ctx.audioWorklet.addModule("/pcm-worklet.js");
      const source = this.ctx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.ctx, "pcm-worklet");
      this.node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
        if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(e.data.pcm);
        this.set({ level: Math.min(1, e.data.level * 4) });
      };
      source.connect(this.node);
      this.connect();
    } catch (err) {
      this.wanted = false;
      this.set({ state: "error", message: err instanceof Error ? err.message : "Microphone unavailable" });
      await this.release();
    }
  }

  private connect() {
    const sid = this.snap.sessionId;
    if (!sid || !this.wanted) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/sessions/${sid}/audio`);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.set({ state: "connecting" });
    ws.onmessage = (e) => {
      if (typeof e.data !== "string") return;
      const msg = JSON.parse(e.data) as { type: string; state?: string; message?: string; text?: string };
      if (msg.type === "status" && msg.state === "listening") {
        this.retries = 0;
        this.set({ state: "listening", message: null });
      } else if (msg.type === "status" && msg.state === "error") {
        this.set({ state: "error", message: msg.message ?? "Speech recognition error" });
      } else if (msg.type === "final") {
        this.set({ lastFinal: msg.text ?? null });
      }
    };
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (!this.wanted) return;
      if (e.code === 4400 || e.code === 4404 || e.code === 4409) {
        // STT off, unknown session, or another microphone took over: do not retry
        this.wanted = false;
        this.set({ state: e.code === 4409 ? "off" : "error" });
        void this.release();
        return;
      }
      this.retries += 1;
      this.set({ state: "connecting", message: "Reconnecting…" });
      const delay = Math.min(5000, 500 * 2 ** Math.min(this.retries, 4));
      this.retryTimer = window.setTimeout(() => this.connect(), delay);
    };
  }

  private async release() {
    this.node?.disconnect();
    this.node = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.ctx) await this.ctx.close().catch(() => undefined);
    this.ctx = null;
  }

  async stop() {
    this.wanted = false;
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer);
    this.retryTimer = null;
    const ws = this.ws;
    this.ws = null;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
    ws?.close();
    await this.release();
    this.set({ state: this.snap.state === "error" ? "error" : "off", level: 0 });
  }

  toggle(sessionId: string) {
    if (this.wanted) void this.stop();
    else void this.start(sessionId);
  }
}

export const mic = new MicClient();

export function useMic(): MicSnapshot & { start: (sid: string) => void; stop: () => void; toggle: (sid: string) => void } {
  const snap = useSyncExternalStore(mic.subscribe, mic.getSnapshot, mic.getSnapshot);
  return {
    ...snap,
    start: (sid) => void mic.start(sid),
    stop: () => void mic.stop(),
    toggle: (sid) => mic.toggle(sid),
  };
}
