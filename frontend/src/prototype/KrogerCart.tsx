import { useEffect, useRef, useState, type JSX } from "react";
import { addToKrogerCart, previewKrogerCart, type KrogerCartPreview } from "../krogerApi";
import type { PlanState } from "./planModel";
import { planRevisionBody, savePlanRevision } from "./planRevisionApi";

export const KROGER_CART_ADDED_LINE = "Added to your Kroger cart. Review and check out on kroger.com.";
export const KROGER_CART_RECONNECT_LINE = "Connect Kroger again.";
export const KROGER_CART_UNAVAILABLE_LINE = "Kroger is unavailable. Try again.";
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
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const key = `${locationId ?? ""}:${JSON.stringify(planRevisionBody(state))}`;

  useEffect(() => {
    setPreview(null);
    setMessage("");
    setPreviewing(false);
    setSending(false);
    setAdded(false);
    setUnconfirmed(false);
    return () => {
      generation.current += 1;
      controller.current?.abort();
    };
  }, [key]);

  const ready = locationId !== null && state.meals.length > 0;

  const showPreview = (): void => {
    if (locationId === null) {
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
    savePlanRevision(planRevisionBody(state), current.signal)
      .then((id) => previewKrogerCart(id, locationId, current.signal))
      .then(
        (value) => {
          if (generation.current === mine) {
            setPreviewing(false);
            setPreview(value);
          }
        },
        () => {
          if (generation.current === mine) {
            setPreviewing(false);
            setMessage(KROGER_CART_UNAVAILABLE_LINE);
          }
        },
      );
  };

  const send = (): void => {
    if (preview === null || sending) {
      return;
    }
    const mine = generation.current;
    setSending(true);
    setMessage("");
    setUnconfirmed(false);
    addToKrogerCart(preview.items.map(({ upc, quantity }) => ({ upc, quantity }))).then((result) => {
      if (generation.current !== mine) {
        return;
      }
      setSending(false);
      if (result === "added") {
        setAdded(true);
        setMessage(KROGER_CART_ADDED_LINE);
      } else if (result === "not_connected") {
        setMessage(KROGER_CART_RECONNECT_LINE);
      } else if (result === "unavailable") {
        setMessage(KROGER_CART_UNAVAILABLE_LINE);
      } else {
        setUnconfirmed(true);
        setMessage(KROGER_CART_UNKNOWN_LINE);
      }
    });
  };

  const count = preview?.items.length ?? 0;
  return (
    <div className="tonight-kroger-cart">
      {ready ? (
        <button
          type="button"
          className="tonight-ask-btn"
          disabled={previewing || sending}
          onClick={showPreview}
        >
          Preview Kroger cart
        </button>
      ) : null}
      {ready && preview !== null ? (
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
          {count > 0 && !added && !unconfirmed ? (
            <button type="button" className="tonight-ask-btn" disabled={sending} onClick={send}>
              {`Send ${String(count)} ${count === 1 ? "item" : "items"} to Kroger cart`}
            </button>
          ) : null}
          {unconfirmed ? (
            <button type="button" className="tonight-ask-btn" disabled={sending} onClick={send}>
              Retry
            </button>
          ) : null}
        </>
      ) : null}
      <p className="tonight-ask-hint" role="status" aria-live="polite">
        {message}
      </p>
    </div>
  );
}
