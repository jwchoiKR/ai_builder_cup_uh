import type { ScreenProps } from "../app/nav";
import { ScreenPlaceholder } from "./Placeholder";

/** Pre-broadcast setup (§12.7, phase P4). Placeholder. */
export function Setup(props: ScreenProps) {
  return <ScreenPlaceholder screen="setup" role="operator" title="Setup" props={props} />;
}
