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
  const [returned] = useState(readReturnMessage);
  // The live region renders first and receives its text after mount so it is announced.
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(false);

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
    mounted.current = true;
    setMessage(returned);
    refresh();
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, [returned]);

  const disconnect = (): void => {
    setMessage("");
    setFailed(false);
    setBusy(true);
    disconnectKroger().then(
      () => {
        if (mounted.current) {
          setBusy(false);
          refresh();
        }
      },
      () => {
        if (mounted.current) {
          setBusy(false);
          setFailed(true);
        }
      },
    );
  };

  if (connected === null && returned === "") {
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
          <p className="tonight-kroger-status">Kroger account connected</p>
          <button type="button" className="tonight-ask-btn" disabled={busy} onClick={disconnect}>
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
