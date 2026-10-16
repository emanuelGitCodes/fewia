import { parseDollars } from "../money";

const AMOUNT_ERROR = "Enter a non-negative dollar amount with at most two decimal places.";

// The count rounds up to whole catalog packages.
export function packageCount(totalQuantity: number, packageQuantity: number): number {
  if (totalQuantity <= 0) {
    return 0;
  }
  return Math.trunc((totalQuantity + packageQuantity - 1) / packageQuantity);
}

export function withBudgetInput<
  T extends { budgetInput: string; budgetCents: number; budgetError: string | null },
>(state: T, budgetInput: string): T {
  // The raw draft updates on every change.
  // budgetCents updates only when the draft is valid.
  try {
    const budgetCents = parseDollars(budgetInput);
    if (budgetCents === null) {
      return { ...state, budgetInput, budgetError: AMOUNT_ERROR };
    }
    return { ...state, budgetInput, budgetCents, budgetError: null };
  } catch (error) {
    const budgetError = error instanceof Error ? error.message : AMOUNT_ERROR;
    return { ...state, budgetInput, budgetError };
  }
}

export function formatMacro(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
