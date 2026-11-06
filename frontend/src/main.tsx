import "@fontsource/lora/400.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { canonicalPath, selectRoot } from "./rootView";
import "./styles.css";
const path = canonicalPath(window.location.pathname);
if (path !== window.location.pathname) {
  window.history.replaceState(
    null,
    "",
    path + window.location.search + window.location.hash,
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>{selectRoot(path)}</StrictMode>,
);
