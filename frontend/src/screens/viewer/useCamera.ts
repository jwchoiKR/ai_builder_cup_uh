// Camera preview for the viewer video area (§12.5, §2.2: no streaming, preview only).
import { useEffect, useRef, useState } from "react";

export type CameraState = "off" | "starting" | "on" | "unavailable";

/** Starts getUserMedia({video:true}) when `enabled`; any failure (denied, no device, insecure
 * context) leaves the caller on its placeholder. Tracks are stopped on unmount. */
export function useCamera(enabled: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<CameraState>("off");

  useEffect(() => {
    if (!enabled) return;
    const media = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
    if (!media?.getUserMedia) {
      setState("unavailable");
      return;
    }
    let stream: MediaStream | null = null;
    let cancelled = false;
    setState("starting");
    media
      .getUserMedia({ video: true })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        if (videoRef.current) videoRef.current.srcObject = s;
        setState("on");
      })
      .catch(() => {
        if (!cancelled) setState("unavailable");
      });
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [enabled]);

  // The caller keeps the <video> element mounted while `enabled`, so srcObject is set above.
  return { videoRef, state };
}
