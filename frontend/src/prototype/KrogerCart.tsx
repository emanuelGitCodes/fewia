import { useCallback, useEffect, useRef, useState, type JSX } from "react";
import { KROGER_FIXTURE_LABEL, type KrogerMode } from "../apiTypes";
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
  "Kroger did not confirm. Check your Kroger cart. This request will not be sent again.";

export const KROGER_CART_FIXTURE_ADDED_LINE = "Added to the fixture cart. No Kroger cart changed.";
export const KROGER_CART_FIXTURE_UNKNOWN_LINE =
  "The fixture cart did not confirm. No Kroger cart changed.";

export function KrogerCart(props: {
  state: PlanState;
  locationId: string | null;
  krogerMode?: KrogerMode;
}): JSX.Element {
  const { state, locationId } = props;
  // The preview lives only in component state; the browser stores nothing.
  const [preview, setPreview] = useState<KrogerCartPreview | null>(null);
  const [message, setMessage] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [sending, setSending] = useState(false);
  const [added, setAdded] = useState(false);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const confirmationExpiresAt = useRef(0);
  const uncertain = useRef(false);
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
    setUnconfirmed(uncertain.current);
    return () => {
      generation.current += 1;
      controller.current?.abort();
    };
  }, [key]);

  const ready = locationId !== null && state.meals.length > 0;

  const showPreview = (): void => {
    if (!ready || locationId === null || inFlight.current || previewing || uncertain.current) {
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
        const value = await previewKrogerCart(id, locationId, current.signal, props.krogerMode);
        if (generation.current === mine) {
          setPreviewing(false);
          setPreview(value);
          confirmationExpiresAt.current = Date.now() + value.expiresInSeconds * 1000;
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
      preview.confirmationToken === null ||
      added ||
      uncertain.current ||
      inFlight.current ||
      previewing
    ) {
      return;
    }
    if (Date.now() >= confirmationExpiresAt.current) {
      setPreview(null);
      setMessage("Cart confirmation expired. Preview the cart again.");
      previewButton.current?.focus();
      return;
    }
    inFlight.current = true;
    latestSend.current += 1;
    const mineSend = latestSend.current;
    const mine = generation.current;
    // The success and unknown text follow the preview that is sent.
    const sentFixture = preview.source === "fixture";
    const addedLine = sentFixture ? KROGER_CART_FIXTURE_ADDED_LINE : KROGER_CART_ADDED_LINE;
    const unknownLine = sentFixture ? KROGER_CART_FIXTURE_UNKNOWN_LINE : KROGER_CART_UNKNOWN_LINE;
    setSending(true);
    setMessage("");
    addToKrogerCart(preview.confirmationToken, preview.source).then((result) => {
      inFlight.current = false;
      if (result === "unknown") uncertain.current = true;
      if (!mounted.current) {
        return;
      }
      setSending(false);
      if (result === "unknown") {
        setUnconfirmed(true);
        if (sendButton.current === document.activeElement) cart.current?.focus();
        setPreview(null);
      }
      if (generation.current !== mine) {
        if (latestSend.current === mineSend) {
          if (result === "added") {
            setMessage(addedLine);
          } else if (result === "unknown") {
            setMessage(unknownLine);
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
        setMessage(addedLine);
      } else if (result === "not_connected") {
        setMessage(KROGER_CART_RECONNECT_LINE);
      } else if (result === "unavailable") {
        setMessage(KROGER_CART_UNAVAILABLE_LINE);
      } else if (result === "rejected") {
        setPreview(null);
        setMessage(KROGER_CART_REJECTED_LINE);
      } else {
        setUnconfirmed(true);
        setMessage(unknownLine);
      }
    });
  };

  const count = preview?.items.length ?? 0;
  const fixturePreview = preview?.source === "fixture";
  // Before a preview exists, the capability picks the wording; after, the preview does.
  const fixtureWording = preview === null ? props.krogerMode === "fixture" : fixturePreview;
  let status = message;
  if (previewing) {
    status = fixtureWording ? "Preparing fixture cart preview." : "Preparing Kroger cart preview.";
  } else if (sending) {
    status = fixtureWording ? "Sending items to fixture cart." : "Sending items to Kroger cart.";
  } else if (status === "" && preview !== null) {
    status =
      count === 0
        ? fixturePreview
          ? "No fixture items found for this plan."
          : KROGER_CART_EMPTY_LINE
        : `${fixturePreview ? "Fixture" : "Kroger"} cart preview ready: ${String(count)} ${count === 1 ? "item" : "items"}.`;
    if (preview.unmatched.length > 0) {
      status += ` ${String(preview.unmatched.length)} ${preview.unmatched.length === 1 ? "ingredient has" : "ingredients have"} no ${fixturePreview ? "fixture" : "Kroger"} match.`;
    }
  }
  return (
    <div ref={cart} className="tonight-kroger-cart" role="group" aria-label="Kroger cart" tabIndex={-1}>
      {ready ? (
        <button
          ref={setPreviewButton}
          type="button"
          className="tonight-ask-btn"
          aria-disabled={!ready || previewing || sending || unconfirmed}
          onClick={showPreview}
        >
          {fixtureWording ? "Preview fixture cart" : "Preview Kroger cart"}
        </button>
      ) : null}
      {preview !== null ? (
        <>
          {fixturePreview ? <p className="tonight-ask-hint"><strong>{KROGER_FIXTURE_LABEL}</strong></p> : null}
          {count > 0 ? (
            <ul
              className="tonight-kroger-cart-items"
              aria-label={fixturePreview ? "Fixture cart preview" : "Kroger cart preview"}
            >
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
              {`No ${fixturePreview ? "fixture" : "Kroger"} match: ${preview.unmatched.map((line) => line.name).join(", ")}.`}
            </p>
          ) : null}
          {count > 0 && preview.confirmationToken !== null && !added && !unconfirmed ? (
            <button
              ref={sendButton}
              type="button"
              className="tonight-ask-btn"
              aria-disabled={!ready || sending || previewing}
              onClick={send}
            >
              {`Send ${String(count)} ${count === 1 ? "item" : "items"} to ${fixturePreview ? "fixture" : "Kroger"} cart`}
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
