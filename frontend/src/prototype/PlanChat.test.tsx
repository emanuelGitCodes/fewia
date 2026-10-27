/** @vitest-environment jsdom */

import type { ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_MESSAGE_LENGTH } from "../chatConversationModel";
import type { ChatJob, ChatJobCreate, ChatResult } from "../chatTypes";
import { useChatJob } from "../useChatJob";
import { useProviderCapabilities } from "../useProviderCapabilities";
import { FAILED_LINE, OFF_LINE, PlanChat } from "./PlanChat";
import { planChatPrefix } from "./planChatModel";
import { initialPlanState, withPlanBudgetInput, type PlanState } from "./planModel";

vi.mock("../useChatJob", () => ({ useChatJob: vi.fn() }));
vi.mock("../useProviderCapabilities", () => ({ useProviderCapabilities: vi.fn() }));

type JobMocks = {
  job: ChatJob | null;
  error: string | null;
  pending: boolean;
  submit: ReturnType<typeof vi.fn<(body: ChatJobCreate) => Promise<void>>>;
  clear: ReturnType<typeof vi.fn<() => void>>;
};

let jobState: JobMocks;

function chatJob(
  id: string,
  status: ChatResult["status"],
  answer: string,
  meals: Array<{ recipe_id: string; servings: number }> = [],
): ChatJob {
  const result = {
    status,
    answer,
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
  return { id, status: "succeeded", result, error_code: null };
}

function setProviders(configured: boolean, failed = false): void {
  vi.mocked(useProviderCapabilities).mockReturnValue({
    capabilities: failed
      ? null
      : {
          chat_configured: configured,
          plaid_configured: false,
          instacart_configured: false,
          spending_source: "manual",
        },
    pending: false,
    error: failed ? "unavailable" : null,
    retry: vi.fn(),
  });
}

function mount(
  state: PlanState = initialPlanState(),
  extra: Partial<ComponentProps<typeof PlanChat>> = {},
) {
  const onToggleIdea = vi.fn();
  const view = render(<PlanChat state={state} onToggleIdea={onToggleIdea} {...extra} />);
  return { ...view, onToggleIdea };
}

function box(): HTMLTextAreaElement {
  return screen.getByLabelText("Ask for a meal") as HTMLTextAreaElement;
}

function type(text: string): void {
  fireEvent.change(box(), { target: { value: text } });
}

async function submitText(text: string): Promise<void> {
  type(text);
  await act(async () => {
    fireEvent.keyDown(box(), { key: "Enter" });
  });
}

function submitted(index: number): ChatJobCreate {
  const body = jobState.submit.mock.calls[index]?.[0];
  if (body === undefined) {
    throw new Error("missing submit body");
  }
  return body;
}

beforeEach(() => {
  jobState = {
    job: null,
    error: null,
    pending: false,
    submit: vi.fn(async (_body: ChatJobCreate) => undefined),
    clear: vi.fn((): void => {
      jobState.job = null;
      jobState.error = null;
      jobState.pending = false;
    }),
  };
  vi.mocked(useChatJob).mockImplementation(() => ({
    job: jobState.job,
    error: jobState.error,
    pending: jobState.pending,
    submit: jobState.submit,
    clear: jobState.clear,
  }));
  setProviders(true);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PlanChat", () => {
  it("is an aside labelled by its Ask FEWIA heading with one status region", () => {
    mount();
    const aside = screen.getByRole("complementary", { name: "Ask FEWIA" });
    expect(aside.querySelector("h2")?.textContent).toBe("Ask FEWIA");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(
      screen.getByText("Replies come from a real model call. Prices are sample estimates."),
    ).toBeTruthy();
  });

  it("shows one line and no composer when chat is not configured", () => {
    setProviders(false);
    mount();
    expect(screen.getByText(OFF_LINE)).toBeTruthy();
    expect(screen.queryByLabelText("Ask for a meal")).toBeNull();
    expect(screen.queryByRole("button", { name: "New chat" })).toBeNull();
  });

  it("shows the off line when the capabilities request failed", () => {
    setProviders(false, true);
    mount();
    expect(screen.getByText(OFF_LINE)).toBeTruthy();
    expect(screen.queryByLabelText("Ask for a meal")).toBeNull();
  });

  it("shows the empty state with three starters that fill the textarea", () => {
    mount();
    expect(screen.getByText("Ask for a meal idea")).toBeTruthy();
    const names = ["Cheap vegetarian dinner for 2", "More protein for under $10", "Use what is in my pantry"];
    for (const name of names) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("button", { name: names[1] }));
    expect(box().value).toBe(names[1]);
    expect(document.activeElement).toBe(box());
  });

  it("shows Queued with a read-only textarea and a Sending button", () => {
    jobState.pending = true;
    jobState.job = { id: "job-1", status: "queued", result: null, error_code: null };
    mount();
    expect(screen.getByRole("status").textContent).toBe("Queued");
    expect(box().readOnly).toBe(true);
    const send = screen.getByRole("button", { name: "Sending" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    expect(screen.queryByText("Ask for a meal idea")).toBeNull();
  });

  it("shows the running text", () => {
    jobState.pending = true;
    jobState.job = { id: "job-1", status: "running", result: null, error_code: null };
    mount();
    expect(screen.getByRole("status").textContent).toBe("Running. FEWIA is finding meals.");
  });

  it("sends on Enter with the plan prefix and keeps the typed text in the transcript", async () => {
    const state = initialPlanState();
    mount(state);
    box().focus();
    await submitText("  Cheap dinner  ");
    expect(jobState.submit).toHaveBeenCalledTimes(1);
    expect(submitted(0).message).toBe(`${planChatPrefix(state)}Cheap dinner`);
    expect(submitted(0).monthly_limit_cents).toBe(4000);
    expect(submitted(0).plan_cap_cents).toBe(4000);
    const log = screen.getByRole("list", { name: "Messages" });
    expect(log.tagName).toBe("OL");
    expect(log.textContent).toContain("Cheap dinner");
    expect(log.textContent).not.toContain("My current plan");
    expect(document.activeElement).toBe(box());
  });

  it("adds a line on Shift+Enter without sending", async () => {
    mount();
    type("Cheap dinner");
    let notPrevented = false;
    await act(async () => {
      notPrevented = fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });
    });
    // fireEvent returns false when a handler called preventDefault.
    expect(notPrevented).toBe(true);
    expect(jobState.submit).not.toHaveBeenCalled();
  });

  it("limits the textarea by the room left after the plan prefix", () => {
    const state = initialPlanState();
    mount(state);
    expect(box().maxLength).toBe(MAX_MESSAGE_LENGTH - planChatPrefix(state).length);
    expect(box().maxLength).toBeLessThan(MAX_MESSAGE_LENGTH);
  });

  it("does not send an empty message", async () => {
    mount();
    await act(async () => {
      fireEvent.keyDown(box(), { key: "Enter" });
    });
    expect(jobState.submit).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("blocks sending and says why while the plan cap is invalid", () => {
    mount(withPlanBudgetInput(initialPlanState(), "12.345"));
    type("Cheap dinner");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Fix the plan cap to send a message.")).toBeTruthy();
  });

  it("shows an idea card for a planned reply and adds it in one tap", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "planned", "Chickpea curry fits.", [
        { recipe_id: "chickpea_curry", servings: 2 },
        { recipe_id: "bean_tacos", servings: 2 },
        { recipe_id: "nope", servings: 2 },
      ]);
    });
    const { onToggleIdea } = mount();
    await submitText("Something with chickpeas");
    expect(screen.getByText("Chickpea curry fits.")).toBeTruthy();
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText("Price changes are sample estimates.")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("FEWIA replied with 1 meal idea.");
    fireEvent.click(screen.getByRole("button", { name: /^Add Chickpea curry, 2 servings/ }));
    expect(onToggleIdea).toHaveBeenCalledWith("chickpea_curry", 2, false);
  });

  it("shows only the answer text for a clarification", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "clarification", "Which meals should I plan?");
    });
    mount();
    await submitText("Plan dinner");
    expect(screen.getByText("Which meals should I plan?")).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
    expect(screen.queryByText("Price changes are sample estimates.")).toBeNull();
  });

  it("shows the failure line and Retry for a failed request, and retries the same body", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = { id: "job-1", status: "failed", result: null, error_code: "tool" };
      jobState.error = "The chat request failed. Retry checks the same request.";
    });
    mount();
    await submitText("Cheap dinner");
    expect(screen.getByRole("status").textContent).toBe(FAILED_LINE);
    expect(screen.queryByRole("button", { name: "Ask again" })).toBeNull();
    const retry = screen.getByRole("button", { name: "Retry" });
    retry.focus();
    await act(async () => {
      fireEvent.click(retry);
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(1)).toEqual(submitted(0));
    expect(document.activeElement).toBe(box());
  });

  it.each(["limit", "incomplete"] as const)(
    "shows the failure line and Ask again for a %s result and hides its answer",
    async (status) => {
      jobState.submit.mockImplementation(async () => {
        jobState.job = chatJob("job-1", status, "Internal turn limit text.");
      });
      mount();
      await submitText("Cheap dinner");
      expect(screen.getByRole("status").textContent).toBe(FAILED_LINE);
      expect(screen.queryByText("Internal turn limit text.")).toBeNull();
      expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    },
  );

  it("sends the last user text as a fresh request on Ask again and focuses the textarea", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "limit", "Internal turn limit text.");
    });
    mount();
    await submitText("Cheap dinner");
    expect(jobState.clear).toHaveBeenCalledTimes(1);
    const again = screen.getByRole("button", { name: "Ask again" });
    again.focus();
    await act(async () => {
      fireEvent.click(again);
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(1).message).toBe(submitted(0).message);
    expect(submitted(1).message.endsWith("Cheap dinner")).toBe(true);
    // A fresh request clears the finished job; retry() would not.
    expect(jobState.clear).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(box());
  });

  it("hides Ask again while the draft is not empty and keeps the failure line", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "limit", "Internal turn limit text.");
    });
    mount();
    await submitText("Cheap dinner");
    expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
    type("Something else");
    expect(screen.queryByRole("button", { name: "Ask again" })).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(FAILED_LINE);
    expect(box().value).toBe("Something else");
    type("");
    expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
  });

  it.each(["limit", "incomplete"] as const)(
    "does not tell the shell about a %s result",
    async (status) => {
      jobState.submit.mockImplementation(async () => {
        jobState.job = chatJob("job-1", status, "Internal turn limit text.");
      });
      const onReply = vi.fn();
      mount(initialPlanState(), { onReply });
      await submitText("Cheap dinner");
      expect(onReply).not.toHaveBeenCalled();
    },
  );

  it("shows the Hide chat button only when a sheet can be closed", () => {
    const onHide = vi.fn();
    const view = mount();
    expect(screen.queryByRole("button", { name: "Hide chat" })).toBeNull();
    view.unmount();
    mount(initialPlanState(), { onHide });
    fireEvent.click(screen.getByRole("button", { name: "Hide chat" }));
    expect(onHide).toHaveBeenCalledTimes(1);
  });

  it("focuses the textarea when the sheet opens and takes the given id", () => {
    const state = initialPlanState();
    const view = render(<PlanChat state={state} onToggleIdea={vi.fn()} id="ask-panel" open={false} />);
    expect(document.activeElement).not.toBe(box());
    view.rerender(<PlanChat state={state} onToggleIdea={vi.fn()} id="ask-panel" open />);
    expect(document.activeElement).toBe(box());
    expect(screen.getByRole("complementary", { name: "Ask FEWIA" }).id).toBe("ask-panel");
  });

  it("tells the shell once when a reply arrives", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "clarification", "Which meals should I plan?");
    });
    const onReply = vi.fn();
    mount(initialPlanState(), { onReply });
    expect(onReply).not.toHaveBeenCalled();
    await submitText("Plan dinner");
    expect(onReply).toHaveBeenCalledTimes(1);
  });

  it("clears the transcript on New chat", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "clarification", "Which meals should I plan?");
    });
    mount();
    await submitText("Plan dinner");
    expect(screen.getByRole("list", { name: "Messages" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByRole("list", { name: "Messages" })).toBeNull();
    expect(screen.getByText("Ask for a meal idea")).toBeTruthy();
    expect(box().value).toBe("");
  });
});
