/** @vitest-environment jsdom */

import { createElement } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { BUDGET_ERROR, TEXT_ERROR } from "./chatConversationModel";
import { ChatPanel, type ChatPanelMessage, type ChatPanelProps } from "./ChatPanel";

const TIMEOUT =
  "The chat request is still processing and may continue. Retry checks the same request.";
const FAIL = "The chat request failed. Retry checks the same request.";
const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";
const SECRET = "error_code: ACCESS_KEY tool_args";

function renderedText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(root: HTMLElement, name: string): HTMLButtonElement {
  return within(root).getByRole("button", { name, exact: true }) as HTMLButtonElement;
}

function submit(root: HTMLElement): { preventDefault: MockInstance<() => void> } {
  const form = within(root).getByRole("textbox").closest("form");
  if (form === null) {
    throw new Error("missing chat form");
  }
  const event = new Event("submit", { bubbles: true, cancelable: true });
  const preventDefault = vi.spyOn(event, "preventDefault");
  fireEvent(form, event);
  return { preventDefault };
}

function messageInput(root: HTMLElement): HTMLTextAreaElement {
  return within(root).getByRole("textbox") as HTMLTextAreaElement;
}

function mount(
  props: Partial<ChatPanelProps> = {},
): {
  rendered: RenderResult;
  onChange: ReturnType<typeof vi.fn<(value: string) => void>>;
  onSend: ReturnType<typeof vi.fn<() => void>>;
  onRetry: ReturnType<typeof vi.fn<() => void>>;
  onNewConversation: ReturnType<typeof vi.fn<() => void>>;
} {
  const onChange = vi.fn<(value: string) => void>();
  const onSend = vi.fn<() => void>();
  const onRetry = vi.fn<() => void>();
  const onNewConversation = vi.fn<() => void>();
  const rendered = render(
    createElement(ChatPanel, {
      messages: props.messages ?? [],
      text: props.text ?? "",
      onChange: props.onChange ?? onChange,
      onSend: props.onSend ?? onSend,
      onRetry: props.onRetry ?? onRetry,
      onNewConversation: props.onNewConversation ?? onNewConversation,
      pending: props.pending ?? false,
      error: props.error ?? null,
      configured: props.configured ?? true,
      configurationPending: props.configurationPending ?? false,
      hasRequest: props.hasRequest ?? false,
      disabled: props.disabled ?? false,
      freshSendDisabled: props.freshSendDisabled ?? false,
    }),
  );
  return { rendered, onChange, onSend, onRetry, onNewConversation };
}

const markup = "<script>alert(1)</script><img src=x onerror=alert(1)>";
const messages: ChatPanelMessage[] = [
  { id: "u1", role: "user", content: markup },
  { id: "a1", role: "assistant", content: `${markup}\nUse 1 to 3 meals and 1 to 8 servings.` },
];

afterEach(cleanup);

describe("ChatPanel", () => {
  it("enables the labeled form and submits through the form", () => {
    const { rendered, onSend, onChange } = mount({ text: "Bean tacos for two" });
    const textarea = messageInput(rendered.container);
    expect(
      Array.from(textarea.labels ?? []).some((label) => label.htmlFor === "chat-message"),
    ).toBe(true);
    expect(textarea.id).toBe("chat-message");
    expect(textarea.disabled).toBe(false);
    expect(fireEvent.keyDown(textarea, { key: "Enter", code: "Enter" })).toBe(true);
    expect(onSend).not.toHaveBeenCalled();
    expect(buttonNamed(rendered.container, "Send").disabled).toBe(false);
    fireEvent.change(textarea, { target: { value: "Lentil soup" } });
    expect(onChange).toHaveBeenCalledWith("Lentil soup");
    const event = submit(rendered.container);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledTimes(1);
    rendered.unmount();
  });

  it("disables the form when disabled, unconfigured, or configurationPending", () => {
    const blocked = mount({ text: "Bean tacos for two", disabled: true });
    expect(messageInput(blocked.rendered.container).disabled).toBe(true);
    expect(buttonNamed(blocked.rendered.container, "Send").disabled).toBe(true);
    expect(buttonNamed(blocked.rendered.container, "Retry the same request").disabled).toBe(true);
    expect(buttonNamed(blocked.rendered.container, "Start a new conversation").disabled).toBe(true);
    submit(blocked.rendered.container);
    expect(blocked.onSend).not.toHaveBeenCalled();
    blocked.rendered.unmount();
    const waiting = mount({ text: "Bean tacos for two", configurationPending: true });
    expect(messageInput(waiting.rendered.container).disabled).toBe(true);
    expect(renderedText(waiting.rendered.container)).toContain("Checking meal chat configuration.");
    expect(renderedText(waiting.rendered.container)).not.toContain("Meal chat is unavailable.");
    waiting.rendered.unmount();
    const unconfigured = mount({ text: "Bean tacos for two", configured: false });
    expect(messageInput(unconfigured.rendered.container).disabled).toBe(true);
    expect(buttonNamed(unconfigured.rendered.container, "Send").disabled).toBe(true);
    expect(buttonNamed(unconfigured.rendered.container, "Start a new conversation").disabled).toBe(false);
    expect(renderedText(unconfigured.rendered.container)).toContain("Meal chat is unavailable.");
    expect(renderedText(unconfigured.rendered.container)).not.toContain("Checking meal chat configuration.");
    unconfigured.rendered.unmount();
  });

  it("disables the pending form and exposes live progress status", () => {
    const { rendered, onSend } = mount({ text: "Bean tacos for two", pending: true });
    expect(messageInput(rendered.container).disabled).toBe(true);
    expect(buttonNamed(rendered.container, "Send").disabled).toBe(true);
    expect(buttonNamed(rendered.container, "Retry the same request").disabled).toBe(true);
    expect(buttonNamed(rendered.container, "Start a new conversation").disabled).toBe(true);
    const live = within(rendered.container).queryAllByRole("status").filter(
      (node) => node.getAttribute("aria-live") === "polite",
    );
    expect(live).toHaveLength(1);
    const status = live[0];
    if (status === undefined) {
      throw new Error("missing live status");
    }
    expect(renderedText(status)).toBe("Your request is in progress.");
    expect(renderedText(rendered.container)).not.toContain("queue");
    expect(renderedText(rendered.container)).not.toContain("job");
    submit(rendered.container);
    expect(onSend).not.toHaveBeenCalled();
    rendered.unmount();
  });

  it("caps the textarea at 4000 characters", () => {
    const { rendered } = mount({ text: "a".repeat(4000) });
    expect(messageInput(rendered.container).maxLength).toBe(4000);
    rendered.unmount();
  });

  it("renders escaped message text and product role labels", () => {
    const { rendered } = mount({ messages });
    const text = renderedText(rendered.container);
    expect(text).toContain("You");
    expect(text).toContain("Assistant");
    expect(text).toContain(markup);
    expect(text).toContain("Use 1 to 3 meals and 1 to 8 servings.");
    const escaped = document.createElement("span");
    escaped.textContent = markup;
    expect(screen.getByText(markup).innerHTML).toBe(escaped.innerHTML);
    expect(rendered.container.getElementsByTagName("script")).toHaveLength(0);
    expect(rendered.container.getElementsByTagName("img")).toHaveLength(0);
    expect(within(rendered.container).queryAllByText("No messages yet")).toHaveLength(0);
    rendered.unmount();
  });

  it("keeps retry and new conversation as separate actions", () => {
    const { rendered, onRetry, onSend, onNewConversation } = mount({
      hasRequest: true,
      error: SECRET,
    });
    expect(renderedText(rendered.container)).toContain(FAIL);
    expect(renderedText(rendered.container)).not.toContain("error_code");
    expect(renderedText(rendered.container)).not.toContain("ACCESS_KEY");
    expect(renderedText(rendered.container)).not.toContain("tool_args");
    fireEvent.click(buttonNamed(rendered.container, "Retry the same request"));
    fireEvent.click(buttonNamed(rendered.container, "Start a new conversation"));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onNewConversation).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    rendered.unmount();
  });

  it("shows timeout may-continue wording and hides unknown secret text", () => {
    const timeout = mount({ hasRequest: true, error: TIMEOUT });
    expect(renderedText(timeout.rendered.container)).toContain(TIMEOUT);
    expect(renderedText(timeout.rendered.container)).not.toContain("The chat request failed.");
    timeout.rendered.unmount();
    const secret = mount({ hasRequest: true, error: SECRET });
    expect(renderedText(secret.rendered.container)).toContain(FAIL);
    expect(renderedText(secret.rendered.container)).not.toContain("error_code");
    expect(renderedText(secret.rendered.container)).not.toContain("ACCESS_KEY");
    expect(renderedText(secret.rendered.container)).not.toContain("tool_args");
    secret.rendered.unmount();
  });

  it("shows controller text and budget validation errors and hides unknown secret text", () => {
    const text = mount({ hasRequest: true, error: TEXT_ERROR });
    expect(renderedText(text.rendered.container)).toContain(TEXT_ERROR);
    expect(renderedText(text.rendered.container)).not.toContain(FAIL);
    text.rendered.unmount();
    const budget = mount({ hasRequest: true, error: BUDGET_ERROR });
    expect(renderedText(budget.rendered.container)).toContain(BUDGET_ERROR);
    expect(BUDGET_ERROR).toContain("monthly limit");
    expect(BUDGET_ERROR).toContain("plan cap");
    expect(renderedText(budget.rendered.container)).not.toContain(FAIL);
    budget.rendered.unmount();
    const secret = mount({ hasRequest: true, error: SECRET });
    expect(renderedText(secret.rendered.container)).toContain(FAIL);
    expect(renderedText(secret.rendered.container)).not.toContain(TEXT_ERROR);
    expect(renderedText(secret.rendered.container)).not.toContain(BUDGET_ERROR);
    expect(renderedText(secret.rendered.container)).not.toContain("error_code");
    expect(renderedText(secret.rendered.container)).not.toContain("ACCESS_KEY");
    expect(renderedText(secret.rendered.container)).not.toContain("tool_args");
    secret.rendered.unmount();
  });

  it("shows the http fallback wording and still hides unknown secret text", () => {
    const fallback = mount({ hasRequest: true, error: HTTP_FALLBACK });
    expect(renderedText(fallback.rendered.container)).toContain(HTTP_FALLBACK);
    expect(renderedText(fallback.rendered.container)).not.toContain(FAIL);
    fallback.rendered.unmount();
    const secret = mount({ hasRequest: true, error: SECRET });
    expect(renderedText(secret.rendered.container)).toContain(FAIL);
    expect(renderedText(secret.rendered.container)).not.toContain(HTTP_FALLBACK);
    expect(renderedText(secret.rendered.container)).not.toContain("error_code");
    expect(renderedText(secret.rendered.container)).not.toContain("ACCESS_KEY");
    expect(renderedText(secret.rendered.container)).not.toContain("tool_args");
    secret.rendered.unmount();
  });

  it("disables retry with no request and enables retry when a request exists", () => {
    const empty = mount({ text: "Bean tacos for two", hasRequest: false });
    expect(buttonNamed(empty.rendered.container, "Retry the same request").disabled).toBe(true);
    empty.rendered.unmount();
    const unconfigured = mount({
      text: "Bean tacos for two",
      hasRequest: true,
      configured: false,
    });
    expect(buttonNamed(unconfigured.rendered.container, "Retry the same request").disabled).toBe(false);
    expect(messageInput(unconfigured.rendered.container).disabled).toBe(true);
    expect(buttonNamed(unconfigured.rendered.container, "Send").disabled).toBe(true);
    unconfigured.rendered.unmount();
    const waiting = mount({
      text: "Bean tacos for two",
      hasRequest: true,
      configurationPending: true,
    });
    expect(buttonNamed(waiting.rendered.container, "Retry the same request").disabled).toBe(false);
    expect(messageInput(waiting.rendered.container).disabled).toBe(true);
    expect(buttonNamed(waiting.rendered.container, "Send").disabled).toBe(true);
    waiting.rendered.unmount();
  });

  it("disables a fresh send and keeps retry, reset, and text entry", () => {
    const { rendered, onSend, onRetry, onNewConversation } = mount({
      text: "Bean tacos for two",
      hasRequest: true,
      freshSendDisabled: true,
    });
    expect(messageInput(rendered.container).disabled).toBe(false);
    expect(buttonNamed(rendered.container, "Send").disabled).toBe(true);
    expect(buttonNamed(rendered.container, "Retry the same request").disabled).toBe(false);
    expect(buttonNamed(rendered.container, "Start a new conversation").disabled).toBe(false);
    submit(rendered.container);
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.click(buttonNamed(rendered.container, "Retry the same request"));
    fireEvent.click(buttonNamed(rendered.container, "Start a new conversation"));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onNewConversation).toHaveBeenCalledTimes(1);
    rendered.unmount();
  });

  it("shows a clear empty state and does not treat configured as live verified", () => {
    const { rendered } = mount({ configured: true, text: "" });
    expect(renderedText(rendered.container)).toContain("No messages yet");
    expect(renderedText(rendered.container)).toContain("Send a meal request to start a conversation.");
    expect(buttonNamed(rendered.container, "Send").disabled).toBe(true);
    expect(buttonNamed(rendered.container, "Retry the same request").disabled).toBe(true);
    expect(renderedText(rendered.container)).not.toContain("verified");
    expect(renderedText(rendered.container)).not.toContain("Bedrock");
    expect(renderedText(rendered.container)).not.toContain("secret");
    rendered.unmount();
  });
});
