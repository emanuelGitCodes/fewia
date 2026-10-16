import "@fontsource/lora/400.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { selectRoot } from "./rootView";
import "./styles.css";
createRoot(document.getElementById("root")!).render(
  <StrictMode>{selectRoot(window.location.pathname)}</StrictMode>,
);
