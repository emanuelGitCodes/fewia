/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchSyncItems, type SyncItem, type SyncJob } from "./syncApi";
import { useSyncJob } from "./useSyncJob";
import { SpendingRefresh, type SpendingRefreshProps } from "./SpendingRefresh";

vi.mock("./syncApi", () => ({
  fetchSyncItems: vi.fn(),
}));
vi.mock("./useSyncJob", () => ({
  useSyncJob: vi.fn(),
}));

const LOAD_MS = 15_000;
const ITEM_A = "item-a";
const ITEM_B = "item-b";
const JOB_1 = "00000000-0000-0000-0000-000000000001";
const JOB_2 = "00000000-0000-0000-0000-000000000002";
const STAMP = "2026-09-06T15:00:00Z";
const RAW = "token access_token cursor secret";
const LOAD_ERROR = "The connection list is unavailable.";
const HTTP_FALLBACK = "The sync request failed. Check the item, then retry.";
const SYNC_FAILURE = "The sync request failed. Retry checks the same request.";

const itemA: SyncItem = { id: ITEM_A, last_synced_at: null };
const itemB: SyncItem = { id: ITEM_B, last_synced_at: STAMP };

type HookValue = ReturnType<typeof useSyncJob>;

const mockedFetch = vi.mocked(fetchSyncItems);
const mockedHook = vi.mocked(useSyncJob);

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") return node;
  return node.children.map((child) => childText(child)).join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) throw new Error(`missing button ${name}`);
  return match;
}

function job(status: SyncJob["status"], id = JOB_1): SyncJob {
  return {
    id,
    status,
    result: status === "succeeded" ? { source: "plaid_sandbox", changed_count: 2 } : null,
    error_code: status === "failed" ? RAW : null,
  };
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function hang(signal?: AbortSignal): Promise<SyncItem[]> {
  return new Promise((_resolve, reject) => {
    const fail = (): void => {
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (signal === undefined) return;
    if (signal.aborted) {
      fail();
      return;
    }
    signal.addEventListener("abort", fail, { once: true });
  });
}

function makeHook(): HookValue {
  const value: HookValue = {
    job: null,
    error: null,
    pending: false,
    start: vi.fn(async () => undefined),
    retry: vi.fn(async () => undefined),
    clear: vi.fn(() => {
      value.job = null;
      value.error = null;
      value.pending = false;
    }),
  };
  return value;
}

describe("SpendingRefresh", () => {
  let hook: HookValue;

  function mount(props: Partial<SpendingRefreshProps> = {}): {
    renderer: ReactTestRenderer;
    onRefreshed: ReturnType<typeof vi.fn<() => void>>;
    update: (patch?: Partial<SpendingRefreshProps>) => void;
  } {
    const onRefreshedSpy = vi.fn<() => void>();
    const state: SpendingRefreshProps = {
      configured: props.configured ?? true,
      disabled: props.disabled,
      onRefreshed: props.onRefreshed ?? onRefreshedSpy,
    };
    let renderer: ReactTestRenderer | undefined;
    act(() => {
      renderer = create(
        createElement(SpendingRefresh, {
          configured: state.configured,
          disabled: state.disabled,
          onRefreshed: state.onRefreshed,
        }),
      );
    });
    if (renderer === undefined) throw new Error("renderer failed to mount");
    const live = renderer;
    return {
      renderer: live,
      onRefreshed: onRefreshedSpy,
      update: (patch: Partial<SpendingRefreshProps> = {}): void => {
        if (patch.configured !== undefined) state.configured = patch.configured;
        if (patch.disabled !== undefined) state.disabled = patch.disabled;
        if (patch.onRefreshed !== undefined) state.onRefreshed = patch.onRefreshed;
        act(() => {
          live.update(
            createElement(SpendingRefresh, {
              configured: state.configured,
              disabled: state.disabled,
              onRefreshed: state.onRefreshed,
            }),
          );
        });
      },
    };
  }

  async function flush(): Promise<void> {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      writable: true,
      value: globalThis,
    });
    vi.useFakeTimers();
    hook = makeHook();
    mockedHook.mockImplementation(() => hook);
    mockedFetch.mockReset();
    mockedFetch.mockResolvedValue([itemA, itemB]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows Sandbox refresh unavailable without a network call", () => {
    const { renderer } = mount({ configured: false });
    expect(mockedFetch).not.toHaveBeenCalled();
    expect(hook.start).not.toHaveBeenCalled();
    expect(childText(renderer.root)).toContain("Sandbox refresh unavailable.");
    expect(renderer.root.findAllByType("select")).toHaveLength(0);
    expect(renderer.root.findAllByType("button")).toHaveLength(0);
    expect(childText(renderer.root)).not.toContain(RAW);
    renderer.unmount();
  });

  it("shows setup required for an empty list and invents no connection", async () => {
    mockedFetch.mockResolvedValue([]);
    const { renderer } = mount();
    await flush();
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch.mock.calls[0]?.[0]).toBeInstanceOf(AbortSignal);
    expect(childText(renderer.root)).toContain("Sandbox setup is required.");
    expect(renderer.root.findAllByType("select")).toHaveLength(0);
    expect(renderer.root.findAllByType("button")).toHaveLength(0);
    expect(childText(renderer.root)).not.toContain("Sandbox connection 1");
    expect(hook.start).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("shows a safe load error and Reload connections", async () => {
    mockedFetch.mockRejectedValue(new Error(RAW));
    const { renderer } = mount();
    await flush();
    expect(childText(renderer.root)).toContain(LOAD_ERROR);
    expect(childText(renderer.root)).not.toContain(RAW);
    const reload = buttonNamed(renderer.root, "Reload connections");
    expect(reload.props.disabled).toBe(false);
    mockedFetch.mockReset();
    mockedFetch.mockResolvedValue([itemA]);
    await act(async () => {
      (reload.props.onClick as () => void)();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(childText(renderer.root)).toContain("Sandbox connection 1");
    expect(childText(renderer.root)).toContain("Never synced");
    renderer.unmount();
  });

  it("times out a hung list load after 15s", async () => {
    mockedFetch.mockImplementation((signal) => hang(signal));
    const { renderer } = mount();
    expect(childText(renderer.root)).toContain("Loading connections.");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LOAD_MS);
      await Promise.resolve();
    });
    expect(childText(renderer.root)).toContain(LOAD_ERROR);
    buttonNamed(renderer.root, "Reload connections");
    expect(mockedFetch.mock.calls[0]?.[0]?.aborted).toBe(true);
    renderer.unmount();
  });

  it("loads labels from internal ids and starts only on click", async () => {
    const { renderer } = mount();
    await flush();
    const select = renderer.root.findByType("select");
    const options = renderer.root.findAllByType("option");
    expect(select.props.value).toBe(ITEM_A);
    expect(options).toHaveLength(2);
    expect(options[0]?.props.value).toBe(ITEM_A);
    expect(options[1]?.props.value).toBe(ITEM_B);
    expect(childText(options[0] as ReactTestInstance)).toBe("Sandbox connection 1");
    expect(childText(options[1] as ReactTestInstance)).toBe("Sandbox connection 2");
    expect(childText(renderer.root)).toContain("Never synced");
    expect(hook.start).not.toHaveBeenCalled();
    const refresh = buttonNamed(renderer.root, "Refresh connection");
    expect(refresh.props.disabled).toBe(false);
    await act(async () => {
      (refresh.props.onClick as () => void)();
    });
    expect(hook.start).toHaveBeenCalledTimes(1);
    expect(hook.start).toHaveBeenCalledWith(ITEM_A);
    expect(hook.retry).not.toHaveBeenCalled();
    act(() => {
      (select.props.onChange as (event: { target: { value: string } }) => void)({
        target: { value: ITEM_B },
      });
    });
    expect(hook.clear).toHaveBeenCalled();
    expect(select.props.value).toBe(ITEM_B);
    expect(childText(renderer.root)).toContain(STAMP);
    renderer.unmount();
  });

  it("disables controls when disabled or busy", async () => {
    const { renderer, update } = mount({ disabled: true });
    await flush();
    expect(renderer.root.findByType("select").props.disabled).toBe(true);
    const refresh = buttonNamed(renderer.root, "Refresh connection");
    expect(refresh.props.disabled).toBe(true);
    await act(async () => {
      (refresh.props.onClick as () => void)();
    });
    expect(hook.start).not.toHaveBeenCalled();
    hook.pending = true;
    update({ disabled: false });
    expect(buttonNamed(renderer.root, "Refresh connection").props.disabled).toBe(true);
    renderer.unmount();
  });

  it("retries transport errors and starts a fresh refresh after failure", async () => {
    const { renderer, update } = mount();
    await flush();
    hook.error = HTTP_FALLBACK;
    update();
    const retry = buttonNamed(renderer.root, "Retry refresh");
    expect(childText(renderer.root)).toContain(HTTP_FALLBACK);
    await act(async () => {
      (retry.props.onClick as () => void)();
    });
    expect(hook.retry).toHaveBeenCalledTimes(1);
    expect(hook.start).not.toHaveBeenCalled();
    hook.error = SYNC_FAILURE;
    hook.job = job("failed");
    update();
    expect(renderer.root.findAll((node) => childText(node) === "Retry refresh")).toHaveLength(0);
    expect(childText(renderer.root)).toContain("The refresh request failed.");
    expect(childText(renderer.root)).not.toContain(RAW);
    const fresh = buttonNamed(renderer.root, "Refresh connection");
    await act(async () => {
      (fresh.props.onClick as () => void)();
    });
    expect(hook.start).toHaveBeenCalledTimes(1);
    expect(hook.start).toHaveBeenCalledWith(ITEM_A);
    expect(hook.retry).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("announces loading, running, queued, and success without a live budget claim", async () => {
    mockedFetch.mockImplementation((signal) => hang(signal));
    const loading = mount();
    const status = loading.renderer.root.findAll(
      (node) => node.type === "p" && (node.props as { role?: string }).role === "status",
    );
    expect(childText(status[0] as ReactTestInstance)).toBe("Loading connections.");
    expect(status[0]?.props["aria-live"]).toBe("polite");
    loading.renderer.unmount();

    mockedFetch.mockReset();
    mockedFetch.mockResolvedValue([itemA]);
    const { renderer, update } = mount();
    await flush();
    hook.pending = true;
    hook.job = job("queued");
    update();
    expect(childText(renderer.root)).toContain("The refresh request is queued.");
    hook.job = job("running");
    update();
    expect(childText(renderer.root)).toContain("The refresh request is running.");
    hook.pending = false;
    hook.job = job("succeeded");
    update();
    expect(childText(renderer.root)).toContain("The connection refreshed.");
    expect(childText(renderer.root)).not.toContain("live");
    expect(childText(renderer.root)).not.toContain("fixture");
    renderer.unmount();
  });

  it("calls onRefreshed once per succeeded job and reloads timestamps", async () => {
    mockedFetch
      .mockResolvedValueOnce([itemA])
      .mockResolvedValueOnce([{ id: ITEM_A, last_synced_at: STAMP }])
      .mockResolvedValue([itemA]);
    const { renderer, update, onRefreshed } = mount();
    await flush();
    expect(childText(renderer.root)).toContain("Never synced");
    hook.job = job("succeeded", JOB_1);
    update();
    await flush();
    expect(onRefreshed).toHaveBeenCalledTimes(1);
    expect(childText(renderer.root)).toContain(STAMP);
    update();
    await flush();
    expect(onRefreshed).toHaveBeenCalledTimes(1);
    hook.job = job("succeeded", JOB_2);
    update();
    await flush();
    expect(onRefreshed).toHaveBeenCalledTimes(2);
    renderer.unmount();
  });

  it("ignores a stale list response after disable and after unmount", async () => {
    const first = deferred<SyncItem[]>();
    let firstSignal: AbortSignal | undefined;
    mockedFetch.mockImplementationOnce((signal) => {
      firstSignal = signal;
      return first.promise;
    });
    mockedFetch.mockResolvedValue([itemB]);
    const { renderer, update } = mount();
    expect(childText(renderer.root)).toContain("Loading connections.");
    update({ configured: false });
    expect(firstSignal?.aborted).toBe(true);
    expect(hook.clear).toHaveBeenCalled();
    expect(childText(renderer.root)).toContain("Sandbox refresh unavailable.");
    await act(async () => {
      first.resolve([itemA]);
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain("Sandbox connection 1");
    expect(childText(renderer.root)).not.toContain(ITEM_A);
    update({ configured: true });
    await flush();
    expect(renderer.root.findByType("select").props.value).toBe(ITEM_B);
    expect(childText(renderer.root)).toContain("Sandbox connection 1");
    expect(childText(renderer.root)).toContain(STAMP);
    renderer.unmount();

    const late = deferred<SyncItem[]>();
    let lateSignal: AbortSignal | undefined;
    mockedFetch.mockReset();
    mockedFetch.mockImplementation((signal) => {
      lateSignal = signal;
      return late.promise;
    });
    const second = mount();
    act(() => {
      second.renderer.unmount();
    });
    expect(lateSignal?.aborted).toBe(true);
    await act(async () => {
      late.resolve([itemA]);
      await Promise.resolve();
    });
  });

  it("does not write browser storage or echo provider material", async () => {
    const { renderer } = mount();
    await flush();
    expect(childText(renderer.root)).not.toContain(RAW);
    expect(childText(renderer.root)).not.toContain("access_token");
    expect("localStorage" in globalThis ? globalThis.localStorage : undefined).toBeUndefined();
    renderer.unmount();
  });
});
