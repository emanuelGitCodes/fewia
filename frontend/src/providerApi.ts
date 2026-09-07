import { readJson } from "./api";
import {
  SHAPE_ERROR,
  isBool,
  isRecord,
  isSpendingSource,
  type ProviderCapabilities,
} from "./apiTypes";

const PROVIDER_KEYS: ReadonlySet<string> = new Set([
  "chat_configured",
  "plaid_configured",
  "instacart_configured",
  "spending_source",
]);

export function parseProviders(value: unknown): ProviderCapabilities {
  if (!isRecord(value)) {
    throw new Error(SHAPE_ERROR);
  }
  const keys = Object.keys(value);
  if (keys.length !== PROVIDER_KEYS.size || keys.some((key) => !PROVIDER_KEYS.has(key))) {
    throw new Error(SHAPE_ERROR);
  }
  if (
    !isBool(value.chat_configured) ||
    !isBool(value.plaid_configured) ||
    !isBool(value.instacart_configured) ||
    !isSpendingSource(value.spending_source)
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    chat_configured: value.chat_configured,
    plaid_configured: value.plaid_configured,
    instacart_configured: value.instacart_configured,
    spending_source: value.spending_source,
  };
}

export async function fetchProviders(signal?: AbortSignal): Promise<ProviderCapabilities> {
  return parseProviders(await readJson("/api/grocery/providers", { method: "GET", signal }));
}
