// D-350: a render error stays in its panel. Without a boundary React unmounts the whole app (a white screen in a demo);
// with one, the other panels keep running and this one shows a small card with a reload.
import { Component, Fragment, type ErrorInfo, type ReactNode } from "react";

import { useT } from "../app/i18n";
import { lastEventType } from "../app/sse";
import { Button } from "./ui";
import styles from "./ui.module.css";

interface Props {
  name: string;
  children: ReactNode;
}

export class PanelBoundary extends Component<Props, { error: Error | null; epoch: number }> {
  state = { error: null as Error | null, epoch: 0 };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // no client-log endpoint exists: the browser console (and the demo operator) is where it is read
    console.error("[panel-error]", this.props.name, error.message, {
      stack: error.stack, componentStack: info.componentStack, lastEventType: lastEventType(),
    });
  }

  render() {
    if (this.state.error) {
      return <PanelError onReload={() => this.setState((s) => ({ error: null, epoch: s.epoch + 1 }))} />;
    }
    // a new epoch remounts the panel, so its state starts fresh from the server
    return <Fragment key={this.state.epoch}>{this.props.children}</Fragment>;
  }
}

function PanelError({ onReload }: { onReload: () => void }) {
  const t = useT();
  return (
    <div className={styles.panelError} role="alert" data-testid="panel-error">
      <span>{t("This panel hit an error")}</span>
      <Button size="sm" onClick={onReload}>
        {t("Reload panel")}
      </Button>
    </div>
  );
}
