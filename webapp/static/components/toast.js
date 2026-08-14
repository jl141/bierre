/**
 * Undo toasts.
 *
 * A profile is deleted without a confirmation dialog (UI PRD §6.2, item 5): the
 * dialog would be in the way of the 99 deletions that are intended, and it does
 * nothing for the one that is not. What protects the mistake is this — a toast
 * carrying the action that puts it back.
 *
 * Three details are what make it usable rather than decorative:
 *
 * 1. **It is a live region**, so the message is announced even though focus did
 *    not move into it. `hidden` toggling alone changes the tree silently.
 * 2. **The countdown pauses while the toast is hovered or holds focus.** A timed
 *    control that expires under a slow reader is a WCAG 2.2.1 failure, and this
 *    is the cheapest honest mitigation: as long as someone is looking at it or
 *    tabbed into it, it waits.
 * 3. **Toasts stack rather than replace.** Deleting two profiles quickly must
 *    not throw away the first undo — the deletion has already happened, so
 *    losing the affordance loses data.
 */

import { h } from "../lib/dom.js";

const DEFAULT_DURATION_MS = 7000;
const TICK_MS = 250;

/**
 * @returns {{element: HTMLElement,
 *            show: function(Object): {focusAction: function(): void, close: function(): void},
 *            clear: function(): void}}
 */
export function createToastRegion() {
  const element = h("div", {
    class: "toast-region",
    // `role="status"` is polite by default; `aria-atomic` makes a toast read as
    // one message rather than as the fragment that changed.
    role: "status",
    "aria-live": "polite",
    "aria-atomic": "true",
  });

  /** Every toast currently on screen, so `clear()` can stop their timers. */
  const live = new Set();

  /**
   * @param {Object} options
   * @param {string} options.message What happened, in the past tense.
   * @param {string} [options.actionLabel] Omit for a toast with no undo.
   * @param {function(): (void|Promise<void>)} [options.onAction]
   * @param {number} [options.duration] Milliseconds the action stays available.
   * @param {boolean} [options.error] Renders as a failure and never expires.
   */
  function show({ message, actionLabel, onAction, duration = DEFAULT_DURATION_MS, error = false }) {
    // Hidden from assistive technology on purpose: inside a live region a
    // counter that changes four times a second would re-announce the toast
    // every tick. Sighted users get the countdown; everyone gets the pause.
    const remaining = h("span", { class: "toast-remaining", "aria-hidden": "true" });
    const text = h("p", { class: "toast-message" }, message);
    const toast = h("div", { class: `toast${error ? " toast-error" : ""}` });

    let deadline = Date.now() + duration;
    let paused = false;
    let ticker = null;

    const actionButton = actionLabel
      ? h(
          "button",
          {
            type: "button",
            class: "toast-action",
            onClick: async () => {
              stop();
              actionButton.disabled = true;
              try {
                await onAction?.();
                close();
              } catch {
                // The caller reports the failure in its own status line; the
                // toast stays so the action can be tried again.
                actionButton.disabled = false;
              }
            },
          },
          actionLabel,
        )
      : null;

    function paint() {
      if (!actionButton || error) return;
      const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      remaining.textContent = paused ? "" : ` ${seconds}s`;
    }

    function stop() {
      if (ticker !== null) clearInterval(ticker);
      ticker = null;
    }

    function close() {
      stop();
      live.delete(close);
      toast.remove();
    }

    function tick() {
      if (paused) {
        // While paused the deadline keeps moving with the clock, so releasing
        // hover or focus gives the full remaining time rather than none.
        deadline = Math.max(deadline, Date.now() + TICK_MS);
        paint();
        return;
      }
      paint();
      if (Date.now() >= deadline) close();
    }

    if (!error) {
      ticker = setInterval(tick, TICK_MS);
      const pause = () => {
        paused = true;
        paint();
      };
      const resume = () => {
        paused = false;
        deadline = Date.now() + duration;
        paint();
      };
      toast.addEventListener("pointerenter", pause);
      toast.addEventListener("pointerleave", resume);
      toast.addEventListener("focusin", pause);
      toast.addEventListener("focusout", resume);
    }

    toast.append(...[text, actionButton, remaining].filter(Boolean));
    paint();
    element.append(toast);
    live.add(close);

    return {
      /** Used when the control that triggered this was removed from the page. */
      focusAction() {
        actionButton?.focus();
      },
      close,
    };
  }

  return {
    element,
    show,

    /** Drop every toast — on unmount, so no timer outlives the view. */
    clear() {
      for (const close of [...live]) close();
    },
  };
}
