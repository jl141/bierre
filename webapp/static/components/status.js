/**
 * Status line: a message, optionally with the indeterminate progress bar.
 *
 * Shared by the run status and the AI-generation dialog. The element is a live
 * region, so a message that appears while focus is elsewhere is still announced
 * — `hidden` alone changes the tree without telling anyone (UI PRD §8.7).
 */

import { clear as clearChildren, h } from "../lib/dom.js";

/**
 * @param {HTMLElement} element A `.status` element.
 * @returns {{text: function(string, {error?: boolean}=): void,
 *            progress: function(string, Object=): void,
 *            workingVisible: function(boolean): void,
 *            clear: function(): void}}
 */
export function createStatus(element) {
  element.setAttribute("role", "status");
  element.setAttribute("aria-live", "polite");

  function show(isError) {
    element.hidden = false;
    element.className = `status${isError ? " error" : ""}`;
  }

  /** Hide just the bar, keeping the last message on screen. */
  function workingVisible(visible) {
    const working = element.querySelector(".status-working");
    if (working) working.hidden = !visible;
  }

  /** Plain message, no progress bar. */
  function text(message, { error = false } = {}) {
    show(error);
    element.replaceChildren(h("span", { class: "status-text" }, message));
  }

  /**
   * Message plus the working bar.
   * @param {string} message
   * @param {{step?: number, total?: number, label?: string}} [event]
   */
  function progress(message, event = {}) {
    show(false);

    const step = Number(event.step);
    const total = Number(event.total);
    const label = String(event.label || "").trim();
    const hasCounts = Number.isFinite(step) && Number.isFinite(total) && total > 0;
    const progressText = hasCounts
      ? `${Math.max(0, step)}/${Math.max(1, total)}${label ? ` ${label}` : ""}`
      : label;

    const existingText = element.querySelector(".status-text");
    const existingProgress = element.querySelector(".status-progress");
    if (existingText && existingProgress) {
      // Reuse the nodes so the CSS animation does not restart on every event.
      existingText.textContent = message;
      existingProgress.textContent = progressText;
    } else {
      element.replaceChildren(
        h("span", { class: "status-text" }, message),
        h(
          "span",
          { class: "status-working" },
          h("span", { class: "bar" }),
          h("span", { class: "status-progress" }, progressText),
        ),
      );
    }
    workingVisible(true);
  }

  function clear() {
    element.hidden = true;
    element.className = "status";
    clearChildren(element);
  }

  return { text, progress, workingVisible, clear };
}
