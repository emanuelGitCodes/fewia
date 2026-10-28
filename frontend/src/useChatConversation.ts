import { useCallback, useEffect, useRef, useState } from "react";
import {
  BUDGET_ERROR,
  MAX_MESSAGE_LENGTH,
  TEXT_ERROR,
  beginDispatch,
  copyJobBody,
  endDispatch,
  keepLatestTurns,
  shouldReplaySavedBody,
  validBudget,
  type ChatBudget,
} from "./chatConversationModel";
import type { ChatJob, ChatJobCreate } from "./chatTypes";
import { useChatJob } from "./useChatJob";

export type { ChatBudget };
export { BUDGET_ERROR, TEXT_ERROR };

export type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export function useChatConversation(
  budget: ChatBudget | null,
  manualJobId: string | null = null,
  options?: { composeMessage?: (text: string) => string },
): {
  message: string;
  setMessage: (value: string) => void;
  messages: ChatTurn[];
  job: ChatJob | null;
  error: string | null;
  pending: boolean;
  hasRequest: boolean;
  send: () => void;
  retry: () => void;
  newConversation: () => void;
} {
  const { job: polledJob, error: jobError, pending, submit, clear } = useChatJob();
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const [lastBody, setLastBody] = useState<ChatJobCreate | null>(null);
  const parentRef = useRef<string | null>(null);
  const seenRef = useRef(new Set<string>());
  const userSeq = useRef(0);
  const busyRef = useRef(false);
  const dispatchGenRef = useRef(0);
  const manualRef = useRef(manualJobId);
  const seenManualRef = useRef<string | null>(null);
  const parentGenRef = useRef(0);
  const sendParentGenRef = useRef(0);
  const convGenRef = useRef(0);
  const sendConvGenRef = useRef(0);
  manualRef.current = manualJobId;
  const composeMessage = options?.composeMessage;
  // clear() cancels old polling attempts. The generation also hides jobs after New chat.
  const job = convGenRef.current === sendConvGenRef.current ? polledJob : null;

  useEffect(() => {
    if (manualJobId === seenManualRef.current) {
      return;
    }
    seenManualRef.current = manualJobId;
    parentRef.current = null;
    parentGenRef.current += 1;
  }, [manualJobId]);

  useEffect(() => {
    const retained = new Set(
      messages.filter((turn) => turn.role === "assistant").map((turn) => turn.id),
    );
    if (job !== null) {
      retained.add(job.id);
    }
    seenRef.current = new Set([...seenRef.current].filter((id) => retained.has(id)));
    if (job === null || job.status !== "succeeded" || job.result === null) {
      return;
    }
    if (seenRef.current.has(job.id)) {
      return;
    }
    seenRef.current.add(job.id);
    if (convGenRef.current !== sendConvGenRef.current) {
      return;
    }
    if (parentGenRef.current === sendParentGenRef.current) {
      parentRef.current = job.id;
    }
    const content = job.result.answer ?? "";
    setMessages((current) =>
      keepLatestTurns([...current, { id: job.id, role: "assistant", content }]),
    );
  }, [job, messages]);

  const send = useCallback((): void => {
    if (busyRef.current || pending) {
      return;
    }
    if (!validBudget(budget)) {
      setLocalError(BUDGET_ERROR);
      return;
    }
    const text = message.trim();
    const composed = composeMessage === undefined ? text : composeMessage(text);
    if (
      text.length === 0 ||
      message.length > MAX_MESSAGE_LENGTH ||
      composed.length > MAX_MESSAGE_LENGTH
    ) {
      setLocalError(TEXT_ERROR);
      return;
    }
    const body: ChatJobCreate = {
      message: composed,
      monthly_limit_cents: budget.monthly_limit_cents,
      plan_cap_cents: budget.plan_cap_cents,
      previous_job_id: parentRef.current ?? manualRef.current,
    };
    if (
      lastBody !== null &&
      shouldReplaySavedBody(job, lastBody, {
        ...body,
        previous_job_id: lastBody.previous_job_id,
      })
    ) {
      setLocalError(null);
      const gen = beginDispatch(busyRef, dispatchGenRef);
      void submit(copyJobBody(lastBody)).finally(() => {
        endDispatch(busyRef, dispatchGenRef, gen);
      });
      return;
    }
    setLocalError(null);
    clear();
    const gen = beginDispatch(busyRef, dispatchGenRef);
    convGenRef.current += 1;
    sendConvGenRef.current = convGenRef.current;
    sendParentGenRef.current = parentGenRef.current;
    userSeq.current += 1;
    const turnId = `user-${userSeq.current}`;
    setLastBody(copyJobBody(body));
    setMessages((current) =>
      keepLatestTurns([...current, { id: turnId, role: "user", content: text }]),
    );
    void submit(copyJobBody(body)).finally(() => {
      endDispatch(busyRef, dispatchGenRef, gen);
    });
  }, [budget, clear, composeMessage, job, lastBody, message, pending, submit]);

  const retry = useCallback((): void => {
    if (busyRef.current || pending || lastBody === null) {
      return;
    }
    setLocalError(null);
    const gen = beginDispatch(busyRef, dispatchGenRef);
    void submit(copyJobBody(lastBody)).finally(() => {
      endDispatch(busyRef, dispatchGenRef, gen);
    });
  }, [lastBody, pending, submit]);

  const newConversation = useCallback((): void => {
    dispatchGenRef.current += 1;
    convGenRef.current += 1;
    busyRef.current = false;
    seenRef.current.clear();
    parentRef.current = null;
    userSeq.current = 0;
    setMessages([]);
    setMessage("");
    setLastBody(null);
    setLocalError(null);
    clear();
  }, [clear]);

  return {
    message,
    setMessage,
    messages,
    job,
    error: localError ?? jobError,
    pending,
    hasRequest: lastBody !== null,
    send,
    retry,
    newConversation,
  };
}
