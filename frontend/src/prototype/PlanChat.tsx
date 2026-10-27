import { useCallback, useEffect, useId, useRef, useState, type JSX, type KeyboardEvent } from "react";
import { BUDGET_ERROR, MAX_MESSAGE_LENGTH, TEXT_ERROR } from "../chatConversationModel";
import { useChatConversation } from "../useChatConversation";
import { useProviderCapabilities } from "../useProviderCapabilities";
import { ChatIdeaCard } from "./ChatIdeaCard";
import { chatBudget, ideasFromJob, planChatPrefix, type ChatIdea } from "./planChatModel";
import type { PlanState } from "./planModel";

export const OFF_LINE = "Ask FEWIA is off. The plan still works.";
export const FAILED_LINE = "FEWIA did not answer. Your plan did not change.";
const STARTERS = [
  "Cheap vegetarian dinner for 2",
  "More protein for under $10",
  "Use what is in my pantry",
] as const;

type Reply = { ideas: ChatIdea[]; answered: boolean };

function replyLine(count: number): string {
  if (count === 0) {
    return "FEWIA replied.";
  }
  return `FEWIA replied with ${String(count)} meal ${count === 1 ? "idea" : "ideas"}.`;
}

export function PlanChat(props: {
  state: PlanState;
  onToggleIdea: (recipeId: string, servings: number, inPlan: boolean) => void;
  id?: string;
  // True while the panel is an open sheet; opening moves focus into it.
  open?: boolean;
  onHide?: () => void;
  onReply?: () => void;
}): JSX.Element {
  const { state, onReply } = props;
  const uid = useId();
  const headingId = `${uid}-heading`;
  const inputId = `${uid}-input`;
  const providers = useProviderCapabilities();
  const composeMessage = useCallback((text: string) => planChatPrefix(state) + text, [state]);
  const budget = chatBudget(state);
  const chat = useChatConversation(budget, null, { composeMessage });
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hideRef = useRef<HTMLButtonElement>(null);
  const announced = useRef<string | null>(null);
  const [again, setAgain] = useState(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  // Ideas are fixed when the job succeeds, against the plan at that moment.
  const [replies, setReplies] = useState<ReadonlyMap<string, Reply>>(new Map());
  const job = chat.job;

  useEffect(() => {
    const result = job?.result ?? null;
    if (job === null || job.status !== "succeeded" || result === null) {
      return;
    }
    const id = job.id;
    setReplies((current) => {
      if (current.has(id)) {
        return current;
      }
      const planned = stateRef.current.meals.map((meal) => meal.recipeId);
      const answered = result.status !== "limit" && result.status !== "incomplete";
      return new Map(current).set(id, { ideas: ideasFromJob(job, planned), answered });
    });
  }, [job]);

  useEffect(() => {
    if (job === null || job.status !== "succeeded" || job.result === null) {
      return;
    }
    if (announced.current !== job.id) {
      announced.current = job.id;
      if (job.result.status !== "limit" && job.result.status !== "incomplete") {
        onReply?.();
      }
    }
  }, [job, onReply]);

  useEffect(() => {
    if (props.open === true) {
      (inputRef.current ?? hideRef.current)?.focus();
    }
  }, [props.open]);

  const on = providers.capabilities?.chat_configured === true;
  const pending = chat.pending;
  const validation = chat.error === TEXT_ERROR || chat.error === BUDGET_ERROR;
  const current = job === null ? undefined : replies.get(job.id);
  const unanswered = current !== undefined && !current.answered;
  const failed = !pending && !validation && (chat.error !== null || unanswered);
  const canSend = on && !pending && budget !== null && chat.message.trim().length > 0;

  let status = "";
  if (providers.pending) {
    status = "Checking Ask FEWIA.";
  } else if (pending) {
    status = job?.status === "running" ? "Running. FEWIA is finding meals." : "Queued";
  } else if (validation && chat.error !== null) {
    status = chat.error;
  } else if (failed) {
    status = FAILED_LINE;
  } else if (current?.answered === true) {
    status = replyLine(current.ideas.length);
  }

  const send = (): void => {
    if (canSend) {
      inputRef.current?.focus();
      chat.send();
    }
  };
  // "Ask again" puts the last user text back in the draft and sends a fresh request.
  const lastUserTurn = [...chat.messages].reverse().find((turn) => turn.role === "user");
  const lastUser = lastUserTurn?.content ?? null;
  // A user turn is hidden when the next turn is an unanswered reply, or when it is the last user turn
  // of an unanswered job, so Ask again does not repeat the question.
  const hiddenTurnIds = new Set<string>();
  chat.messages.forEach((turn, index) => {
    const next = chat.messages[index + 1];
    if (turn.role === "user" && next?.role === "assistant" && replies.get(next.id)?.answered === false) {
      hiddenTurnIds.add(turn.id);
    }
  });
  if (unanswered && lastUserTurn !== undefined) {
    hiddenTurnIds.add(lastUserTurn.id);
  }
  const askAgain = (): void => {
    if (lastUser !== null) {
      chat.setMessage(lastUser);
      setAgain(true);
    }
  };
  const chatSend = chat.send;
  const draft = chat.message;
  useEffect(() => {
    if (again && draft === lastUser) {
      setAgain(false);
      if (canSend) {
        inputRef.current?.focus();
        chatSend();
      }
    }
  }, [again, draft, lastUser, canSend, chatSend]);
  const retry = (): void => {
    inputRef.current?.focus();
    chat.retry();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };
  const startChat = (): void => {
    setReplies(new Map());
    chat.newConversation();
  };
  const fillStarter = (text: string): void => {
    chat.setMessage(text);
    inputRef.current?.focus();
  };
  const empty = chat.messages.length === 0;

  return (
    <aside id={props.id} className="tonight-ask" aria-labelledby={headingId}>
      <div className="tonight-ask-head">
        <div>
          <h2 id={headingId}>Ask FEWIA</h2>
          {on ? (
            <p className="tonight-ask-sub">
              Replies come from a real model call. Prices are sample estimates.
            </p>
          ) : null}
        </div>
        <div className="tonight-ask-actions">
          {on ? (
            <button type="button" className="tonight-ask-btn" onClick={startChat}>
              New chat
            </button>
          ) : null}
          {props.onHide !== undefined ? (
            <button
              type="button"
              className="tonight-ask-btn tonight-ask-hide"
              ref={hideRef}
              onClick={props.onHide}
            >
              Hide chat
            </button>
          ) : null}
        </div>
      </div>
      <p className="tonight-ask-status" role="status" aria-live="polite">
        {status}
      </p>
      {failed && unanswered && (chat.message.trim().length === 0 || chat.message.trim() === lastUser) ? (
        <button
          type="button"
          className="tonight-ask-btn"
          disabled={lastUser === null || budget === null}
          onClick={askAgain}
        >
          Ask again
        </button>
      ) : null}
      {failed && !unanswered ? (
        <button type="button" className="tonight-ask-btn" disabled={!chat.hasRequest} onClick={retry}>
          Retry
        </button>
      ) : null}
      {!providers.pending && !on ? <p className="tonight-ask-off">{OFF_LINE}</p> : null}
      {on && empty && !pending && !failed ? (
        <div className="tonight-ask-empty">
          <p className="tonight-ask-title">Ask for a meal idea</p>
          <p>FEWIA suggests meals from the catalog. Your plan calculates every price.</p>
          <div className="tonight-ask-starters">
            {STARTERS.map((text) => (
              <button
                key={text}
                type="button"
                className="tonight-ask-btn"
                onClick={() => {
                  fillStarter(text);
                }}
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {on && !empty ? (
        <ol className="tonight-ask-log" aria-label="Messages">
          {chat.messages.map((turn) => {
            const reply = replies.get(turn.id);
            if (turn.role === "assistant" && reply?.answered === false) {
              return null;
            }
            if (hiddenTurnIds.has(turn.id)) {
              return null;
            }
            const ideas = reply?.ideas ?? [];
            return (
              <li key={turn.id} className={`tonight-ask-turn is-${turn.role}`}>
                <p className="tonight-ask-who">{turn.role === "user" ? "You" : "FEWIA"}</p>
                <p className="tonight-ask-text">{turn.content}</p>
                {ideas.length > 0 ? (
                  <>
                    <ul className="tonight-ask-ideas" aria-label="Meal ideas">
                      {ideas.map((idea) => (
                        <li key={idea.recipeId}>
                          <ChatIdeaCard
                            recipeId={idea.recipeId}
                            servings={idea.servings}
                            state={state}
                            onToggle={props.onToggleIdea}
                          />
                        </li>
                      ))}
                    </ul>
                    <p className="tonight-ask-est">Price changes are sample estimates.</p>
                  </>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}
      {on ? (
        <form
          className="tonight-ask-form"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <label htmlFor={inputId}>Ask for a meal</label>
          <div className="tonight-ask-row">
            <textarea
              id={inputId}
              ref={inputRef}
              rows={2}
              maxLength={Math.max(MAX_MESSAGE_LENGTH - planChatPrefix(state).length, 0)}
              value={chat.message}
              readOnly={pending}
              aria-describedby={`${inputId}-hint`}
              onChange={(event) => {
                chat.setMessage(event.target.value);
              }}
              onKeyDown={onKeyDown}
            />
            <button type="submit" className="tonight-ask-send" disabled={!canSend}>
              {pending ? "Sending" : "Send"}
            </button>
          </div>
          <p id={`${inputId}-hint`} className="tonight-ask-hint">
            {budget === null
              ? "Fix the plan cap to send a message."
              : "Enter sends. Shift+Enter adds a line."}
          </p>
        </form>
      ) : null}
    </aside>
  );
}
