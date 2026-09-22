import type {
  GroceryBudget,
  GroceryPlan,
  GroceryRequest,
  JobStatus,
  MealPlanNutrition,
} from "./apiTypes";

export type ChatResultStatus =
  | "planned"
  | "needs_revision"
  | "clarification"
  | "limit"
  | "incomplete";

export type ChatSpendingSource = "fixture" | "plaid_sandbox";

export type ChatToolOutcome = "success" | "error";

export type ChatUsage = {
  inputTokens: number;
  outputTokens: number;
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

export type ChatResult = {
  status: ChatResultStatus;
  answer: string;
  plan: GroceryPlan | null;
  budget: GroceryBudget | null;
  request: GroceryRequest | null;
  meal_nutrition: MealPlanNutrition | null;
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
};

export type ChatJob = {
  id: string;
  status: JobStatus;
  result: ChatResult | null;
  error_code: string | null;
};
