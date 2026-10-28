import { describe, expect, it } from "vitest";
import type { ChatJob, ChatResult } from "../chatTypes";
import {
  chatBudget,
  ideasFromJob,
  planChatPrefix,
  retainChatReplies,
  type ChatReply,
} from "./planChatModel";
import { addMeal, initialPlanState, removeMeal, togglePlanPantry, withPlanBudgetInput } from "./planModel";

function jobWith(
  status: ChatResult["status"],
  meals: Array<{ recipe_id: string; servings: number }>,
): ChatJob {
  const result = {
    status,
    answer: "ok",
    plan: null,
    budget: null,
    request:
      status === "clarification"
        ? null
        : {
            meals,
            budget_period: "2026-09-01",
            plan_cap_cents: null,
            pantry_ingredients: [],
            ingredient_exclusions: [],
            diet: "omnivore",
          },
    meal_nutrition: null,
    evidence_id: null,
    evidence_revision_id: null,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 1,
    planner_revisions: 0,
    usage: null,
  } as ChatResult;
  return { id: "job-1", status: "succeeded", result, error_code: null };
}

describe("planChatPrefix", () => {
  it("states the meals, the pantry in order, and the plan cap", () => {
    const prefix = planChatPrefix(initialPlanState());
    expect(prefix.startsWith("My current plan: Bean tacos, 2 servings. Pantry: ")).toBe(true);
    expect(prefix).toContain("olive oil");
    expect(prefix.endsWith(" Plan cap: $40.00.\n\n")).toBe(true);
  });

  it("joins several meals and keeps pantry order", () => {
    let state = addMeal(initialPlanState(), "chickpea_curry", 1);
    state = { ...state, pantry: ["salt", "olive_oil"] };
    const prefix = planChatPrefix(state);
    expect(prefix).toContain("Bean tacos, 2 servings; Chickpea curry, 1 serving.");
    expect(prefix).toContain("Pantry: salt, olive oil.");
  });

  it("says none when the pantry is empty", () => {
    const state = { ...initialPlanState(), pantry: [] };
    expect(planChatPrefix(state)).toContain("Pantry: none.");
  });

  it("reports no meals but still states the pantry and the plan cap", () => {
    const state = removeMeal(initialPlanState(), "bean_tacos");
    const prefix = planChatPrefix(state);
    expect(prefix.startsWith("My current plan: no meals. Pantry: ")).toBe(true);
    expect(prefix).toContain("olive oil");
    expect(prefix.endsWith(" Plan cap: $40.00.\n\n")).toBe(true);
    expect(planChatPrefix({ ...state, pantry: [] })).toBe(
      "My current plan: no meals. Pantry: none. Plan cap: $40.00.\n\n",
    );
  });

  it("follows the pantry toggle", () => {
    const state = togglePlanPantry(initialPlanState(), "olive_oil");
    expect(planChatPrefix(state)).not.toContain("olive oil");
  });
});

describe("chatBudget", () => {
  it("uses the plan cap for both limits", () => {
    expect(chatBudget(initialPlanState())).toEqual({
      monthly_limit_cents: 4000,
      plan_cap_cents: 4000,
    });
  });

  it("is null while the cap input is invalid", () => {
    expect(chatBudget(withPlanBudgetInput(initialPlanState(), "12.345"))).toBeNull();
  });
});

describe("ideasFromJob", () => {
  const planned = ["bean_tacos"];

  it("returns known meals that are not yet planned", () => {
    const job = jobWith("planned", [
      { recipe_id: "chickpea_curry", servings: 3 },
      { recipe_id: "egg_fried_rice", servings: 2 },
    ]);
    expect(ideasFromJob(job, planned)).toEqual([
      { recipeId: "chickpea_curry", servings: 3 },
      { recipeId: "egg_fried_rice", servings: 2 },
    ]);
  });

  it("reads needs_revision results too", () => {
    const job = jobWith("needs_revision", [{ recipe_id: "chickpea_curry", servings: 2 }]);
    expect(ideasFromJob(job, planned)).toHaveLength(1);
  });

  it("skips unknown, inherited, planned, and duplicate ids", () => {
    const job = jobWith("planned", [
      { recipe_id: "nope", servings: 2 },
      { recipe_id: "constructor", servings: 2 },
      { recipe_id: "bean_tacos", servings: 2 },
      { recipe_id: "chickpea_curry", servings: 2 },
      { recipe_id: "chickpea_curry", servings: 4 },
    ]);
    expect(ideasFromJob(job, planned)).toEqual([{ recipeId: "chickpea_curry", servings: 2 }]);
  });

  it("returns at most three ideas", () => {
    const job = jobWith("planned", [
      { recipe_id: "chickpea_curry", servings: 2 },
      { recipe_id: "egg_fried_rice", servings: 2 },
      { recipe_id: "lentil_soup", servings: 2 },
      { recipe_id: "vegetable_stir_fry", servings: 2 },
    ]);
    expect(ideasFromJob(job, [])).toHaveLength(3);
  });

  it("gives no ideas for clarification, limit, incomplete, or a missing result", () => {
    const meals = [{ recipe_id: "chickpea_curry", servings: 2 }];
    expect(ideasFromJob(jobWith("clarification", meals), [])).toEqual([]);
    expect(ideasFromJob(jobWith("limit", meals), [])).toEqual([]);
    expect(ideasFromJob(jobWith("incomplete", meals), [])).toEqual([]);
    expect(ideasFromJob({ id: "j", status: "running", result: null, error_code: null }, [])).toEqual([]);
  });
});

describe("retainChatReplies", () => {
  it("bounds metadata to retained assistants plus the current completion", () => {
    let replies: ReadonlyMap<string, ChatReply> = new Map();
    for (let index = 0; index < 40; index += 1) {
      const job = {
        ...jobWith("planned", [{ recipe_id: "chickpea_curry", servings: 2 }]),
        id: `job-${index}`,
      };
      const retained = Array.from(
        { length: Math.min(index, 8) },
        (_, offset) => `job-${index - offset - 1}`,
      );
      replies = retainChatReplies(replies, retained, job, []);
      expect(replies.size).toBeLessThanOrEqual(9);
      expect(replies.get(job.id)?.ideas).toEqual([{ recipeId: "chickpea_curry", servings: 2 }]);
      expect(replies.has(`job-${index - 9}`)).toBe(false);
      const appended = retainChatReplies(replies, [...retained, job.id], job, ["chickpea_curry"]);
      expect(appended).toBe(replies);
    }
    expect(retainChatReplies(replies, [], null, []).size).toBe(0);
  });

  it("keeps failed-turn metadata while the assistant is retained", () => {
    const job = jobWith("incomplete", []);
    const replies = retainChatReplies(new Map(), [], job, []);
    expect(replies.get(job.id)?.answered).toBe(false);
    expect(retainChatReplies(replies, [job.id], null, [])).toBe(replies);
    expect(retainChatReplies(replies, [], null, []).size).toBe(0);
  });
});
