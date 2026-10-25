import { t as tr } from "./i18n";
import { Component, type ErrorInfo, type ReactNode } from "react";

/** Preserve a useful recovery route if an unexpected render error occurs. */
export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Workspace render failed", error.name, info.componentStack);
  }
  render() {
    if (this.state.failed)
      return (
        <main>
          <h1>{tr("Workspace could not be displayed")}</h1>
          <p>
            {" "}
            {tr(
              "Reload to recover. If checkout was interrupted, check sales history before creating another sale.",
            )}{" "}
          </p>
          <button className="primary" onClick={() => location.reload()}>
            {" "}
            {tr("Reload workspace")}{" "}
          </button>
        </main>
      );
    return this.props.children;
  }
}
