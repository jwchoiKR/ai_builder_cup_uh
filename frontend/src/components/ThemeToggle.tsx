import { Moon, Sun } from "lucide-react";

import type { ThemeName } from "../app/theme";
import styles from "./ui.module.css";

export function ThemeToggle({ theme, onToggle, label }: { theme: ThemeName; onToggle: () => void; label?: string }) {
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className={styles.iconButton}
      onClick={onToggle}
      aria-label={`${label ? `${label}: ` : ""}switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
    </button>
  );
}
