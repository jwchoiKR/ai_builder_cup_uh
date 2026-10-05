// Pre-broadcast setup (DEV_SPEC §12.7): documents, Brief Agent, glossary confirmation.
import type { ScreenProps } from "../app/nav";
import { useCatalog } from "../app/store";
import { useTheme } from "../app/theme";
import { setupApi } from "./setup/setupApi";
import { SetupView } from "./setup/SetupView";

export function Setup(props: ScreenProps) {
  const [ownTheme, , setTheme, themePref] = useTheme();
  const theme = props.theme ?? ownTheme;
  const catalog = useCatalog(props.sessionId);
  return (
    <SetupView
      products={catalog?.products ?? []}
      brand={catalog?.brand ?? ""}
      client={setupApi}
      theme={theme}
      themePref={themePref}
      onSetTheme={props.embedded ? undefined : setTheme}
      sessionId={props.sessionId}
    />
  );
}

export default Setup;
