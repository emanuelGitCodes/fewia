import { useEffect, useRef, useState, type JSX } from "react";
import { isAbortError } from "../api";
import { disconnectKroger, readKrogerConnection } from "../krogerApi";
import { KrogerCart } from "./KrogerCart";
import type { PlanState } from "./planModel";
import { PLAN_SAVE_WARNING, savePlanCheckpoint, type KrogerReturn } from "./planCheckpoint";

export const KROGER_CONNECT_PATH = "/api/grocery/kroger/connect";
export const KROGER_CONNECTED_LINE = "Kroger account connected.";
export const KROGER_SIGN_IN_FAILED_LINE = "Kroger sign-in did not finish. Try again.";
export const KROGER_DISCONNECT_FAILED_LINE = "Could not disconnect Kroger. Try again.";

function returnMessage(status: KrogerReturn | null | undefined): string {
  if (status === "connected") {
    return KROGER_CONNECTED_LINE;
  }
  return status === "error" ? KROGER_SIGN_IN_FAILED_LINE : "";
}

export function KrogerConnect(props: {
  plan: PlanState;
  locationId?: string | null;
  // The sign-in result read by the page; the page also removes it from the URL.
  returnStatus?: KrogerReturn | null;
}): JSX.Element | null {
  // The connection state lives only in component state.
  const [connected, setConnected] = useState<boolean | null>(null);
  const [returned] = useState(() => returnMessage(props.returnStatus));
  // The live region renders first and receives its text after mount so it is announced.
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
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
        <a
          className="tonight-ask-btn"
          href={KROGER_CONNECT_PATH}
          onClick={(event) => {
            // A failed save warns once; the next click signs in with a reset plan.
            if (!saveFailed && !savePlanCheckpoint(props.plan)) {
              setSaveFailed(true);
              event.preventDefault();
            }
          }}
        >
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
      {connected === true ? (
        <KrogerCart state={props.plan} locationId={props.locationId ?? null} />
      ) : null}
      <p className="tonight-ask-hint" aria-live="polite">
        {saveFailed ? PLAN_SAVE_WARNING : failed ? KROGER_DISCONNECT_FAILED_LINE : message}
      </p>
    </div>
  );
}
