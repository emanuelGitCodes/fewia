import { Suspense, lazy } from "react";
import type { ReactElement } from "react";
import App from "./App";

const TonightPrototype = lazy(() =>
  import("./prototype/TonightPrototype").then((module) => ({
    default: module.TonightPrototype,
  })),
);

export const DEFAULT_PATH = "/prototype";

export function canonicalPath(pathname: string): string {
  return pathname === "" || pathname === "/" ? DEFAULT_PATH : pathname;
}

export function selectRoot(pathname: string): ReactElement {
  if (pathname.replace(/\/+$/, "") === "/prototype") {
    return (
      <Suspense fallback={null}>
        <TonightPrototype />
      </Suspense>
    );
  }
  return <App />;
}
