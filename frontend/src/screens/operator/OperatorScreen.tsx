// Operator control room (DEV_SPEC §12.4). Light by default. Three columns at >= 1440 px, the right rail
// under the middle column at 1280-1439 px, one column below (Studio panes).
import { useT } from "../../app/i18n";
import type { ScreenProps } from "../../app/nav";
import { useCatalog, useServerNow, useSession } from "../../app/store";
import { useTheme } from "../../app/theme";
import { AlertStack } from "./AlertStack";
import { CommentStream } from "./CommentStream";
import { OperatorProvider } from "./context";
import { OperatorHeader } from "./Header";
import { RunOfShow, ViewerPreview } from "./LeftColumn";
import styles from "./operator.module.css";
import { QuestionDesk } from "./QuestionDesk";
import { RightRail } from "./RightRail";

export function OperatorScreen(props: ScreenProps) {
  // No T key on this screen, so the toggle (2nd element) is not used; the gear sets the theme.
  const [ownTheme, , setTheme, themePref] = useTheme();
  const t = useT();
  const theme = props.theme ?? ownTheme;
  const { state, connection, error } = useSession(props.sessionId, "operator");
  const catalog = useCatalog(props.sessionId);
  const now = useServerNow(state, 1000);

  if (!props.sessionId) {
    return (
      <div className={styles.root} data-theme={theme}>
        <p className={styles.empty}>{t("No session selected.")}</p>
      </div>
    );
  }

  return (
    <OperatorProvider value={{ sid: props.sessionId, state, catalog, now }}>
      <div className={styles.root} data-theme={theme}>
        <OperatorHeader connection={connection} themePref={themePref} onSetTheme={setTheme} showSettings={!props.embedded} />
        {error && <p className={styles.error}>{error}</p>}
        <AlertStack />
        <div className={styles.columns}>
          <div className={[styles.col, styles.colLeft].join(" ")}>
            <ViewerPreview />
            <RunOfShow />
          </div>
          <div className={[styles.col, styles.colMain].join(" ")}>
            <QuestionDesk />
            <CommentStream />
          </div>
          <div className={[styles.col, styles.colRail].join(" ")}>
            <RightRail />
          </div>
        </div>
      </div>
    </OperatorProvider>
  );
}
