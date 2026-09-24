import { useEffect, useRef, useState } from "react";
import { isAbortError } from "./api";
import { fetchSyncItems, type SyncItem } from "./syncApi";
import { useSyncJob } from "./useSyncJob";

export type SpendingRefreshProps = {
  configured: boolean;
  disabled?: boolean;
  onRefreshed: () => void;
};

const LOAD_MS = 15_000;
const LOAD_ERROR = "The connection list is unavailable.";

function liveText(
  loadPending: boolean,
  empty: boolean,
  pending: boolean,
  status: string | undefined,
): string | null {
  if (loadPending && empty) return "Loading connections.";
  if (pending && status === "queued") return "The refresh request is queued.";
  if (pending) return "The refresh request is running.";
  if (status === "succeeded") return "The connection refreshed.";
  if (status === "failed") return "The refresh request failed.";
  return null;
}

export function SpendingRefresh({
  configured, disabled = false, onRefreshed,
}: SpendingRefreshProps): JSX.Element {
  const { job, error, pending, start, retry, clear } = useSyncJob();
  const [items, setItems] = useState<SyncItem[]>([]);
  const [loadPending, setLoadPending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [loadTick, setLoadTick] = useState(0);
  const seenJobs = useRef(new Set<string>());

  useEffect(() => {
    if (!configured) {
      setItems([]);
      setSelectedId("");
      setLoadPending(false);
      setLoadError(null);
      clear();
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    let timedOut = false;
    const timer = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, LOAD_MS);
    setLoadPending(true);
    setLoadError(null);
    void fetchSyncItems(controller.signal).then(
      (next) => {
        if (cancelled) return;
        setItems(next);
        setLoadPending(false);
        setSelectedId((current) =>
          next.some((item) => item.id === current) ? current : (next[0]?.id ?? ""),
        );
      },
      (caught: unknown) => {
        if (cancelled || (isAbortError(caught) && !timedOut)) return;
        setItems([]);
        setSelectedId("");
        setLoadError(LOAD_ERROR);
        setLoadPending(false);
      },
    ).finally(() => window.clearTimeout(timer));
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [configured, loadTick, clear]);

  useEffect(() => {
    if (!configured || job?.status !== "succeeded" || seenJobs.current.has(job.id)) return;
    seenJobs.current.add(job.id);
    onRefreshed();
    setLoadTick((tick) => tick + 1);
  }, [configured, job, onRefreshed]);

  const selected = items.find((item) => item.id === selectedId);
  const busy = pending || loadPending;
  const blocked = Boolean(disabled);
  const failed = job?.status === "failed";
  const showRetry = error !== null && !failed && job?.status !== "succeeded";
  const refreshOff = blocked || busy || selectedId === "";
  const live = liveText(loadPending, items.length === 0, pending, job?.status);
  const actionOff = showRetry ? blocked || busy : refreshOff;
  return (
    <section aria-labelledby="spending-refresh-heading">
      <h2 id="spending-refresh-heading">Spending refresh</h2>
      {!configured ? <p className="panel-note">Sandbox refresh unavailable.</p> : null}
      {configured && loadError !== null ? (
        <>
          <p className="form-error" role="status">{LOAD_ERROR}</p>
          <button type="button" className="retry-catalog" disabled={blocked || pending} onClick={() => setLoadTick((tick) => tick + 1)}>
            Reload connections
          </button>
        </>
      ) : null}
      {configured && loadError === null && !loadPending && items.length === 0 ? (
        <p className="panel-note">Sandbox setup is required.</p>
      ) : null}
      {configured && items.length > 0 ? (
        <>
          <label htmlFor="spending-connection">Sandbox connection</label>
          <select id="spending-connection" value={selectedId} disabled={blocked || loadPending}
            onChange={(event) => {
              const next = event.target.value;
              if (next !== selectedId) clear();
              setSelectedId(next);
            }}>
            {items.map((item, index) => (
              <option key={item.id} value={item.id}>{`Sandbox connection ${index + 1}`}</option>
            ))}
          </select>
          <p className="budget-source">{selected?.last_synced_at ?? "Never synced"}</p>
        </>
      ) : null}
      {configured && items.length > 0 ? (
        <button type="button" className="rebuild-estimate" disabled={actionOff}
          onClick={() => {
            if (showRetry) void retry();
            else if (!refreshOff) void start(selectedId);
          }}>
          {showRetry ? "Retry refresh" : "Refresh connection"}
        </button>
      ) : null}
      {configured && live !== null ? (
        <p className="catalog-status" role="status" aria-live="polite">{live}</p>
      ) : null}
      {configured && showRetry ? <p className="form-error" role="status">{error}</p> : null}
    </section>
  );
}
