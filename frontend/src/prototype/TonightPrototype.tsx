import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type JSX } from "react";
import {
  addMeal,
  planLines,
  removeMeal,
  shiftMealServings,
  togglePlanChecked,
  togglePlanPantry,
  withPlanBudgetInput,
  withPlanView,
  withProposalSnapshot,
  type PlanState,
} from "./planModel";
import { consumePlanCheckpoint, PLAN_RESTORE_ERROR, readReturnPlan } from "./planCheckpoint";
import { PlanChat } from "./PlanChat";
import { PantryPanel, PlanPanel, PrototypeNav } from "./PrototypePanels";
import { useKrogerStore } from "./useKrogerStore";
import "./tonight.css";

// Below 1180 px Ask FEWIA is a sheet; below 720 px it covers the whole plan under the pinned total.
const SHEET_QUERY = "(max-width: 1179px)";
const PHONE_QUERY = "(max-width: 719px)";

function useMediaQuery(query: string, fallback: boolean): boolean {
  const [value, setValue] = useState(() => window.matchMedia?.(query).matches ?? fallback);
  useEffect(() => {
    const list = window.matchMedia?.(query);
    if (list === undefined) {
      return undefined;
    }
    const update = (): void => {
      setValue(list.matches);
    };
    update();
    list.addEventListener?.("change", update);
    return () => {
      list.removeEventListener?.("change", update);
    };
  }, [query]);
  return value;
}

export function TonightPrototype(): JSX.Element {
  const [returnPlan] = useState(readReturnPlan);
  const [state, setState] = useState<PlanState>(() => returnPlan.state);
  const [restoreError, setRestoreError] = useState(returnPlan.error);
  // Cleared once the return line has been shown, so it appears once per page load.
  const [krogerReturn, setKrogerReturn] = useState(returnPlan.kroger);
  const consumed = useRef(false);
  useEffect(() => {
    if (!returnPlan.returning || consumed.current) {
      return;
    }
    consumed.current = true;
    if (!consumePlanCheckpoint()) {
      setRestoreError(PLAN_RESTORE_ERROR);
    }
    // This is the only place that strips the marker; PlanChat shows its message.
    const url = new URL(window.location.href);
    url.searchParams.delete("kroger");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  }, [returnPlan]);
  useEffect(() => {
    // The restore warning ends with the first plan change after it.
    if (state !== returnPlan.state) {
      setRestoreError(null);
    }
  }, [state, returnPlan]);
  const kroger = useKrogerStore();
  const previousView = useRef(state.view);
  const rootRef = useRef<HTMLDivElement>(null);
  const focusedRef = useRef<HTMLElement | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const dockRef = useRef<HTMLButtonElement>(null);
  const askId = useId();
  const newReplyId = `${askId}-new`;
  const [askOpen, setAskOpen] = useState(false);
  const [newReply, setNewReply] = useState(false);
  const [replySequence, setReplySequence] = useState(0);
  const sheetLayout = useMediaQuery(SHEET_QUERY, true);
  const phone = useMediaQuery(PHONE_QUERY, false);
  const sheetOpen = askOpen && sheetLayout;
  useEffect(() => {
    // The sheet stays closed after a desktop round trip.
    if (!sheetLayout) {
      setAskOpen(false);
      setNewReply(false);
    }
  }, [sheetLayout]);
  const wasOpen = useRef(false);
  const restoreFocus = useRef(false);
  const lines = planLines(state);
  const previousLayout = useRef({ sheetLayout, phone });

  useLayoutEffect(() => {
    const previous = previousLayout.current;
    previousLayout.current = { sheetLayout, phone };
    const panel = rootRef.current?.querySelector(".tonight-ask");
    const focused = focusedRef.current;
    if (!(panel instanceof HTMLElement) || focused === null) {
      return;
    }
    if (sheetLayout && !previous.sheetLayout && panel.contains(focused)) {
      dockRef.current?.focus();
    } else if (
      !sheetLayout &&
      previous.sheetLayout &&
      (dockRef.current?.contains(focused) === true || focused.matches(".tonight-ask-hide"))
    ) {
      panel.querySelector<HTMLElement>("h2")?.focus();
    } else if (phone && !previous.phone && sheetOpen && !panel.contains(focused)) {
      panel.querySelector<HTMLElement>("h2")?.focus();
    }
  }, [sheetLayout, phone, sheetOpen]);

  const closeSheet = useCallback((): void => {
    const panel = rootRef.current?.querySelector(".tonight-ask");
    restoreFocus.current = panel?.contains(document.activeElement) === true;
    setAskOpen(false);
  }, []);
  const openSheet = (): void => {
    const canvas = canvasRef.current;
    const pinned = canvas?.querySelector(".tonight-pinned");
    if (phone && canvas !== null && pinned instanceof HTMLElement) {
      // The sheet starts under the pinned total, so scroll the total to the top first.
      const gap = pinned.getBoundingClientRect().top - canvas.getBoundingClientRect().top;
      if (gap > 0) {
        canvas.scrollTop += gap;
      }
    }
    setNewReply(false);
    setAskOpen(true);
  };
  const onReply = useCallback((): void => {
    if (sheetLayout && !sheetOpen) {
      setNewReply(true);
      setReplySequence((current) => current + 1);
    }
  }, [sheetLayout, sheetOpen]);

  useEffect(() => {
    if (wasOpen.current && !sheetOpen && sheetLayout && restoreFocus.current) {
      dockRef.current?.focus();
    }
    wasOpen.current = sheetOpen;
    restoreFocus.current = false;
  }, [sheetOpen, sheetLayout]);
  useEffect(() => {
    if (!sheetOpen) {
      return undefined;
    }
    const onKey = (event: KeyboardEvent): void => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !event.isComposing &&
        event.keyCode !== 229
      ) {
        event.preventDefault();
        closeSheet();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [sheetOpen, closeSheet]);
  // Phone chat makes the plan and navigation inert. Tablet chat makes only covered content inert.
  useEffect(() => {
    if (!sheetOpen) {
      return undefined;
    }
    const main = mainRef.current;
    const covered: Array<Element | null> = phone
      ? [
          headerRef.current,
          main,
          rootRef.current?.querySelector(".tonight-nav") ?? null,
        ]
      : [main?.querySelector(".tonight-plan-main") ?? main];
    const targets = covered.filter(
      (node): node is Element => node !== null && !node.hasAttribute("inert"),
    );
    for (const node of targets) {
      node.setAttribute("inert", "");
    }
    return () => {
      for (const node of targets) {
        node.removeAttribute("inert");
      }
    };
  }, [sheetOpen, phone, state.view]);
  useEffect(() => {
    // Focus moves only when the view changes.
    if (previousView.current === state.view) {
      return;
    }
    previousView.current = state.view;
    const heading = mainRef.current?.querySelector("h1");
    if (heading instanceof HTMLElement) {
      heading.focus({ preventScroll: true });
    }
    const canvas = canvasRef.current;
    if (canvas !== null) {
      canvas.scrollTop = 0;
    }
    window.scrollTo(0, 0);
  }, [state.view]);
  return (
    <div
      ref={rootRef}
      className={sheetOpen ? "tonight-prototype is-ask-open" : "tonight-prototype"}
      onFocusCapture={(event) => {
        focusedRef.current = event.target;
      }}
      onBlurCapture={(event) => {
        if (event.relatedTarget instanceof HTMLElement) {
          focusedRef.current = event.relatedTarget;
        }
      }}
    >
      <div className="tonight-frame">
        <div className="tonight-canvas" ref={canvasRef}>
          <header className="tonight-header" ref={headerRef}>
            <p className="tonight-wordmark">FEWIA</p>
            {restoreError !== null ? <p role="alert">{restoreError}</p> : null}
          </header>
          <main ref={mainRef}>
            {state.view === "plan" ? (
              <PlanPanel
                state={state}
                lines={lines}
                onToggleMeal={(id, planned) => {
                  setState((current) => (planned ? removeMeal(current, id) : addMeal(current, id)));
                }}
                onShiftServings={(id, delta) => {
                  setState((current) => shiftMealServings(current, id, delta));
                }}
                onTogglePantry={(id) => {
                  setState((current) => togglePlanPantry(current, id));
                }}
                onToggleChecked={(id) => {
                  setState((current) => togglePlanChecked(current, id));
                }}
                onBudgetChange={(value) => {
                  setState((current) => withPlanBudgetInput(current, value));
                }}
                onEditPantry={() => {
                  setState((current) => withPlanView(current, "pantry"));
                }}
              />
            ) : null}
            {state.view === "pantry" ? (
              <PantryPanel
                pantry={state.pantry}
                onToggle={(id) => {
                  setState((current) => togglePlanPantry(current, id));
                }}
                onBack={() => {
                  setState((current) => withPlanView(current, "plan"));
                }}
              />
            ) : null}
          </main>
          <PlanChat
            id={askId}
            state={state}
            open={sheetOpen}
            collapsed={sheetLayout && !sheetOpen}
            modal={phone && sheetOpen}
            onHide={closeSheet}
            onReply={onReply}
            krogerReturn={krogerReturn}
            onKrogerReturnShown={() => {
              setKrogerReturn(null);
            }}
            krogerStore={kroger.store}
            onKrogerChoose={kroger.choose}
            onKrogerClear={kroger.clear}
            onApplyProposal={(snapshot) => {
              setState((current) => withProposalSnapshot(current, snapshot));
            }}
            onToggleIdea={(id, servings, inPlan) => {
              setState((current) =>
                inPlan ? removeMeal(current, id) : addMeal(current, id, servings),
              );
            }}
          />
        </div>
        <div className="tonight-dock" hidden={!sheetLayout || sheetOpen}>
          <button
            type="button"
            className="tonight-dock-btn"
            ref={dockRef}
            aria-expanded={sheetOpen}
            aria-controls={askId}
            aria-haspopup={phone ? "dialog" : undefined}
            aria-describedby={newReply ? newReplyId : undefined}
            onClick={openSheet}
          >
            Ask FEWIA for a meal idea
          </button>
          {newReply ? (
            <span id={newReplyId} className="tonight-dock-new">
              1 new reply
            </span>
          ) : null}
        </div>
      </div>
      <PrototypeNav
        view={state.view}
        onNav={(view) => {
          setAskOpen(false);
          setState((current) => withPlanView(current, view));
        }}
      />
      <div className="tonight-dock-announcement visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {newReply ? <span key={replySequence}>FEWIA replied. Open Ask FEWIA to read it.</span> : null}
      </div>
    </div>
  );
}
