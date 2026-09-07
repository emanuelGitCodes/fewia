/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { describe, expect, it, vi } from "vitest";
import { BUDGET_ERROR, TEXT_ERROR } from "./chatConversationModel";
import { ChatPanel, type ChatPanelMessage, type ChatPanelProps } from "./ChatPanel";

const TIMEOUT =
  "The chat request is still processing and may continue. Retry checks the same request.";
const FAIL = "The chat request failed. Retry checks the same request.";
const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";
const SECRET = "error_code: ACCESS_KEY tool_args";

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) {
    throw new Error(`missing button ${name}`);
  }
  return match;
}

function submit(root: ReactTestInstance): { preventDefault: ReturnType<typeof vi.fn<() => void>> } {
  const event = { preventDefault: vi.fn<() => void>() };
  act(() => {
    (root.findByType("form").props.onSubmit as (current: typeof event) => void)(event);
  });
  return event;
}

function mount(
  props: Partial<ChatPanelProps> = {},
): {
  renderer: ReactTestRenderer;
  onChange: ReturnType<typeof vi.fn<(value: string) => void>>;
  onSend: ReturnType<typeof vi.fn<() => void>>;
  onRetry: ReturnType<typeof vi.fn<() => void>>;
  onNewConversation: ReturnType<typeof vi.fn<() => void>>;
} {
  const onChange = vi.fn<(value: string) => void>();
  const onSend = vi.fn<() => void>();
  const onRetry = vi.fn<() => void>();
  const onNewConversation = vi.fn<() => void>();
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(
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
      }),
    );
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return { renderer, onChange, onSend, onRetry, onNewConversation };
}

const markup = "<script>alert(1)</script><img src=x onerror=alert(1)>";
const messages: ChatPanelMessage[] = [
  { id: "u1", role: "user", content: markup },
  { id: "a1", role: "assistant", content: `${markup}\nUse 1 to 3 meals and 1 to 8 servings.` },
];

describe("ChatPanel", () => {
  it("enables the labeled form and submits through the form", () => {
    const { renderer, onSend, onChange } = mount({ text: "Bean tacos for two" });
    const textarea = renderer.root.findByType("textarea");
    expect(renderer.root.findByProps({ htmlFor: "chat-message" })).toBeTruthy();
    expect(textarea.props.id).toBe("chat-message");
    expect(textarea.props.disabled).toBe(false);
    expect(textarea.props.onKeyDown).toBeUndefined();
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(false);
    act(() => {
      (textarea.props.onChange as (event: { target: { value: string } }) => void)({
        target: { value: "Lentil soup" },
      });
    });
    expect(onChange).toHaveBeenCalledWith("Lentil soup");
    const event = submit(renderer.root);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("disables the form when disabled, unconfigured, or configurationPending", () => {
    const blocked = mount({ text: "Bean tacos for two", disabled: true });
    expect(blocked.renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(buttonNamed(blocked.renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(blocked.renderer.root, "Retry the same request").props.disabled).toBe(true);
    expect(buttonNamed(blocked.renderer.root, "Start a new conversation").props.disabled).toBe(true);
    submit(blocked.renderer.root);
    expect(blocked.onSend).not.toHaveBeenCalled();
    blocked.renderer.unmount();
    const waiting = mount({ text: "Bean tacos for two", configurationPending: true });
    expect(waiting.renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(childText(waiting.renderer.root)).toContain("Checking meal chat configuration.");
    expect(childText(waiting.renderer.root)).not.toContain("Meal chat is unavailable.");
    waiting.renderer.unmount();
    const unconfigured = mount({ text: "Bean tacos for two", configured: false });
    expect(unconfigured.renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(buttonNamed(unconfigured.renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(unconfigured.renderer.root, "Start a new conversation").props.disabled).toBe(false);
    expect(childText(unconfigured.renderer.root)).toContain("Meal chat is unavailable.");
    expect(childText(unconfigured.renderer.root)).not.toContain("Checking meal chat configuration.");
    unconfigured.renderer.unmount();
  });

  it("disables the pending form and exposes live progress status", () => {
    const { renderer, onSend } = mount({ text: "Bean tacos for two", pending: true });
    expect(renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Retry the same request").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Start a new conversation").props.disabled).toBe(true);
    const live = renderer.root.findAll(
      (node) => node.props["aria-live"] === "polite" && node.props.role === "status",
    );
    expect(live).toHaveLength(1);
    const status = live[0];
    if (status === undefined) {
      throw new Error("missing live status");
    }
    expect(childText(status)).toBe("Your request is in progress.");
    expect(childText(renderer.root)).not.toContain("queue");
    expect(childText(renderer.root)).not.toContain("job");
    submit(renderer.root);
    expect(onSend).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("caps the textarea at 4000 characters", () => {
    const { renderer } = mount({ text: "a".repeat(4000) });
    expect(renderer.root.findByType("textarea").props.maxLength).toBe(4000);
    renderer.unmount();
  });

  it("renders escaped message text and product role labels", () => {
    const { renderer } = mount({ messages });
    const text = childText(renderer.root);
    expect(text).toContain("You");
    expect(text).toContain("Assistant");
    expect(text).toContain(markup);
    expect(text).toContain("Use 1 to 3 meals and 1 to 8 servings.");
    expect(renderer.root.findAll((node) => node.props.dangerouslySetInnerHTML !== undefined)).toHaveLength(0);
    expect(renderer.root.findAllByType("script")).toHaveLength(0);
    expect(renderer.root.findAllByType("img")).toHaveLength(0);
    expect(renderer.root.findAllByProps({ className: "conversation-empty" })).toHaveLength(0);
    renderer.unmount();
  });

  it("keeps retry and new conversation as separate actions", () => {
    const { renderer, onRetry, onSend, onNewConversation } = mount({
      hasRequest: true,
      error: SECRET,
    });
    expect(childText(renderer.root)).toContain(FAIL);
    expect(childText(renderer.root)).not.toContain("error_code");
    expect(childText(renderer.root)).not.toContain("ACCESS_KEY");
    expect(childText(renderer.root)).not.toContain("tool_args");
    act(() => {
      (buttonNamed(renderer.root, "Retry the same request").props.onClick as () => void)();
    });
    act(() => {
      (buttonNamed(renderer.root, "Start a new conversation").props.onClick as () => void)();
    });
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onNewConversation).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("shows timeout may-continue wording and hides unknown secret text", () => {
    const timeout = mount({ hasRequest: true, error: TIMEOUT });
    expect(childText(timeout.renderer.root)).toContain(TIMEOUT);
    expect(childText(timeout.renderer.root)).not.toContain("The chat request failed.");
    timeout.renderer.unmount();
    const secret = mount({ hasRequest: true, error: SECRET });
    expect(childText(secret.renderer.root)).toContain(FAIL);
    expect(childText(secret.renderer.root)).not.toContain("error_code");
    expect(childText(secret.renderer.root)).not.toContain("ACCESS_KEY");
    expect(childText(secret.renderer.root)).not.toContain("tool_args");
    secret.renderer.unmount();
  });

  it("shows controller text and budget validation errors and hides unknown secret text", () => {
    const text = mount({ hasRequest: true, error: TEXT_ERROR });
    expect(childText(text.renderer.root)).toContain(TEXT_ERROR);
    expect(childText(text.renderer.root)).not.toContain(FAIL);
    text.renderer.unmount();
    const budget = mount({ hasRequest: true, error: BUDGET_ERROR });
    expect(childText(budget.renderer.root)).toContain(BUDGET_ERROR);
    expect(BUDGET_ERROR).toContain("monthly limit");
    expect(BUDGET_ERROR).toContain("plan cap");
    expect(childText(budget.renderer.root)).not.toContain(FAIL);
    budget.renderer.unmount();
    const secret = mount({ hasRequest: true, error: SECRET });
    expect(childText(secret.renderer.root)).toContain(FAIL);
    expect(childText(secret.renderer.root)).not.toContain(TEXT_ERROR);
    expect(childText(secret.renderer.root)).not.toContain(BUDGET_ERROR);
    expect(childText(secret.renderer.root)).not.toContain("error_code");
    expect(childText(secret.renderer.root)).not.toContain("ACCESS_KEY");
    expect(childText(secret.renderer.root)).not.toContain("tool_args");
    secret.renderer.unmount();
  });

  it("shows the http fallback wording and still hides unknown secret text", () => {
    const fallback = mount({ hasRequest: true, error: HTTP_FALLBACK });
    expect(childText(fallback.renderer.root)).toContain(HTTP_FALLBACK);
    expect(childText(fallback.renderer.root)).not.toContain(FAIL);
    fallback.renderer.unmount();
    const secret = mount({ hasRequest: true, error: SECRET });
    expect(childText(secret.renderer.root)).toContain(FAIL);
    expect(childText(secret.renderer.root)).not.toContain(HTTP_FALLBACK);
    expect(childText(secret.renderer.root)).not.toContain("error_code");
    expect(childText(secret.renderer.root)).not.toContain("ACCESS_KEY");
    expect(childText(secret.renderer.root)).not.toContain("tool_args");
    secret.renderer.unmount();
  });

  it("disables retry with no request and enables retry when a request exists", () => {
    const empty = mount({ text: "Bean tacos for two", hasRequest: false });
    expect(buttonNamed(empty.renderer.root, "Retry the same request").props.disabled).toBe(true);
    empty.renderer.unmount();
    const unconfigured = mount({
      text: "Bean tacos for two",
      hasRequest: true,
      configured: false,
    });
    expect(buttonNamed(unconfigured.renderer.root, "Retry the same request").props.disabled).toBe(false);
    expect(unconfigured.renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(buttonNamed(unconfigured.renderer.root, "Send").props.disabled).toBe(true);
    unconfigured.renderer.unmount();
    const waiting = mount({
      text: "Bean tacos for two",
      hasRequest: true,
      configurationPending: true,
    });
    expect(buttonNamed(waiting.renderer.root, "Retry the same request").props.disabled).toBe(false);
    expect(waiting.renderer.root.findByType("textarea").props.disabled).toBe(true);
    expect(buttonNamed(waiting.renderer.root, "Send").props.disabled).toBe(true);
    waiting.renderer.unmount();
  });

  it("shows a clear empty state and does not treat configured as live verified", () => {
    const { renderer } = mount({ configured: true, text: "" });
    expect(childText(renderer.root)).toContain("No messages yet");
    expect(childText(renderer.root)).toContain("Send a meal request to start a conversation.");
    expect(buttonNamed(renderer.root, "Send").props.disabled).toBe(true);
    expect(buttonNamed(renderer.root, "Retry the same request").props.disabled).toBe(true);
    expect(childText(renderer.root)).not.toContain("verified");
    expect(childText(renderer.root)).not.toContain("Bedrock");
    expect(childText(renderer.root)).not.toContain("secret");
    renderer.unmount();
  });
});
