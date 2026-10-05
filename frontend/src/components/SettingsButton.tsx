// Settings gear (D-109, D-119): theme and UI language; on the host screen also reading size and the
// microphone input. Replaces the light/dark toggle on the host and
// operator screens. The language applies to every screen of this browser; on-air text never changes.
import { Settings } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { LANGS, setLang, useLang, useT } from "../app/i18n";
import { mic } from "../app/mic";
import { listMicDevices, READING_SIZES, resetHostLayout, setReadingSize, useMicDevice, useReadingSize } from "../app/prefs";
import type { ThemePref } from "../app/theme";
import styles from "./ui.module.css";

const THEMES: { value: ThemePref; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

export function SettingsButton({
  themePref,
  onTheme,
  host = false,
}: {
  themePref?: ThemePref;
  onTheme?: (t: ThemePref) => void;
  /** D-119: the host screen also offers reading size and the microphone input */
  host?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const size = useReadingSize();
  const device = useMicDevice();
  const [devices, setDevices] = useState<{ deviceId: string; label: string }[]>([]);
  useEffect(() => {
    if (open && host) void listMicDevices().then(setDevices);
  }, [open, host]);
  const root = useRef<HTMLDivElement>(null);
  const lang = useLang();
  const t = useT();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={styles.settings} ref={root}>
      <button
        type="button"
        className={styles.iconButton}
        onClick={() => setOpen((o) => !o)}
        aria-label={t("Settings")}
        aria-expanded={open}
        title={t("Settings")}
        data-testid="settings-button"
      >
        <Settings size={16} aria-hidden />
      </button>
      {open && (
        <div className={styles.settingsMenu} role="dialog" aria-label={t("Settings")} data-testid="settings-menu">
          {onTheme && (
            <fieldset className={styles.settingsGroup}>
              <legend>{t("Theme")}</legend>
              {THEMES.map((o) => (
                <label key={o.value}>
                  <input type="radio" name="settings-theme" checked={themePref === o.value} onChange={() => onTheme(o.value)} />
                  {t(o.label)}
                </label>
              ))}
            </fieldset>
          )}
          {host && (
            <fieldset className={styles.settingsGroup}>
              <legend>{t("Reading size")}</legend>
              {READING_SIZES.map((v) => (
                <label key={v}>
                  <input type="radio" name="settings-size" checked={size === v} onChange={() => setReadingSize(v)} />
                  {Math.round(v * 100)}%
                </label>
              ))}
            </fieldset>
          )}
          {host && (
            <fieldset className={styles.settingsGroup}>
              <legend>{t("Microphone")}</legend>
              <select
                className={styles.settingsSelect}
                aria-label={t("Microphone")}
                value={device ?? ""}
                onChange={(e) => void mic.useDevice(e.target.value || null)}
                data-testid="settings-mic"
              >
                <option value="">{t("System default")}</option>
                {devices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </option>
                ))}
              </select>
            </fieldset>
          )}
          {host && (
            <fieldset className={styles.settingsGroup}>
              <legend>{t("Layout")}</legend>
              {/* D-181: the panel sizes back to the default */}
              <button type="button" className={styles.settingsAction} onClick={resetHostLayout} data-testid="settings-reset-layout">
                {t("Reset layout")}
              </button>
            </fieldset>
          )}
          <fieldset className={styles.settingsGroup}>
            <legend>{t("Screen language")}</legend>
            {LANGS.map((o) => (
              <label key={o.value}>
                <input type="radio" name="settings-lang" checked={lang === o.value} onChange={() => setLang(o.value)} />
                {o.label}
              </label>
            ))}
            <p className={styles.settingsNote}>{t("Labels only. What you say on air is not translated.")}</p>
          </fieldset>
        </div>
      )}
    </div>
  );
}
