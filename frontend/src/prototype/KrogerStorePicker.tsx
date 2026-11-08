import { useEffect, useId, useLayoutEffect, useRef, useState, type JSX } from "react";
import { isAbortError } from "../api";
import { KROGER_FIXTURE_LABEL, type KrogerMode, type KrogerSource } from "../apiTypes";
import type { KrogerStore } from "../chatTypes";
import { findKrogerStores, type KrogerStoreOption } from "../krogerApi";

export const KROGER_UNAVAILABLE_LINE = "Kroger stores are not available right now.";
export const KROGER_NO_STORES_LINE = "No Kroger stores found near that ZIP code.";

export function KrogerStorePicker(props: {
  store: KrogerStore | null;
  onChoose: (option: KrogerStoreOption) => void;
  onClear: () => void;
  krogerMode?: KrogerMode;
}): JSX.Element {
  const { store, onChoose, onClear } = props;
  // The label follows the store list when there is one, and the capability otherwise.
  const [listSource, setListSource] = useState<KrogerSource | null>(null);
  // The source of the chosen store stays until the store is removed.
  const [chosenSource, setChosenSource] = useState<KrogerSource | null>(null);
  const shownSource = listSource ?? (store === null ? null : chosenSource);
  const fixture = shownSource === null ? props.krogerMode === "fixture" : shownSource === "fixture";
  const zipId = useId();
  const [open, setOpen] = useState(false);
  // The ZIP and the store list live only in component state.
  const [zip, setZip] = useState("");
  const [options, setOptions] = useState<KrogerStoreOption[] | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const focusTarget = useRef<"input" | "opener" | null>(null);

  useLayoutEffect(() => {
    if (focusTarget.current === "input") {
      input.current?.focus();
    } else if (focusTarget.current === "opener") {
      opener.current?.focus();
    }
    focusTarget.current = null;
  });

  const start = (): void => {
    if (open) {
      input.current?.focus();
    } else {
      focusTarget.current = "input";
      setOpen(true);
    }
  };

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
    setListSource(null);
    findKrogerStores(zip, current.signal).then(
      (found) => {
        if (controller.current === current) {
          setOptions(found.stores);
          setListSource(found.source);
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
    controller.current = null;
    focusTarget.current = "opener";
    setOpen(false);
    setOptions(null);
    setListSource(null);
    setPending(false);
    setFailed(false);
    setZip("");
  };

  let status = "";
  if (pending) {
    status = fixture ? "Finding fixture stores." : "Finding Kroger stores.";
  } else if (failed) {
    status = KROGER_UNAVAILABLE_LINE;
  } else if (options !== null && options.length === 0) {
    status = KROGER_NO_STORES_LINE;
  } else if (options !== null) {
    status = `Found ${String(options.length)} ${fixture ? "fixture" : "Kroger"} ${options.length === 1 ? "store" : "stores"}.`;
  }

  return (
    <div className="tonight-kroger-picker">
      {fixture ? <p className="tonight-ask-hint"><strong>{KROGER_FIXTURE_LABEL}</strong></p> : null}
      {store !== null ? (
        <div className="tonight-kroger-chosen">
          <p id={`${zipId}-store`}>Kroger store: {store.name}</p>
          <button
            ref={opener}
            type="button"
            className="tonight-ask-btn"
            aria-describedby={`${zipId}-store`}
            onClick={start}
          >
            Change
          </button>
          <button
            type="button"
            className="tonight-ask-btn"
            aria-describedby={`${zipId}-store`}
            onClick={() => {
              if (open) {
                input.current?.focus();
              } else {
                focusTarget.current = "opener";
              }
              setChosenSource(null);
              onClear();
            }}
          >
            Remove
          </button>
        </div>
      ) : null}
      {store === null && !open ? (
        <button
          ref={opener}
          type="button"
          className="tonight-ask-btn"
          onClick={start}
        >
          {fixture ? "Choose a fixture store for fixture prices" : "Choose a Kroger store for live prices"}
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
          <p id={`${zipId}-hint`} className="tonight-ask-hint">
            Enter a five-digit ZIP code.
          </p>
          <div className="tonight-ask-row">
            <input
              ref={input}
              id={zipId}
              aria-describedby={`${zipId}-hint`}
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
              aria-disabled={!/^\d{5}$/.test(zip) || pending}
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
                      setChosenSource(listSource);
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
      <p className="tonight-ask-hint" role="status" aria-live="polite">
        {status}
      </p>
    </div>
  );
}
