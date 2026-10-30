import { afterEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR } from "./apiTypes";
import { disconnectKroger, findKrogerStores, readKrogerConnection } from "./krogerApi";

const store = {
  location_id: "01400943",
  name: "Main Street",
  address_line: "1 Test Way",
  city: "Springfield",
  state: "OH",
};

function reply(body: unknown, ok = true): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, json: async () => body }) as Response),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("readKrogerConnection", () => {
  it("returns the boolean", async () => {
    reply({ connected: true });
    expect(await readKrogerConnection()).toBe(true);
    reply({ connected: false });
    expect(await readKrogerConnection()).toBe(false);
  });

  it("throws SHAPE_ERROR for a malformed body", async () => {
    for (const body of [null, {}, { connected: "yes" }, { connected: true, extra: 1 }]) {
      reply(body);
      await expect(readKrogerConnection()).rejects.toThrow(SHAPE_ERROR);
    }
  });

  it("throws HTTP_ERROR on a 503", async () => {
    reply({}, false);
    await expect(readKrogerConnection()).rejects.toThrow(HTTP_ERROR);
  });
});

describe("disconnectKroger", () => {
  it("sends DELETE and accepts 204", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 204 }) as Response));
    await disconnectKroger();
    const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(path).toBe("/api/grocery/kroger/connection");
    expect(init?.method).toBe("DELETE");
  });

  it("throws HTTP_ERROR on any other status or a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200 }) as Response));
    await expect(disconnectKroger()).rejects.toThrow(HTTP_ERROR);
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("down"); }));
    await expect(disconnectKroger()).rejects.toThrow(HTTP_ERROR);
  });
});

describe("findKrogerStores", () => {
  it("posts the ZIP in the body with no query string and maps the stores", async () => {
    reply({ stores: [store] });
    const stores = await findKrogerStores("45202");
    expect(stores).toEqual([
      { locationId: "01400943", name: "Main Street", addressLine: "1 Test Way", city: "Springfield", state: "OH" },
    ]);
    const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(path).toBe("/api/grocery/kroger/stores");
    expect(String(path)).not.toContain("?");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ zip_code: "45202" }));
  });

  it("accepts an empty list", async () => {
    reply({ stores: [] });
    expect(await findKrogerStores("45202")).toEqual([]);
  });

  it("throws SHAPE_ERROR for each malformed response", async () => {
    const missing: Record<string, unknown> = { ...store };
    delete missing.city;
    const bad: unknown[] = [
      null,
      { stores: "x" },
      {},
      { stores: Array.from({ length: 6 }, () => store) },
      { stores: [missing] },
      { stores: [{ ...store, extra: "x" }] },
      { stores: [{ ...store, location_id: "0140094" }] },
      { stores: [{ ...store, location_id: "014009430" }] },
      { stores: [{ ...store, location_id: "0140094!" }] },
      { stores: [{ ...store, name: "" }] },
      { stores: [{ ...store, address_line: 5 }] },
      { stores: [{ ...store, city: "x".repeat(161) }] },
      { stores: [{ ...store, state: null }] },
      { stores: ["store"] },
    ];
    for (const body of bad) {
      reply(body);
      await expect(findKrogerStores("45202")).rejects.toThrow(SHAPE_ERROR);
    }
  });

  it("counts text length in code points, not UTF-16 units", async () => {
    reply({ stores: [{ ...store, city: "😀".repeat(160) }] });
    expect(await findKrogerStores("45202")).toHaveLength(1);
    reply({ stores: [{ ...store, city: "😀".repeat(161) }] });
    await expect(findKrogerStores("45202")).rejects.toThrow(SHAPE_ERROR);
  });

  it("throws HTTP_ERROR on a failed status", async () => {
    reply({ detail: "bad" }, false);
    await expect(findKrogerStores("45202")).rejects.toThrow(HTTP_ERROR);
  });
});
