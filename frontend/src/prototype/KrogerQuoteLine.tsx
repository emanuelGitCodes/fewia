import type { JSX } from "react";
import type { KrogerQuote, KrogerStore } from "../chatTypes";
import { formatDollars } from "../money";

export const KROGER_DEGRADED_LINE = "Kroger did not answer, so no live price is shown.";

function localTime(iso: string): string {
  // Newer ICU puts a narrow no-break space before AM/PM; a plain space reads the same.
  return new Date(iso)
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    .replace(/\s/g, " ");
}

export function krogerQuoteSentence(quote: KrogerQuote, store: KrogerStore | null): string {
  const parts = [quote.product_label];
  if (quote.size !== null && quote.size.length > 0) {
    parts.push(quote.size);
  }
  parts.push(`regular ${formatDollars(quote.regular_cents)}`);
  if (quote.promo_cents !== null) {
    parts.push(`sale ${formatDollars(quote.promo_cents)}`);
  }
  if (quote.stock_level !== null && quote.stock_level.length > 0) {
    parts.push(`stock ${quote.stock_level.toLowerCase().replace(/_/g, " ")}`);
  }
  const name = store === null ? "Kroger" : `Kroger ${store.name}`;
  return (
    `Live price from ${name} as of ${localTime(quote.retrieved_at)}: ${parts.join(", ")}. ` +
    "Availability and the final price are not verified."
  );
}

export function KrogerQuoteLine(props: {
  quote: KrogerQuote | null;
  degraded: boolean;
  store: KrogerStore | null;
}): JSX.Element | null {
  if (props.quote !== null) {
    return <p className="tonight-ask-kroger">{krogerQuoteSentence(props.quote, props.store)}</p>;
  }
  return props.degraded ? <p className="tonight-ask-kroger">{KROGER_DEGRADED_LINE}</p> : null;
}
