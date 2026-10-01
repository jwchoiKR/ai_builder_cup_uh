import type { ScreenProps } from "../app/nav";
import { HostScreen } from "./host/HostScreen";

/** Host screen (§12.3). */
export function Host(props: ScreenProps) {
  return <HostScreen {...props} />;
}

export default Host;
