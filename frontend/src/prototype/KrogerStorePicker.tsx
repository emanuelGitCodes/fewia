import { useEffect, useId, useRef, useState, type JSX } from "react";
import { isAbortError } from "../api";
import type { KrogerStore } from "../chatTypes";
import { findKrogerStores, type KrogerStoreOption } from "../krogerApi";

export const KROGER_UNAVAILABLE_LINE = "Kroger stores are not available right now.";
export const KROGER_NO_STORES_LINE = "No Kroger stores found near that ZIP code.";

export function KrogerStorePicker(props: {
  store: KrogerStore | null;
  onChoose: (option: KrogerStoreOption) => void;
  onClear: () => void;
}): JSX.Element {
  const { store, onChoose, onClear } = props;
  const zipId = useId();
  const [open, setOpen] = useState(false);
  // The ZIP and the store list live only in component state.
  const [zip, setZip] = useState("");
  const [options, setOptions] = useState<KrogerStoreOption[] | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  const search = (): void => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setPending(true);
    setFailed(false);
    setOptions(null);
    findKrogerStores(zip, current.signal).then(
      (found) => {
        if (controller.current === current) {
          setOptions(found);
          setZip("");
          setPending(false);
        }
      },
      (error: unknown) => {
        if (controller.current === current && !isAbortError(error)) {
          setFailed(true);
          setPending(false);
        }
      },
    );
  };
  const close = (): void => {
    controller.current?.abort();
    setOpen(false);
    setOptions(null);
    setPending(false);
    setFailed(false);
    setZip("");
  };

  let status = "";
  if (pending) {
    status = "Finding Kroger stores.";
  } else if (failed) {
    status = KROGER_UNAVAILABLE_LINE;
  } else if (options !== null && options.length === 0) {
    status = KROGER_NO_STORES_LINE;
  }

  return (
    <div className="tonight-kroger-picker">
      {store !== null ? (
        <div className="tonight-kroger-chosen">
          <p>Kroger store: {store.name}</p>
          <button
            type="button"
            className="tonight-ask-btn"
            onClick={() => {
              setOpen(true);
            }}
          >
            Change
          </button>
          <button type="button" className="tonight-ask-btn" onClick={onClear}>
            Remove
          </button>
        </div>
      ) : null}
      {store === null && !open ? (
        <button
          type="button"
          className="tonight-ask-btn"
          onClick={() => {
            setOpen(true);
          }}
        >
          Choose a Kroger store for live prices
        </button>
      ) : null}
      {open ? (
        <form
          className="tonight-kroger-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (/^\d{5}$/.test(zip) && !pending) {
              search();
            }
          }}
        >
          <label htmlFor={zipId}>ZIP code</label>
          <div className="tonight-ask-row">
            <input
              id={zipId}
              type="text"
              inputMode="numeric"
              maxLength={5}
              autoComplete="off"
              value={zip}
              onChange={(event) => {
                setZip(event.target.value);
              }}
            />
            <button
              type="submit"
              className="tonight-ask-btn"
              disabled={!/^\d{5}$/.test(zip) || pending}
            >
              Find stores
            </button>
            <button type="button" className="tonight-ask-btn" onClick={close}>
              Cancel
            </button>
          </div>
          {options !== null && options.length > 0 ? (
            <ul className="tonight-kroger-stores" aria-label="Kroger stores">
              {options.map((option, index) => (
                <li key={`${option.locationId}-${String(index)}`}>
                  <button
                    type="button"
                    className="tonight-ask-btn"
                    onClick={() => {
                      onChoose(option);
                      close();
                    }}
                  >
                    {`${option.name}, ${option.addressLine}, ${option.city}, ${option.state}`}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </form>
      ) : null}
      <p className="tonight-ask-hint" aria-live="polite">
        {status}
      </p>
    </div>
  );
}
