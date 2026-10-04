import { useLayoutEffect, useRef, type JSX } from "react";

type HandoffConsentProps = {
  onCancel: () => void;
  onConfirm: () => void;
};

export function HandoffConsent({ onCancel, onConfirm }: HandoffConsentProps): JSX.Element {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const submitted = useRef(false);
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const trigger = document.activeElement;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) {
        trigger.focus();
      }
    };
  }, []);
  return (
    <dialog
      ref={dialogRef}
      className="handoff-consent"
      aria-labelledby="handoff-consent-title"
      aria-describedby="handoff-consent-description"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h2 id="handoff-consent-title">Create shopping list?</h2>
      <p id="handoff-consent-description">
        Share the shopping-list ingredients and quantities with Instacart to create a
        development shopping link. This creates no purchase. Store prices are not verified.
      </p>
      <div className="handoff-consent-actions">
        <button type="button" className="rebuild-estimate" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className="rebuild-estimate"
          onClick={() => {
            if (submitted.current || !dialogRef.current?.open) {
              return;
            }
            submitted.current = true;
            onConfirm();
            onCancel();
          }}
        >
          Confirm shopping list
        </button>
      </div>
    </dialog>
  );
}
