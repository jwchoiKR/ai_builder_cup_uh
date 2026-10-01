// Pre-broadcast setup (DEV_SPEC §12.7): documents, Brief Agent, glossary confirmation.
import type { ScreenProps } from "../app/nav";
import { useCatalog } from "../app/store";
import { useTheme } from "../app/theme";
import { setupApi } from "./setup/setupApi";
import { SetupView } from "./setup/SetupView";

export function Setup(props: ScreenProps) {
  const [ownTheme, toggle] = useTheme("setup");
  const theme = props.theme ?? ownTheme;
  const catalog = useCatalog();
  return (
    <SetupView
      products={catalog?.products ?? []}
      brand={catalog?.brand ?? "DAON LAB"}
      client={setupApi}
      theme={theme}
      onToggleTheme={props.embedded ? undefined : toggle}
    />
  );
}

export default Setup;
