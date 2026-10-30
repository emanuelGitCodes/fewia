import { useEffect, useRef, useState, type JSX } from "react";
import { isAbortError } from "../api";
import { disconnectKroger, readKrogerConnection } from "../krogerApi";

export const KROGER_CONNECT_PATH = "/api/grocery/kroger/connect";
export const KROGER_CONNECTED_LINE = "Kroger account connected.";
export const KROGER_SIGN_IN_FAILED_LINE = "Kroger sign-in did not finish. Try again.";
export const KROGER_DISCONNECT_FAILED_LINE = "Could not disconnect Kroger. Try again.";

function readReturnMessage(): string {
  const value = new URLSearchParams(window.location.search).get("kroger");
  if (value === "connected") {
    return KROGER_CONNECTED_LINE;
  }
  return value === "error" ? KROGER_SIGN_IN_FAILED_LINE : "";
}

export function KrogerConnect(): JSX.Element | null {
  // The connection state lives only in component state; the browser stores nothing.
  const [connected, setConnected] = useState<boolean | null>(null);
  const [message] = useState(readReturnMessage);
  const [failed, setFailed] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const refresh = (): void => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    readKrogerConnection(current.signal).then(
      (value) => {
        if (controller.current === current) {
          setConnected(value);
        }
      },
      (error: unknown) => {
        if (controller.current === current && !isAbortError(error)) {
          setConnected(null);
        }
      },
    );
  };

  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.has("kroger")) {
      url.searchParams.delete("kroger");
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
    }
    refresh();
    return () => {
      controller.current?.abort();
    };
  }, []);

  const disconnect = (): void => {
    setFailed(false);
    disconnectKroger().then(refresh, () => {
      setFailed(true);
    });
  };

  if (connected === null && message === "") {
    return null;
  }
  return (
    <div className="tonight-kroger-connect">
      {connected === false ? (
        <a className="tonight-ask-btn" href={KROGER_CONNECT_PATH}>
          Connect Kroger
        </a>
      ) : null}
      {connected === true ? (
        <>
          <p>Kroger account connected</p>
          <button type="button" className="tonight-ask-btn" onClick={disconnect}>
            Disconnect
          </button>
        </>
      ) : null}
      <p className="tonight-ask-hint" aria-live="polite">
        {failed ? KROGER_DISCONNECT_FAILED_LINE : message}
      </p>
    </div>
  );
}
