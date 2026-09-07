/** @vitest-environment node */

import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJob } from "./api";

describe("fetchJob JSON abort", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("aborts a hung JSON body when the caller signal aborts", async () => {
    let markJsonStart: (() => void) | undefined;
    const jsonStarted = new Promise<void>((resolve) => {
      markJsonStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => {
          if (markJsonStart === undefined) {
            throw new Error("JSON start is not armed");
          }
          markJsonStart();
          return new Promise(() => undefined);
        },
      })),
    );
    const controller = new AbortController();
    const pending = fetchJob("job-1", controller.signal);
    await jsonStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
