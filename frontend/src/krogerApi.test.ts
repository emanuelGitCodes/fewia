// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { acceptSession, loseSession, OWNER_PROOF_STORAGE, workspaceStorageKey } from "./api";
import { HTTP_ERROR, SHAPE_ERROR } from "./apiTypes";
import {
  addToKrogerCart,
  connectKroger,
  disconnectKroger,
  findKrogerStores,
  previewKrogerCart,
  readKrogerConnection,
  validateKrogerStartUrl,
} from "./krogerApi";

const cartItem = {
  ingredient_id: "beans",
  name: "Black beans",
  upc: "0001111041600",
  description: "Kroger Black Beans",
  size: null,
  quantity: 2,
};
const confirmation = { confirmation_token: "confirmation-1", expires_in_seconds: 300 };

beforeEach(() => {
  acceptSession({ auth_mode: "local_demo", workspace_id: "12345678-1234-4234-8234-123456789abc" });
  window.sessionStorage.setItem(workspaceStorageKey(OWNER_PROOF_STORAGE), JSON.stringify({ proof: "owner-proof", expiresAt: Date.now() + 28800_000 }));
});

describe("previewKrogerCart", () => {
  it("posts the ids and maps the body", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        items: [cartItem],
        unmatched: [{ ingredient_id: "x", name: "Saffron" }],
        source: "live",
        ...confirmation,
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await previewKrogerCart("rev-1", "01400943");
    expect(result.source).toBe("live");
    expect(result.confirmationToken).toBe("confirmation-1");
    expect(result.items[0]).toMatchObject({
      upc: "0001111041600",
      size: null,
      quantity: 2,
    });
    expect(result.unmatched).toEqual([{ ingredientId: "x", name: "Saffron" }]);
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe(JSON.stringify({ plan_revision_id: "rev-1", location_id: "01400943" }));
  });

  it("rejects malformed bodies", async () => {
    const live = "live";
    const bad = [
      null,
      { items: [] },
      { items: [], unmatched: [], source: live, extra: 1 },
      { items: [{ ...cartItem, quantity: 11 }], unmatched: [], source: live },
      { items: [{ ...cartItem, upc: "12" }], unmatched: [], source: live },
      { items: [{ ...cartItem, extra: 1 }], unmatched: [], source: live },
      { items: [], unmatched: [{ ingredient_id: "x" }], source: live },
      { items: Array.from({ length: 31 }, () => cartItem), unmatched: [], source: live },
      { items: [cartItem, { ...cartItem, ingredient_id: "rice" }], unmatched: [], source: live },
      { items: [], unmatched: [] },
      { items: [], unmatched: [], source: "off" },
      { items: [], unmatched: [], source: "demo" },
      { items: [], unmatched: [], source: null },
    ];
    for (const body of bad) {
      reply(body === null ? null : {
        ...confirmation,
        confirmation_token: body.items.length === 0 ? null : confirmation.confirmation_token,
        ...body,
      });
      await expect(previewKrogerCart("rev-1", "01400943")).rejects.toThrow(SHAPE_ERROR);
    }
  });
});

describe("previewKrogerCart source", () => {
  it("accepts a fixture preview", async () => {
    reply({ items: [cartItem], unmatched: [], source: "fixture", ...confirmation });
    expect((await previewKrogerCart("rev-1", "01400943")).source).toBe("fixture");
  });
});

describe("addToKrogerCart", () => {
  it("maps status codes", async () => {
    const cases: [number, string][] = [
      [204, "added"],
      [409, "not_connected"],
      [503, "unavailable"],
      [400, "rejected"],
      [422, "rejected"],
      [504, "unknown"],
      [502, "unknown"],
      [500, "unknown"],
      [501, "unknown"],
      [505, "unknown"],
      [599, "unknown"],
    ];
    for (const [status, expected] of cases) {
      const fetchMock = vi.fn(async () => ({ status }) as Response);
      vi.stubGlobal("fetch", fetchMock);
      expect(await addToKrogerCart("confirmation-1")).toBe(expected);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
      expect(path).toBe("/api/grocery/kroger/cart/add");
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({ confirmation_token: "confirmation-1" });
      expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    }
  });

  it("returns unknown when the network fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("down");
      }),
    );
    expect(await addToKrogerCart("confirmation-1")).toBe("unknown");
    expect(fetch).toHaveBeenCalledTimes(1);
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
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok, json: async () => body }) as Response));
}

afterEach(() => {
  loseSession();
  vi.unstubAllGlobals();
});

describe("connectKroger", () => {
  it("posts connect and accepts only the allowed relative start URL", async () => {
    reply({ authorization_url: "/api/grocery/kroger/connect/start?attempt=opaque" });
    expect(await connectKroger()).toBe("/api/grocery/kroger/connect/start?attempt=opaque");
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it.each([
    "https://foreign.example/api/grocery/kroger/connect/start",
    "//foreign.example/api/grocery/kroger/connect/start",
    "/api/grocery/kroger/connect/start#fragment", "/api/grocery/kroger/connection",
    "/api/grocery/kroger/connect/../connection", "javascript:alert(1)",
    "/\\foreign.example/api/grocery/kroger/connect/start", " /api/grocery/kroger/connect/start",
  ])("rejects unsafe start URLs %s", (url) => {
    expect(() => validateKrogerStartUrl(url)).toThrow(SHAPE_ERROR);
  });

  it("rejects an absolute URL even on this origin", () => {
    expect(() => validateKrogerStartUrl(`${window.location.origin}/api/grocery/kroger/connect/start`)).toThrow(SHAPE_ERROR);
  });
});

describe("cart confirmation shape", () => {
  it.each(["live", "fixture"])("accepts an empty %s preview with a null token", async (source) => {
    reply({ items: [], unmatched: [{ ingredient_id: "x", name: "Saffron" }], source,
      confirmation_token: null, expires_in_seconds: 300 });
    expect(await previewKrogerCart("rev-1", "01400943")).toEqual({
      items: [], unmatched: [{ ingredientId: "x", name: "Saffron" }], source,
      confirmationToken: null, expiresInSeconds: 300,
    });
  });

  it.each([
    { items: [], confirmation_token: "token" },
    { items: [], confirmation_token: "" },
    { items: [], confirmation_token: undefined },
    { items: [cartItem], confirmation_token: null },
    { items: [cartItem], confirmation_token: "" },
    { items: [cartItem], confirmation_token: 123 },
    { items: [cartItem], confirmation_token: "x".repeat(8193) },
  ])("rejects mismatched items and token %#", async (fields) => {
    reply({ unmatched: [], source: "live", expires_in_seconds: 300, ...fields });
    await expect(previewKrogerCart("rev-1", "01400943")).rejects.toThrow(SHAPE_ERROR);
  });

  it.each([null, 0, 299, 301, "300"])("rejects invalid empty-preview expiry %s", async (expires) => {
    reply({ items: [], unmatched: [], source: "live", confirmation_token: null, expires_in_seconds: expires });
    await expect(previewKrogerCart("rev-1", "01400943")).rejects.toThrow(SHAPE_ERROR);
  });

  it.each([
    {}, { confirmation_token: "", expires_in_seconds: 300 },
    { confirmation_token: "token", expires_in_seconds: 301 },
    { confirmation_token: "token", expires_in_seconds: "300" },
  ])("rejects invalid confirmation %#", async (fields) => {
    reply({ items: [cartItem], unmatched: [], source: "live", ...fields });
    await expect(previewKrogerCart("rev-1", "01400943")).rejects.toThrow(SHAPE_ERROR);
  });
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("down");
      }),
    );
    await expect(disconnectKroger()).rejects.toThrow(HTTP_ERROR);
  });
});

describe("findKrogerStores", () => {
  it("posts the ZIP in the body with no query string and maps the stores", async () => {
    reply({ stores: [store], source: "live" });
    const result = await findKrogerStores("45202");
    expect(result.source).toBe("live");
    expect(result.stores).toEqual([
      {
        locationId: "01400943",
        name: "Main Street",
        addressLine: "1 Test Way",
        city: "Springfield",
        state: "OH",
      },
    ]);
    const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(path).toBe("/api/grocery/kroger/stores");
    expect(String(path)).not.toContain("?");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ zip_code: "45202" }));
  });

  it("accepts an empty list", async () => {
    reply({ stores: [], source: "live" });
    expect(await findKrogerStores("45202")).toEqual({ stores: [], source: "live" });
  });

  it("returns the fixture source", async () => {
    reply({ stores: [store], source: "fixture" });
    expect((await findKrogerStores("45202")).source).toBe("fixture");
  });

  it("throws SHAPE_ERROR for a missing, unknown, or extra source key", async () => {
    const bad: unknown[] = [
      { stores: [store] },
      { stores: [store], source: "off" },
      { stores: [store], source: "demo" },
      { stores: [store], source: null },
      { stores: [store], source: "live", extra: 1 },
    ];
    for (const body of bad) {
      reply(body);
      await expect(findKrogerStores("45202")).rejects.toThrow(SHAPE_ERROR);
    }
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
    reply({ stores: [{ ...store, city: "😀".repeat(160) }], source: "live" });
    expect((await findKrogerStores("45202")).stores).toHaveLength(1);
    reply({ stores: [{ ...store, city: "😀".repeat(161) }], source: "live" });
    await expect(findKrogerStores("45202")).rejects.toThrow(SHAPE_ERROR);
  });

  it("throws HTTP_ERROR on a failed status", async () => {
    reply({ detail: "bad" }, false);
    await expect(findKrogerStores("45202")).rejects.toThrow(HTTP_ERROR);
  });
});
