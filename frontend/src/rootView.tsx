import { Suspense, lazy } from "react";
import type { ReactElement } from "react";
import App from "./App";

const TonightPrototype = lazy(() =>
  import("./prototype/TonightPrototype").then((module) => ({
    default: module.TonightPrototype,
  })),
);

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
