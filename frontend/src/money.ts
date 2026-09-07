const AMOUNT_ERROR =
  "Enter a non-negative dollar amount with at most two decimal places.";
const INCOMPLETE_ESTIMATE = "Incomplete estimate";
const DECIMAL = /^(0|[1-9]\d*)(?:\.(\d{1,2}))?$/;

export function parseDollars(value: string, optional?: boolean): number | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    if (optional === true) {
      return null;
    }
    throw new Error(AMOUNT_ERROR);
  }
  const match = DECIMAL.exec(trimmed);
  const whole = match?.[1];
  if (match === null || whole === undefined) {
    throw new Error(AMOUNT_ERROR);
  }
  const fraction = (match[2] ?? "").padEnd(2, "0");
  const cents = BigInt(whole) * 100n + BigInt(fraction);
  if (cents > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error(AMOUNT_ERROR);
  }
  return Number(cents);
}

export function formatDollars(cents: number | null): string {
  if (cents === null) {
    return INCOMPLETE_ESTIMATE;
  }
  const sign = cents < 0 ? "-" : "";
  const absolute = Math.abs(cents);
  const dollars = Math.trunc(absolute / 100);
  const fraction = String(absolute % 100).padStart(2, "0");
  return `${sign}$${dollars.toLocaleString("en-US")}.${fraction}`;
}
