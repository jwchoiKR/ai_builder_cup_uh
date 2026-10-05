import { useCallback } from "react";

import { api } from "../app/api";
import type { ScreenProps } from "../app/nav";
import { useCatalog, useHealth, useSession } from "../app/store";
import { useTheme } from "../app/theme";
import type { ViewerIdentity } from "./viewer/identity";
import { ViewerView } from "./viewer/ViewerView";

/** Viewer page (§12.5). Standalone it is a framed 390x844 phone; embedded (Studio pane, operator
 * preview) it fills its container. */
export function Viewer(props: ScreenProps) {
  const [ownTheme, , setTheme, themePref] = useTheme();
  const theme = props.theme ?? ownTheme;
  const { state, connection } = useSession(props.sessionId, "viewer");
  const catalog = useCatalog(props.sessionId);
  const health = useHealth();
  const sessionId = props.sessionId;
  const embedded = Boolean(props.embedded);

  const onSend = useCallback(
    (identity: ViewerIdentity, text: string) =>
      sessionId
        ? api.postComment(sessionId, { author_id: identity.authorId, author_name: identity.name, text })
        : Promise.resolve(null),
    [sessionId],
  );

  return (
    <ViewerView
      state={state}
      catalog={catalog}
      connection={connection}
      theme={theme}
      embedded={embedded}
      inputEnabled={Boolean(health?.viewer_input_enabled)}
      cameraEnabled={!embedded && import.meta.env.MODE !== "test"}
      themePref={themePref}
      onSetTheme={embedded || props.theme ? undefined : setTheme}
      onSend={sessionId ? onSend : undefined}
    />
  );
}
