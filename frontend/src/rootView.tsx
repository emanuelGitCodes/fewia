import { Suspense, lazy, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { flushSync } from "react-dom";
import App from "./App";
import {
  currentSession, extractPairingTicket, fetchSession, loseSession, redeemPairingTicket,
  recheckSession, SESSION_CHANGE_EVENT, SESSION_LOSS_EVENT, SESSION_RECOVERY_EVENT,
  signOut, workspaceRecovery,
} from "./api";
import type { GrocerySession } from "./apiTypes";

const TonightPrototype = lazy(() =>
  import("./prototype/TonightPrototype").then((module) => ({
    default: module.TonightPrototype,
  })),
);

export const DEFAULT_PATH = "/prototype";

export function canonicalPath(pathname: string): string {
  return pathname === "" || pathname === "/" ? DEFAULT_PATH : pathname;
}

export function selectRoot(pathname: string, ticket = extractPairingTicket()): ReactElement {
  return <SessionBoundary pathname={pathname} ticket={ticket} />;
}

function SessionBoundary({ pathname, ticket }: { pathname: string; ticket: string | null }): ReactElement {
  const [session, setSession] = useState<GrocerySession | null>(null);
  const [message, setMessage] = useState("Loading your session.");
  const [revision, setRevision] = useState(0);
  const [checking, setChecking] = useState(false);
  const bootstrap = useRef<Promise<GrocerySession> | null>(null);
  const ready = useRef(false);
  const signingOut = useRef(false);
  const checkRevision = useRef(0);
  useEffect(() => {
    let mounted = true;
    const lost = (): void => {
      ready.current = false;
      checkRevision.current += 1;
      flushSync(() => {
        setSession(null);
        setChecking(false);
        setMessage("Your session ended. Reload to sign in again.");
      });
    };
    const changed = (): void => {
      if (ready.current) {
        setSession(currentSession());
        setRevision((value) => value + 1);
      }
    };
    const revalidate = (): void => {
      if (!ready.current || signingOut.current) return;
      const check = recheckSession();
      if (check === null) return;
      const mine = ++checkRevision.current;
      flushSync(() => { setChecking(true); });
      const finished = (): void => {
        if (mounted && mine === checkRevision.current) setChecking(false);
      };
      void check.then(finished, finished);
    };
    const recover = (): void => {
      const check = workspaceRecovery();
      if (check === null) return;
      const mine = ++checkRevision.current;
      setMessage("Checking your session.");
      void check.then(
        (value) => {
          if (!mounted || mine !== checkRevision.current || currentSession() !== value) return;
          ready.current = true;
          signingOut.current = false;
          setRevision((value) => value + 1);
          setSession(value);
          setChecking(false);
        },
        () => {
          if (mounted && mine === checkRevision.current) {
            setMessage("Your session ended. Reload to sign in again.");
          }
        },
      );
    };
    window.addEventListener(SESSION_LOSS_EVENT, lost);
    window.addEventListener(SESSION_CHANGE_EVENT, changed);
    window.addEventListener(SESSION_RECOVERY_EVENT, recover);
    window.addEventListener("focus", revalidate);
    bootstrap.current ??= (async () => {
      const value = await fetchSession();
      try {
        if (ticket !== null) await redeemPairingTicket(ticket);
        if (currentSession() !== value) throw new Error("Session changed.");
        return value;
      } catch (error) {
        if (currentSession() === value) loseSession();
        throw error;
      }
    })();
    void bootstrap.current.then(
      (value) => {
        if (mounted && currentSession() === value) {
          ready.current = true;
          setSession(value);
        }
      },
      () => {
        if (mounted && !signingOut.current && workspaceRecovery() === null) {
          setMessage("Your session could not be opened. Reload to try again. If pairing failed, open a new operator link.");
        }
      },
    );
    return () => {
      mounted = false;
      window.removeEventListener(SESSION_LOSS_EVENT, lost);
      window.removeEventListener(SESSION_CHANGE_EVENT, changed);
      window.removeEventListener(SESSION_RECOVERY_EVENT, recover);
      window.removeEventListener("focus", revalidate);
    };
  }, [ticket]);

  if (session === null) return <p role="status" aria-live="polite">{message}</p>;
  return (
    <>
      {checking ? <p role="status" aria-live="polite">Checking your session.</p> : null}
      <div hidden={checking} inert={checking}>
        <AuthenticatedView key={`${session.workspace_id}:${revision}`} pathname={pathname} onSignOut={() => {
        if (signingOut.current) return;
        signingOut.current = true;
        void signOut().then(
          (url) => {
            if (currentSession() !== null || workspaceRecovery() !== null) return;
            setMessage("You are signed out.");
            if (url !== null) window.location.assign(url);
          },
          () => {
            if (currentSession() === null && workspaceRecovery() === null) {
              setMessage("Browser state cleared. Sign-out could not be confirmed. Reload to sign in again.");
            }
          },
        );
        }} />
      </div>
    </>
  );
}

function AuthenticatedView({ pathname, onSignOut }: { pathname: string; onSignOut: () => void }): ReactElement {
  if (pathname.replace(/\/+$/, "") === "/prototype") {
    return (
      <Suspense fallback={null}>
        <TonightPrototype onSignOut={onSignOut} />
      </Suspense>
    );
  }
  return <App onSignOut={onSignOut} />;
}
