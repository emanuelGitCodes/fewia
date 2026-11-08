import { useEffect, useLayoutEffect, useRef, useState, type JSX } from "react";
import { isAbortError } from "../api";
import { disconnectKroger, readKrogerConnection } from "../krogerApi";
import { KrogerCart } from "./KrogerCart";
import type { PlanState } from "./planModel";
import { PLAN_SAVE_WARNING, savePlanCheckpoint, type KrogerReturn } from "./planCheckpoint";

export const KROGER_CONNECT_PATH = "/api/grocery/kroger/connect";
export const KROGER_CONNECTED_LINE = "Kroger account connected.";
export const KROGER_SIGN_IN_FAILED_LINE = "Kroger sign-in did not finish. Try again.";
export const KROGER_DISCONNECT_FAILED_LINE = "Could not disconnect Kroger. Try again.";
export const KROGER_CONNECTION_UNVERIFIED_LINE =
  "Could not verify the current Kroger connection. Reload to check.";

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
  // Called once the return line has been shown, so a remount does not show it again.
  onReturnShown?: () => void;
}): JSX.Element | null {
  // The connection state lives only in component state.
  const [connected, setConnected] = useState<boolean | null>(null);
  const [returned] = useState(() => returnMessage(props.returnStatus));
  // The live region renders first and receives its text after mount so it is announced.
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [warned, setWarned] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const disconnecting = useRef(false);
  const account = useRef<HTMLDivElement | null>(null);
  const disconnectButton = useRef<HTMLButtonElement | null>(null);
  const connectLink = useRef<HTMLAnchorElement | null>(null);
  const focusConnect = useRef(false);
  const onReturnShown = useRef(props.onReturnShown);
  onReturnShown.current = props.onReturnShown;

  useLayoutEffect(() => {
    if (focusConnect.current && connected === false && document.activeElement === document.body) {
      connectLink.current?.focus();
    }
    focusConnect.current = false;
  }, [connected]);

  const refresh = (confirmDisconnect = false): void => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    readKrogerConnection(current.signal).then(
      (value) => {
        if (controller.current === current) {
          if (confirmDisconnect) {
            disconnecting.current = false;
            setBusy(false);
            if (value === false) {
              focusConnect.current =
                disconnectButton.current !== null &&
                document.activeElement === disconnectButton.current;
              setMessage("Kroger account disconnected.");
            } else {
              setFailed(true);
              setMessage("");
              return;
            }
          }
          setConnected(value);
        }
      },
      (error: unknown) => {
        if (controller.current === current && !isAbortError(error)) {
          if (confirmDisconnect) {
            disconnecting.current = false;
            setBusy(false);
            if (account.current?.contains(document.activeElement)) {
              account.current.focus();
            }
            setConnected(null);
            setMessage(KROGER_CONNECTION_UNVERIFIED_LINE);
          } else {
            setConnected(null);
          }
        }
      },
    );
  };

  useEffect(() => {
    mounted.current = true;
    setMessage(returned);
    if (returned !== "") {
      onReturnShown.current?.();
    }
    refresh();
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, [returned]);

  const disconnect = (): void => {
    if (disconnecting.current) {
      return;
    }
    disconnecting.current = true;
    setMessage("Disconnecting Kroger account.");
    setFailed(false);
    setBusy(true);
    disconnectKroger().then(
      () => {
        if (mounted.current) {
          refresh(true);
        }
      },
      () => {
        if (mounted.current) {
          disconnecting.current = false;
          setBusy(false);
          setFailed(true);
          setMessage("");
        }
      },
    );
  };

  if (connected === null && returned === "" && message === "") {
    return null;
  }
  return (
    <div ref={account} className="tonight-kroger-connect" role="group" aria-label="Kroger account" tabIndex={-1}>
      {connected === false ? (
        <a
          ref={connectLink}
          className="tonight-ask-btn"
          href={KROGER_CONNECT_PATH}
          onClick={(event) => {
            // Every click tries the save. The first failure warns; a later failure signs in
            // with a reset plan, and a success clears the warning.
            if (savePlanCheckpoint(props.plan)) {
              setWarned(false);
            } else if (!warned) {
              setWarned(true);
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
          <button
            ref={disconnectButton}
            type="button"
            className="tonight-ask-btn"
            aria-disabled={busy}
            onClick={disconnect}
          >
            Disconnect
          </button>
        </>
      ) : null}
      {connected === true ? (
        <KrogerCart state={props.plan} locationId={props.locationId ?? null} />
      ) : null}
      <p className="tonight-ask-hint" role="status" aria-label="Kroger account status" aria-live="polite">
        {warned ? PLAN_SAVE_WARNING : failed ? KROGER_DISCONNECT_FAILED_LINE : message}
      </p>
    </div>
  );
}
