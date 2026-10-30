import type {
  GroceryBudget,
  GroceryPlan,
  GroceryRequest,
  JobStatus,
  MealPlanNutrition,
  SpendingSource,
} from "./apiTypes";

export type ChatResultStatus =
  | "planned"
  | "needs_revision"
  | "clarification"
  | "limit"
  | "incomplete";

export type ChatSpendingSource = SpendingSource;

export type ChatToolOutcome = "success" | "error";

export type ChatUsage = {
  inputTokens: number;
  outputTokens: number;
  cacheReadInputTokens?: number;
  cacheWriteInputTokens?: number;
};

export type ChatToolTrace = {
  tool: string;
  outcome: ChatToolOutcome;
  tool_use_id: string;
  sequence: number;
  revision_index: number | null;
  evidence_id?: string;
  evidence_revision_id?: string;
};

export type KrogerStore = { locationId: string; name: string };

export type KrogerQuote = {
  kind: "store_live";
  ingredient_id: string;
  product_label: string;
  brand: string | null;
  size: string | null;
  regular_cents: number;
  promo_cents: number | null;
  stock_level: string | null;
  location_id: string;
  retrieved_at: string;
};

export type ChatResult = {
  status: ChatResultStatus;
  answer: string;
  plan: GroceryPlan | null;
  budget: GroceryBudget | null;
  request: GroceryRequest | null;
  meal_nutrition: MealPlanNutrition | null;
  kroger_quote?: KrogerQuote | null;
  kroger_degraded?: true;
  proposal_id?: string;
  evidence_id: string | null;
  evidence_revision_id: string | null;
  spending_source: ChatSpendingSource;
  tool_trace: ChatToolTrace[];
  model_turns: number;
  planner_revisions: number;
  usage: ChatUsage | null;
};

export type ChatJobCreate = {
  message: string;
  monthly_limit_cents: number;
  plan_cap_cents: number | null;
  previous_job_id: string | null;
  plan_revision_id: string | null;
};

export type ChatJob = {
  id: string;
  status: JobStatus;
  result: ChatResult | null;
  error_code: string | null;
};
