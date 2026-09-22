import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { GroceryJob } from "./apiTypes";
import type { FormState } from "./BudgetForm";
import { ChatPanel } from "./ChatPanel";
import { chatBudgetFromForm, chatEstimateJob, formFromChat } from "./chatWorkspaceModel";
import { useChatConversation, type ChatTurn } from "./useChatConversation";
import { useProviderCapabilities } from "./useProviderCapabilities";
import "./chat.css";

export const REBUILD_CHAT_GUIDANCE = "Rebuild your estimate to use these changes in chat";

function formKey(form: FormState, contextKey: string): string {
  return JSON.stringify([form, contextKey]);
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

function validManualId(job: GroceryJob | null): string | null {
  if (job === null || job.status !== "succeeded" || job.result === null) {
    return null;
  }
  return job.id;
}

export type ChatWorkspaceInput = {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  formJob: GroceryJob | null;
  formDirty?: boolean;
  contextKey?: string;
};

type EstimateSource = { kind: "chat" | "form"; id: string };

export function useChatWorkspace({
  form,
  setForm,
  formJob,
  formDirty = false,
  contextKey = "",
}: ChatWorkspaceInput): {
  pending: boolean;
  estimateJob: GroceryJob | null;
  estimateDirty: boolean;
  configured: boolean;
  configurationPending: boolean;
  providerError: string | null;
  retryProviders: () => void;
  conversation: ReturnType<typeof useChatConversation>;
  needsRebuild: boolean;
  instacartConfigured: boolean;
  plaidConfigured: boolean;
} {
  const providers = useProviderCapabilities();
  const [source, setSource] = useState<EstimateSource | null>(null);
  const [appliedKey, setAppliedKey] = useState<string | null>(null);
  const [chatEstimate, setChatEstimate] = useState<GroceryJob | null>(null);
  const owned =
    source !== null && appliedKey !== null && formKey(form, contextKey) === appliedKey;
  const contextId = owned ? source.id : null;
  const needsRebuild = source !== null && !owned;
  const conversation = useChatConversation(chatBudgetFromForm(form), contextId);
  const formEpoch = useRef(0);
  const sendEpoch = useRef(0);
  const manualGen = useRef(0);
  const sendManualGen = useRef(0);
  const contextGen = useRef(0);
  const sendContextGen = useRef(0);
  const lastUserId = useRef<string | null>(null);
  const applying = useRef(false);
  const formReady = useRef(false);
  const contextReady = useRef(false);
  const seenChat = useRef(new Set<string>());
  const seenForm = useRef<string | null>(null);

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
    if (!contextReady.current) {
      contextReady.current = true;
      return;
    }
    contextGen.current += 1;
  }, [contextKey]);

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
    sendManualGen.current = manualGen.current;
    sendContextGen.current = contextGen.current;
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
    const incoming = validManualId(formJob);
    if (incoming !== null && incoming !== seenForm.current) {
      return;
    }
    if (
      formEpoch.current !== sendEpoch.current ||
      manualGen.current !== sendManualGen.current ||
      contextGen.current !== sendContextGen.current
    ) {
      return;
    }
    const estimate = chatEstimateJob(job);
    if (estimate === null) {
      return;
    }
    const next = formFromChat(form, job.result);
    if (next !== form) {
      applying.current = true;
      setForm(next);
    }
    setAppliedKey(formKey(next, contextKey));
    setChatEstimate(estimate);
    setSource({ kind: "chat", id: job.id });
  }, [conversation.job, form, formJob, setForm, contextKey]);

  useEffect(() => {
    if (formJob === null || formJob.status !== "succeeded" || formJob.result === null) {
      return;
    }
    if (seenForm.current === formJob.id) {
      return;
    }
    seenForm.current = formJob.id;
    manualGen.current += 1;
    setChatEstimate(null);
    setSource({ kind: "form", id: formJob.id });
    if (!formDirty) {
      setAppliedKey(formKey(form, contextKey));
    }
  }, [form, formDirty, formJob, contextKey]);

  const chatPlan = source?.kind === "chat" ? chatEstimate : null;
  return {
    pending: conversation.pending,
    estimateJob: chatPlan,
    estimateDirty:
      chatPlan !== null && appliedKey !== null && formKey(form, contextKey) !== appliedKey,
    configured: providers.capabilities?.chat_configured === true,
    configurationPending: providers.pending,
    providerError: providers.error,
    retryProviders: providers.retry,
    conversation,
    needsRebuild,
    instacartConfigured: providers.capabilities?.instacart_configured === true,
    plaidConfigured: providers.capabilities?.plaid_configured === true,
  };
}

export function ChatWorkspace(props: {
  formPending: boolean;
  configured: boolean;
  configurationPending: boolean;
  providerError: string | null;
  retryProviders: () => void;
  conversation: ReturnType<typeof useChatConversation>;
  freshSendBlocked?: boolean;
  freshSendDisabled?: boolean;
}): JSX.Element {
  const chat = props.conversation;
  const rebuild = props.freshSendBlocked === true;
  const sendLocked = rebuild || props.freshSendDisabled === true;
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
      {rebuild ? (
        <p className="conversation-status" role="status" aria-live="polite">
          {REBUILD_CHAT_GUIDANCE}
        </p>
      ) : null}
      <ChatPanel
        messages={chat.messages}
        text={chat.message}
        onChange={chat.setMessage}
        onSend={() => {
          if (!sendLocked) {
            chat.send();
          }
        }}
        onRetry={chat.retry}
        onNewConversation={chat.newConversation}
        pending={chat.pending}
        error={chat.error}
        configured={props.configured}
        configurationPending={props.configurationPending}
        hasRequest={chat.hasRequest}
        disabled={props.formPending}
        freshSendDisabled={sendLocked}
      />
    </div>
  );
}
