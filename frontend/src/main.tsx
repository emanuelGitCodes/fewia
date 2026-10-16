import "@fontsource/lora/400.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
const TonightPrototype = lazy(() =>
  import("./prototype/TonightPrototype").then((module) => ({
    default: module.TonightPrototype,
  })),
);
const prototype = window.location.pathname.replace(/\/+$/, "") === "/prototype";
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {prototype ? (
      <Suspense fallback={null}>
        <TonightPrototype />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
