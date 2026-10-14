import { useRef, type JSX } from "react";
import { BUDGET_ERROR, TEXT_ERROR } from "./chatConversationModel";

export type ChatPanelRole = "user" | "assistant";

export type ChatPanelMessage = {
  id: string;
  role: ChatPanelRole;
  content: string;
};

export type ChatPanelProps = {
  messages: ChatPanelMessage[];
  text: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onRetry: () => void;
  onNewConversation: () => void;
  pending: boolean;
  error: string | null;
  configured: boolean;
  configurationPending: boolean;
  hasRequest: boolean;
  disabled: boolean;
  freshSendDisabled?: boolean;
};

const MAX_LENGTH = 4000;
const FAIL = "The chat request failed. Retry checks the same request.";
const TIMEOUT =
  "The chat request is still processing and may continue. Retry checks the same request.";
const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";
const CHECKING = "Checking meal chat configuration.";
const UNAVAILABLE = "Meal chat is unavailable.";
const PENDING = "Your request is in progress.";

function visibleError(error: string): string {
  if (
    error === TIMEOUT ||
    error === HTTP_FALLBACK ||
    error === TEXT_ERROR ||
    error === BUDGET_ERROR
  ) {
    return error;
  }
  return FAIL;
}

export function ChatPanel({
  messages,
  text,
  onChange,
  onSend,
  onRetry,
  onNewConversation,
  pending,
  error,
  configured,
  configurationPending,
  hasRequest,
  disabled,
  freshSendDisabled = false,
}: ChatPanelProps): JSX.Element {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputDisabled = disabled || !configured || configurationPending;
  const formLocked = inputDisabled || pending;
  const retryLocked = !hasRequest || disabled || pending;
  const canSend = !formLocked && !freshSendDisabled && text.trim().length > 0;
  const shownError = error !== null && !pending ? visibleError(error) : null;
  const note = configurationPending ? CHECKING : !configured ? UNAVAILABLE : null;
  return (
    <section className="panel conversation-panel" aria-labelledby="chat-heading">
      <h2 id="chat-heading">Meal chat</h2>
      {note !== null ? <p className="panel-note">{note}</p> : null}
      <p className="conversation-status" role="status" aria-live="polite">
        {pending ? PENDING : shownError ?? ""}
      </p>
      {shownError !== null ? <p className="conversation-error">{shownError}</p> : null}
      {messages.length === 0 ? (
        <div className="conversation-empty">
          <p className="empty-title">No messages yet</p>
          <p>Send a meal request to start a conversation.</p>
        </div>
      ) : (
        <ul aria-label="Messages">
          {messages.map((message) => (
            <li key={message.id}>
              <p>{message.role === "user" ? "You" : "Assistant"}</p>
              <p>{message.content}</p>
            </li>
          ))}
        </ul>
      )}
      <div className="conversation-composer">
        <form
          className="budget-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSend) {
              inputRef.current?.focus();
              onSend();
            }
          }}
        >
          <label htmlFor="chat-message">Message</label>
          <textarea
            id="chat-message"
            ref={inputRef}
            maxLength={MAX_LENGTH}
            value={text}
            disabled={inputDisabled}
            readOnly={pending}
            rows={6}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
          <button type="submit" className="conversation-action" disabled={!canSend}>
            Send
          </button>
        </form>
        <button type="button" className="conversation-action" disabled={retryLocked} onClick={onRetry}>
          Retry the same request
        </button>
        <button type="button" disabled={disabled || pending} onClick={onNewConversation}>
          Start a new conversation
        </button>
      </div>
    </section>
  );
}
