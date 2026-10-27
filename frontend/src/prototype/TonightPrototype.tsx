import { useCallback, useEffect, useId, useRef, useState, type JSX } from "react";
import { DEMO_NOTICE } from "./prototypeData";
import {
  addMeal,
  initialPlanState,
  planLines,
  removeMeal,
  shiftMealServings,
  togglePlanChecked,
  togglePlanPantry,
  withPlanBudgetInput,
  withPlanView,
  type PlanState,
} from "./planModel";
import { PlanChat } from "./PlanChat";
import { PantryPanel, PlanPanel, PrototypeNav } from "./PrototypePanels";
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
  const [state, setState] = useState<PlanState>(initialPlanState);
  const previousView = useRef(state.view);
  const canvasRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const footerRef = useRef<HTMLElement>(null);
  const dockRef = useRef<HTMLButtonElement>(null);
  const askId = useId();
  const newReplyId = `${askId}-new`;
  const [askOpen, setAskOpen] = useState(false);
  const [newReply, setNewReply] = useState(false);
  const sheetLayout = useMediaQuery(SHEET_QUERY, true);
  const phone = useMediaQuery(PHONE_QUERY, false);
  const sheetOpen = askOpen && sheetLayout;
  const wasOpen = useRef(false);
  const restoreFocus = useRef(false);
  const lines = planLines(state);

  const closeSheet = useCallback((): void => {
    restoreFocus.current = true;
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
    }
  }, [sheetLayout, sheetOpen]);

  useEffect(() => {
    if (wasOpen.current && !sheetOpen && restoreFocus.current) {
      dockRef.current?.focus();
    }
    wasOpen.current = sheetOpen;
    restoreFocus.current = false;
  }, [sheetOpen]);
  useEffect(() => {
    if (!sheetOpen) {
      return undefined;
    }
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        closeSheet();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [sheetOpen, closeSheet]);
  // The sheet covers content the user must not reach: the whole plan on a phone, the meals column otherwise.
  useEffect(() => {
    if (!sheetOpen) {
      return undefined;
    }
    const main = mainRef.current;
    const covered: Array<Element | null> = phone
      ? [headerRef.current, main, footerRef.current]
      : [main?.querySelector(".tonight-plan-main") ?? main];
    const targets = covered.filter((node): node is Element => node !== null);
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
    <div className={sheetOpen ? "tonight-prototype is-ask-open" : "tonight-prototype"}>
      <div className="tonight-frame">
        <div className="tonight-canvas" ref={canvasRef}>
          <header className="tonight-header" ref={headerRef}>
            <p className="tonight-wordmark">FEWIA</p>
            <p className="tonight-demo">{DEMO_NOTICE}</p>
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
            onHide={closeSheet}
            onReply={onReply}
            onToggleIdea={(id, servings, inPlan) => {
              setState((current) =>
                inPlan ? removeMeal(current, id) : addMeal(current, id, servings),
              );
            }}
          />
          <footer className="tonight-footer" ref={footerRef}>
            <a href="/">Existing app</a>
          </footer>
        </div>
        {sheetLayout ? (
          <div className="tonight-dock">
            <button
              type="button"
              className="tonight-dock-btn"
              ref={dockRef}
              aria-expanded={sheetOpen}
              aria-controls={askId}
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
        ) : null}
      </div>
      <PrototypeNav
        view={state.view}
        onNav={(view) => {
          setAskOpen(false);
          setState((current) => withPlanView(current, view));
        }}
      />
    </div>
  );
}
