import type { ScreenProps } from "../app/nav";
import { OperatorScreen } from "./operator/OperatorScreen";

/** Operator control room (§12.4). */
export function Operator(props: ScreenProps) {
  return <OperatorScreen {...props} />;
}
