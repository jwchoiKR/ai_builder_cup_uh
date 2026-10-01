import type { ScreenProps } from "../app/nav";
import { ScreenPlaceholder } from "./Placeholder";

/** Post-broadcast summary (§12.8, phase P4). Placeholder. */
export function Summary(props: ScreenProps) {
  return <ScreenPlaceholder screen="summary" role="operator" title="Broadcast summary" props={props} />;
}
