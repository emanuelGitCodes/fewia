import { useCallback, useEffect, useRef, useState, type JSX } from "react";
import { addToKrogerCart, previewKrogerCart, type KrogerCartPreview } from "../krogerApi";
import type { PlanState } from "./planModel";
import { planRevisionBody, savePlanRevision } from "./planRevisionApi";

export const KROGER_CART_ADDED_LINE = "Added to your Kroger cart. Review and check out on kroger.com.";
export const KROGER_CART_RECONNECT_LINE =
  "Your Kroger sign-in expired. Disconnect, then connect Kroger again.";
export const KROGER_CART_REJECTED_LINE =
  "Kroger could not take these items. Preview the cart again.";
export const KROGER_CART_UNAVAILABLE_LINE = "Kroger is unavailable. Try again.";
export const KROGER_CART_EMPTY_LINE = "No Kroger items found for this plan.";
export const KROGER_CART_SAVE_FAILED_LINE = "Could not save the plan. Try again.";
export const KROGER_CART_UNKNOWN_LINE =
  "Kroger did not confirm. Check your Kroger cart before you retry.";

export function KrogerCart(props: { state: PlanState; locationId: string | null }): JSX.Element {
  const { state, locationId } = props;
  // The preview lives only in component state; the browser stores nothing.
  const [preview, setPreview] = useState<KrogerCartPreview | null>(null);
  const [message, setMessage] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [sending, setSending] = useState(false);
  const [added, setAdded] = useState(false);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const cart = useRef<HTMLDivElement | null>(null);
  const previewButton = useRef<HTMLButtonElement | null>(null);
  const setPreviewButton = useCallback((node: HTMLButtonElement | null): void => {
    if (
      node === null &&
      previewButton.current !== null &&
      document.activeElement === previewButton.current
    ) {
      cart.current?.focus();
    }
    previewButton.current = node;
  }, []);
  const sendButton = useRef<HTMLButtonElement | null>(null);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const latestSend = useRef(0);
  const key = `${locationId ?? ""}:${JSON.stringify(planRevisionBody(state))}`;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (sendButton.current !== null && document.activeElement === sendButton.current) {
      (previewButton.current ?? cart.current)?.focus();
    }
    setPreview(null);
    setMessage("");
    setPreviewing(false);
    if (!inFlight.current) {
      setSending(false);
    }
    setAdded(false);
    setUnconfirmed(false);
    return () => {
      generation.current += 1;
      controller.current?.abort();
    };
  }, [key]);

  const ready = locationId !== null && state.meals.length > 0;

  const showPreview = (): void => {
    if (!ready || locationId === null || inFlight.current || previewing) {
      return;
    }
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    generation.current += 1;
    const mine = generation.current;
    setPreview(null);
    setMessage("");
    setAdded(false);
    setUnconfirmed(false);
    setPreviewing(true);
    const run = async (): Promise<void> => {
      let id: string;
      try {
        id = await savePlanRevision(planRevisionBody(state), current.signal);
      } catch {
        if (generation.current === mine) {
          setPreviewing(false);
          setMessage(KROGER_CART_SAVE_FAILED_LINE);
        }
        return;
      }
      try {
        const value = await previewKrogerCart(id, locationId, current.signal);
        if (generation.current === mine) {
          setPreviewing(false);
          setPreview(value);
        }
      } catch {
        if (generation.current === mine) {
          setPreviewing(false);
          setMessage(KROGER_CART_UNAVAILABLE_LINE);
        }
      }
    };
    void run();
  };

  const send = (): void => {
    if (
      !ready ||
      preview === null ||
      preview.items.length === 0 ||
      added ||
      inFlight.current ||
      previewing
    ) {
      return;
    }
    inFlight.current = true;
    latestSend.current += 1;
    const mineSend = latestSend.current;
    const mine = generation.current;
    setSending(true);
    setMessage("");
    addToKrogerCart(preview.items.map(({ upc, quantity }) => ({ upc, quantity }))).then((result) => {
      inFlight.current = false;
      if (!mounted.current) {
        return;
      }
      setSending(false);
      if (generation.current !== mine) {
        if (latestSend.current === mineSend) {
          if (result === "added") {
            setMessage(KROGER_CART_ADDED_LINE);
          } else if (result === "unknown") {
            setMessage(KROGER_CART_UNKNOWN_LINE);
          }
        }
        return;
      }
      setUnconfirmed(false);
      if (
        (result === "added" || result === "rejected") &&
        sendButton.current !== null &&
        document.activeElement === sendButton.current
      ) {
        previewButton.current?.focus();
      }
      if (result === "added") {
        setAdded(true);
        setMessage(KROGER_CART_ADDED_LINE);
      } else if (result === "not_connected") {
        setMessage(KROGER_CART_RECONNECT_LINE);
      } else if (result === "unavailable") {
        setMessage(KROGER_CART_UNAVAILABLE_LINE);
      } else if (result === "rejected") {
        setPreview(null);
        setMessage(KROGER_CART_REJECTED_LINE);
      } else {
        setUnconfirmed(true);
        setMessage(KROGER_CART_UNKNOWN_LINE);
      }
    });
  };

  const count = preview?.items.length ?? 0;
  let status = message;
  if (previewing) {
    status = "Preparing Kroger cart preview.";
  } else if (sending) {
    status = "Sending items to Kroger cart.";
  } else if (status === "" && preview !== null) {
    status =
      count === 0
        ? KROGER_CART_EMPTY_LINE
        : `Kroger cart preview ready: ${String(count)} ${count === 1 ? "item" : "items"}.`;
    if (preview.unmatched.length > 0) {
      status += ` ${String(preview.unmatched.length)} ${preview.unmatched.length === 1 ? "ingredient has" : "ingredients have"} no Kroger match.`;
    }
  }
  return (
    <div ref={cart} className="tonight-kroger-cart" role="group" aria-label="Kroger cart" tabIndex={-1}>
      {ready ? (
        <button
          ref={setPreviewButton}
          type="button"
          className="tonight-ask-btn"
          aria-disabled={!ready || previewing || sending}
          onClick={showPreview}
        >
          Preview Kroger cart
        </button>
      ) : null}
      {preview !== null ? (
        <>
          {count > 0 ? (
            <ul className="tonight-kroger-cart-items" aria-label="Kroger cart preview">
              {preview.items.map((item) => (
                <li key={item.upc}>
                  <span className="tonight-kroger-cart-name">{item.name}</span>
                  <span>{item.description}</span>
                  {item.size !== null ? <span>{item.size}</span> : null}
                  <span>Quantity {item.quantity}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {preview.unmatched.length > 0 ? (
            <p className="tonight-ask-hint">
              {`No Kroger match: ${preview.unmatched.map((line) => line.name).join(", ")}.`}
            </p>
          ) : null}
          {count > 0 && !added ? (
            <button
              ref={sendButton}
              type="button"
              className="tonight-ask-btn"
              aria-disabled={!ready || sending || previewing}
              onClick={send}
            >
              {unconfirmed
                ? "Retry"
                : `Send ${String(count)} ${count === 1 ? "item" : "items"} to Kroger cart`}
            </button>
          ) : null}
        </>
      ) : null}
      <p className="tonight-ask-hint" role="status" aria-live="polite">
        {status}
      </p>
    </div>
  );
}
