import { useCallback, useEffect, useLayoutEffect, useRef, useState, type JSX } from "react";
import { currentSession, hasKrogerOwnerProof, isAbortError } from "../api";
import { KROGER_FIXTURE_LABEL, type KrogerMode } from "../apiTypes";
import { connectKroger, disconnectKroger, readKrogerConnection } from "../krogerApi";
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
  krogerMode?: KrogerMode;
}): JSX.Element | null {
  const { krogerMode } = props;
  const fixture = props.krogerMode === "fixture";
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
  const connecting = useRef(false);
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

  const refresh = useCallback((confirmDisconnect = false): void => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    readKrogerConnection(current.signal, krogerMode).then(
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
  }, [krogerMode]);

  useEffect(() => {
    setMessage(returned);
    if (returned !== "") {
      onReturnShown.current?.();
    }
  }, [returned]);

  useEffect(() => {
    mounted.current = true;
    refresh();
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, [refresh]);

  const disconnect = (): void => {
    if (disconnecting.current) {
      return;
    }
    disconnecting.current = true;
    setMessage("Disconnecting Kroger account.");
    setFailed(false);
    setBusy(true);
    disconnectKroger(props.krogerMode).then(
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

  if (props.krogerMode === "live" && currentSession()?.auth_mode === "local_demo" && !hasKrogerOwnerProof()) {
    return <p role="status" aria-live="polite">Open the operator pairing link to use live Kroger.</p>;
  }
  if (connected === null && returned === "" && message === "" && !fixture) {
    return null;
  }
  return (
    <div ref={account} className="tonight-kroger-connect" role="group" aria-label="Kroger account" tabIndex={-1}>
      {fixture ? <p className="tonight-ask-hint"><strong>{KROGER_FIXTURE_LABEL}</strong></p> : null}
      {connected === false ? (
        <a
          ref={connectLink}
          className="tonight-ask-btn"
          href="#"
          aria-disabled={busy}
          onClick={(event) => {
            event.preventDefault();
            if (connecting.current || disconnecting.current) return;
            if (savePlanCheckpoint(props.plan)) {
              setWarned(false);
            } else if (!warned) {
              setWarned(true);
              return;
            }
            connecting.current = true;
            const workspace = currentSession();
            setBusy(true);
            setMessage("Opening Kroger sign-in.");
            void connectKroger(props.krogerMode).then(
              (url) => {
                const active = currentSession();
                if (mounted.current && active !== null && workspace !== null && active.workspace_id === workspace.workspace_id &&
                    active.auth_mode === workspace.auth_mode) window.location.assign(url);
              },
              () => {
                if (mounted.current) {
                  connecting.current = false;
                  setBusy(false);
                  setMessage(KROGER_SIGN_IN_FAILED_LINE);
                }
              },
            );
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
        <KrogerCart
          state={props.plan}
          locationId={props.locationId ?? null}
          krogerMode={props.krogerMode}
        />
      ) : null}
      <p className="tonight-ask-hint" role="status" aria-label="Kroger account status" aria-live="polite">
        {warned ? PLAN_SAVE_WARNING : failed ? KROGER_DISCONNECT_FAILED_LINE : message}
      </p>
    </div>
  );
}
