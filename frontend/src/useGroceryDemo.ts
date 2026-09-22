import { useCallback, useEffect, useState } from "react";
import { fetchConfig, isAbortError } from "./api";
import type { GroceryConfig, GroceryJobCreate } from "./apiTypes";
import { buildRequest, initialForm, type FormState } from "./BudgetForm";
import { configFingerprint } from "./chatWorkspaceModel";
import { useGroceryJob } from "./useGroceryJob";

const CONFIG_MS = 20_000;
const CONFIG_UNAVAILABLE = "The grocery catalog is unavailable. Retry the catalog request.";

function cloneBody(body: GroceryJobCreate): GroceryJobCreate {
  return JSON.parse(JSON.stringify(body)) as GroceryJobCreate;
}

function exampleForm(current: FormState, kind: "beans" | "vegan"): FormState {
  if (kind === "beans") {
    return { ...current, diet: "omnivore", meals: [{ recipe_id: "bean_tacos", servings: 2 }] };
  }
  return {
    ...current,
    diet: "vegan",
    meals: [
      { recipe_id: "bean_tacos", servings: 2 },
      { recipe_id: "lentil_soup", servings: 2 },
      { recipe_id: "chickpea_curry", servings: 2 },
    ],
  };
}

function isDirty(config: GroceryConfig | null, form: FormState, last: GroceryJobCreate | null): boolean {
  if (last === null) {
    return false;
  }
  if (config === null) {
    return true;
  }
  try {
    return JSON.stringify(buildRequest(config, form)) !== JSON.stringify(last);
  } catch {
    return true;
  }
}

export function useGroceryDemo() {
  const [config, setConfig] = useState<GroceryConfig | null>(null);
  const [configPending, setConfigPending] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const [form, setForm] = useState<FormState>(initialForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [lastBody, setLastBody] = useState<GroceryJobCreate | null>(null);
  const [lastFingerprint, setLastFingerprint] = useState("");
  const { job, error, pending, submit, clear } = useGroceryJob();
  const reloadConfig = useCallback((): void => {
    setConfigPending(true);
    setRetryTick((tick) => tick + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, CONFIG_MS);
    setConfigPending(true);
    setConfigError(null);
    void fetchConfig(controller.signal)
      .then(
        (value) => {
          if (!cancelled) {
            setConfig(value);
            setConfigError(null);
            setConfigPending(false);
          }
        },
        (caught: unknown) => {
          if (!cancelled && !(isAbortError(caught) && !timedOut)) {
            setConfigError(CONFIG_UNAVAILABLE);
            setConfigPending(false);
          }
        },
      )
      .finally(() => window.clearTimeout(timeoutId));
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [retryTick]);

  const runSubmit = useCallback(
    async (state: FormState, forceNewKey: boolean): Promise<void> => {
      if (config === null || pending || configPending || configError !== null) {
        return;
      }
      let body: GroceryJobCreate;
      try {
        body = cloneBody(buildRequest(config, state));
      } catch (caught) {
        if (caught instanceof Error) {
          setFormError(caught.message);
          return;
        }
        throw caught;
      }
      setFormError(null);
      if (forceNewKey || job?.status === "succeeded" || job?.status === "failed") {
        clear();
      }
      setLastBody(body);
      setLastFingerprint(configFingerprint(config));
      await submit(body);
    },
    [clear, config, configError, configPending, job, pending, submit],
  );
  const submitForm = useCallback(
    (next?: FormState): Promise<void> => runSubmit(next ?? form, false),
    [form, runSubmit],
  );
  const newRequest = useCallback((): void => {
    void runSubmit(form, true);
  }, [form, runSubmit]);
  const retry = useCallback((): void => {
    if (!pending && lastBody !== null) {
      void submit(lastBody);
    }
  }, [lastBody, pending, submit]);
  const example = useCallback(
    (kind: "beans" | "vegan"): void => {
      const next = exampleForm(form, kind);
      setForm(next);
      void runSubmit(next, false);
    },
    [form, runSubmit],
  );
  const togglePantry = useCallback((id: string): void => {
    setForm((current) => ({
      ...current,
      pantry: current.pantry.includes(id)
        ? current.pantry.filter((item) => item !== id)
        : [...current.pantry, id],
    }));
  }, []);

  return {
    config, configPending, configError, reloadConfig, form, setForm, formError,
    job, error, pending, submitForm, retry, newRequest, example, togglePantry,
    dirty:
      isDirty(config, form, lastBody) ||
      (lastBody !== null && lastFingerprint !== configFingerprint(config)),
  };
}

export type GroceryDemo = ReturnType<typeof useGroceryDemo>;
