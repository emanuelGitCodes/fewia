import { afterEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR } from "./apiTypes";
import {
  addToKrogerCart,
  disconnectKroger,
  findKrogerStores,
  previewKrogerCart,
  readKrogerConnection,
} from "./krogerApi";

const cartItem = {
  ingredient_id: "beans",
  name: "Black beans",
  upc: "0001111041600",
  description: "Kroger Black Beans",
  size: null,
  quantity: 2,
};

describe("previewKrogerCart", () => {
  it("posts the ids and maps the body", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ items: [cartItem], unmatched: [{ ingredient_id: "x", name: "Saffron" }] }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await previewKrogerCart("rev-1", "01400943");
    expect(result.items[0]).toMatchObject({ upc: "0001111041600", size: null, quantity: 2 });
    expect(result.unmatched).toEqual([{ ingredientId: "x", name: "Saffron" }]);
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe(JSON.stringify({ plan_revision_id: "rev-1", location_id: "01400943" }));
  });

  it("rejects malformed bodies", async () => {
    const bad = [
      null,
      { items: [] },
      { items: [], unmatched: [], extra: 1 },
      { items: [{ ...cartItem, quantity: 11 }], unmatched: [] },
      { items: [{ ...cartItem, upc: "12" }], unmatched: [] },
      { items: [{ ...cartItem, extra: 1 }], unmatched: [] },
      { items: [], unmatched: [{ ingredient_id: "x" }] },
      { items: Array.from({ length: 31 }, () => cartItem), unmatched: [] },
    ];
    for (const body of bad) {
      reply(body);
      await expect(previewKrogerCart("rev-1", "01400943")).rejects.toThrow(SHAPE_ERROR);
    }
  });
});

describe("addToKrogerCart", () => {
  it("maps status codes", async () => {
    const cases: [number, string][] = [
      [204, "added"],
      [409, "not_connected"],
      [503, "unavailable"],
      [504, "unknown"],
      [500, "unknown"],
    ];
    for (const [status, expected] of cases) {
      vi.stubGlobal("fetch", vi.fn(async () => ({ status }) as Response));
      expect(await addToKrogerCart([{ upc: "0001111041600", quantity: 1 }])).toBe(expected);
    }
  });

  it("returns unknown when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("down"); }));
    expect(await addToKrogerCart([{ upc: "0001111041600", quantity: 1 }])).toBe("unknown");
  });
});

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
