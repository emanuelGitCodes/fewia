import { useEffect, useRef, useState } from "react";
import { isAbortError } from "./api";
import type { SupermarketEstimate as Overlay } from "./apiTypes";
import { fetchSupermarketEstimate } from "./supermarketApi";

const TIMEOUT_MS = 45_000;
const EXPIRE_MS = 5 * 60 * 1000;
const UNAVAILABLE = "The supermarket estimate is unavailable. Retry the estimate request.";
export const IN_PROGRESS = "The supermarket estimate request is in progress.";

export type SupermarketEstimateModel = {
  overlay: Overlay | null;
  error: string | null;
  pending: boolean;
  lookup: () => void;
};

export function useSupermarketEstimate(jobId: string): SupermarketEstimateModel {
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const attemptRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const clocks = useRef<Array<ReturnType<typeof setTimeout>>>([]);

  const clearClocks = (): void => {
    for (const timer of clocks.current) {
      clearTimeout(timer);
    }
    clocks.current = [];
  };

  const stop = (clearState: boolean): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    attemptRef.current += 1;
    pendingRef.current = false;
    clearClocks();
    if (clearState) {
      setOverlay(null);
      setError(null);
      setPending(false);
    }
  };

  useEffect(() => {
    stop(false);
    setOverlay(null);
    setError(null);
    setPending(false);
    const root =
      typeof document === "undefined" || typeof document.addEventListener !== "function"
        ? null
        : document;
    const onHidden = (): void => {
      if (root !== null && root.hidden) {
        stop(true);
      }
    };
    root?.addEventListener("visibilitychange", onHidden);
    return () => {
      root?.removeEventListener("visibilitychange", onHidden);
      stop(false);
    };
  }, [jobId]);

  const lookup = (): void => {
    if (pendingRef.current) {
      return;
    }
    stop(false);
    const controller = new AbortController();
    controllerRef.current = controller;
    const attempt = attemptRef.current;
    const live = (): boolean => attempt === attemptRef.current;
    pendingRef.current = true;
    setOverlay(null);
    setError(null);
    setPending(true);
    clocks.current.push(
      setTimeout(() => {
        if (!live()) {
          return;
        }
        attemptRef.current += 1;
        pendingRef.current = false;
        controller.abort();
        clearClocks();
        setOverlay(null);
        setError(UNAVAILABLE);
        setPending(false);
      }, TIMEOUT_MS),
    );
    void fetchSupermarketEstimate(jobId, controller.signal).then(
      (value) => {
        if (!live()) {
          return;
        }
        pendingRef.current = false;
        clearClocks();
        setOverlay(value);
        setError(null);
        setPending(false);
        clocks.current.push(setTimeout(() => stop(true), EXPIRE_MS));
      },
      (caught: unknown) => {
        if (!live() || isAbortError(caught)) {
          return;
        }
        pendingRef.current = false;
        clearClocks();
        setOverlay(null);
        setError(UNAVAILABLE);
        setPending(false);
        clocks.current.push(setTimeout(() => stop(true), EXPIRE_MS));
      },
    );
  };

  return { overlay, error, pending, lookup };
}
