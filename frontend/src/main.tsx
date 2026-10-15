import "@fontsource/lora/400.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { TonightPrototype } from "./prototype/TonightPrototype";
import "./styles.css";
const prototype = window.location.pathname.replace(/\/+$/, "") === "/prototype";
createRoot(document.getElementById("root")!).render(
  <StrictMode>{prototype ? <TonightPrototype /> : <App />}</StrictMode>,
);
