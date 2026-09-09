import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { GroceryJob } from "./apiTypes";
import type { FormState } from "./BudgetForm";
import { ChatPanel } from "./ChatPanel";
import { chatBudgetFromForm, chatEstimateJob, formFromChat } from "./chatWorkspaceModel";
import { useChatConversation, type ChatTurn } from "./useChatConversation";
import { useProviderCapabilities } from "./useProviderCapabilities";
import "./chat.css";

function formKey(form: FormState): string {
  return JSON.stringify(form);
}

function latestUserTurnId(messages: ChatTurn[]): string | null {
  let latest: string | null = null;
  for (const item of messages) {
    if (item.role === "user") {
      latest = item.id;
    }
  }
  return latest;
}

export type ChatWorkspaceInput = {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  formJob: GroceryJob | null;
};

type EstimateSource = { kind: "chat" | "form"; id: string };

export function useChatWorkspace({ form, setForm, formJob }: ChatWorkspaceInput): {
  pending: boolean;
  estimateJob: GroceryJob | null;
  estimateDirty: boolean;
  configured: boolean;
  configurationPending: boolean;
  providerError: string | null;
  retryProviders: () => void;
  conversation: ReturnType<typeof useChatConversation>;
} {
  const providers = useProviderCapabilities();
  const conversation = useChatConversation(chatBudgetFromForm(form));
  const formEpoch = useRef(0);
  const sendEpoch = useRef(0);
  const lastUserId = useRef<string | null>(null);
  const applying = useRef(false);
  const formReady = useRef(false);
  const seenChat = useRef(new Set<string>());
  const seenForm = useRef<string | null>(null);
  const [source, setSource] = useState<EstimateSource | null>(null);
  const [appliedKey, setAppliedKey] = useState<string | null>(null);

  useEffect(() => {
    if (applying.current) {
      applying.current = false;
      return;
    }
    if (!formReady.current) {
      formReady.current = true;
      return;
    }
    formEpoch.current += 1;
  }, [form]);

  useEffect(() => {
    const userId = latestUserTurnId(conversation.messages);
    if (userId === null) {
      lastUserId.current = null;
      return;
    }
    if (lastUserId.current === userId) {
      return;
    }
    sendEpoch.current = formEpoch.current;
    lastUserId.current = userId;
  }, [conversation.messages]);

  useEffect(() => {
    const job = conversation.job;
    if (job === null || job.status !== "succeeded" || job.result === null) {
      return;
    }
    if (seenChat.current.has(job.id)) {
      return;
    }
    seenChat.current.add(job.id);
    if (formEpoch.current !== sendEpoch.current) {
      return;
    }
    if (chatEstimateJob(job) === null) {
      return;
    }
    const next = formFromChat(form, job.result);
    if (next !== form) {
      applying.current = true;
      setForm(next);
    }
    setAppliedKey(formKey(next));
    setSource({ kind: "chat", id: job.id });
  }, [conversation.job, form, setForm]);

  useEffect(() => {
    if (formJob === null || formJob.status !== "succeeded" || formJob.result === null) {
      return;
    }
    if (seenForm.current === formJob.id) {
      return;
    }
    seenForm.current = formJob.id;
    setSource({ kind: "form", id: formJob.id });
  }, [formJob]);

  const chatPlan =
    source?.kind === "chat" && conversation.job?.id === source.id
      ? chatEstimateJob(conversation.job)
      : null;
  return {
    pending: conversation.pending,
    estimateJob: chatPlan,
    estimateDirty: chatPlan !== null && appliedKey !== null && formKey(form) !== appliedKey,
    configured: providers.capabilities?.chat_configured === true,
    configurationPending: providers.pending,
    providerError: providers.error,
    retryProviders: providers.retry,
    conversation,
  };
}

export function ChatWorkspace(props: {
  formPending: boolean;
  configured: boolean;
  configurationPending: boolean;
  providerError: string | null;
  retryProviders: () => void;
  conversation: ReturnType<typeof useChatConversation>;
}): JSX.Element {
  const chat = props.conversation;
  return (
    <div className="chat-workspace">
      {props.providerError !== null ? (
        <div className="catalog-banner">
          <p className="catalog-error" role="status" aria-live="polite">
            {props.providerError}
          </p>
          <button type="button" className="retry-catalog" onClick={props.retryProviders}>
            Retry provider status
          </button>
        </div>
      ) : null}
      <ChatPanel
        messages={chat.messages}
        text={chat.message}
        onChange={chat.setMessage}
        onSend={chat.send}
        onRetry={chat.retry}
        onNewConversation={chat.newConversation}
        pending={chat.pending}
        error={chat.error}
        configured={props.configured}
        configurationPending={props.configurationPending}
        hasRequest={chat.hasRequest}
        disabled={props.formPending}
      />
    </div>
  );
}
