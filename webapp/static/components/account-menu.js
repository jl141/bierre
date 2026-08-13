/**
 * Account slot in the header: a Sign in link when anonymous, a disclosure menu
 * when signed in.
 *
 * Returns null when the deployment has no sign-in flow. That is the whole point
 * of the capability gate: local mode gets no account affordance at all, not a
 * disabled one with a tooltip explaining why (UI PRD §4). Someone who ran a
 * Python script on their own machine is already authenticated by owning it.
 *
 * `<details>`/`<summary>` rather than an ARIA menu: a disclosure is what this
 * actually is, and the native element already has the keyboard behaviour, the
 * expanded state and the screen-reader announcement that a hand-rolled
 * `role="menu"` gets wrong. Only two things are missing from the native
 * element and are added below — Escape to close, and closing on a click
 * elsewhere in the page.
 */

import { h } from "../lib/dom.js";
import { describeAuthError } from "../lib/session.js";

/**
 * @param {Object} options
 * @param {{get: function(): Object, subscribe: function(function(Object): void): function(): void}} options.store
 * @param {Object} options.session `lib/session.js`
 * @param {{navigate: function(string): void}} options.router
 * @returns {?HTMLElement}
 */
export function createAccountMenu({ store, session, router }) {
  if (!store.get().capabilities?.auth) return null;

  const slot = h("div", { class: "account-slot-inner" });
  let renderedKey = null;

  /**
   * Re-render only when the identity on display changes. The store notifies on
   * every patch — a search result, a settings load — and replacing the menu's
   * DOM on each one would close it under the user's cursor.
   */
  function render(state = store.get()) {
    const user = state.user;
    const key = user ? `${user.id}:${user.display_name}:${user.email}` : "anonymous";
    if (key === renderedKey) return;

    renderedKey = key;
    slot.replaceChildren(user ? buildMenu(user) : buildSignInLink());
  }

  function buildSignInLink() {
    return h("a", { class: "account-link", href: "#/signin" }, "Sign in");
  }

  function buildMenu(user) {
    // A display name is optional and starts empty, so the address is the
    // fallback label — never the user id, which means nothing to its owner.
    const label = user.display_name || user.email || "Account";

    const error = h("p", { class: "account-menu-error", role: "alert", hidden: true });
    const signOutButton = h("button", {
      type: "button",
      class: "account-menu-action",
      onClick: () => endSession(() => session.signOut()),
    }, "Sign out");
    const signOutAllButton = h("button", {
      type: "button",
      class: "account-menu-action",
      onClick: () => endSession(() => session.signOutEverywhere()),
    }, "Sign out everywhere");

    const details = h(
      "details",
      { class: "account-menu" },
      h("summary", { class: "account-menu-summary" }, label),
      h(
        "div",
        { class: "account-menu-panel" },
        h(
          "ul",
          { class: "account-menu-list" },
          h("li", null, h("a", { class: "account-menu-action", href: "#/account" }, "Account")),
          h("li", null, signOutButton),
          h("li", null, signOutAllButton),
        ),
        error,
      ),
    );

    // The panel outlives a navigation, so a link inside it has to close it.
    details.addEventListener("click", (event) => {
      if (event.target.closest("a")) details.open = false;
    });

    details.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !details.open) return;
      details.open = false;
      // Focus must come back to the control that opened the panel; leaving it on
      // a hidden button strands a keyboard user at the top of the document.
      details.querySelector("summary").focus();
    });

    async function endSession(run) {
      if (signOutButton.disabled) return;
      error.hidden = true;
      signOutButton.disabled = true;
      signOutAllButton.disabled = true;

      try {
        await run();
        // The store update re-renders this slot, so nothing here is reachable
        // afterwards; the navigation is what the user is waiting for.
        router.navigate("/");
      } catch (failure) {
        error.textContent = describeAuthError(failure, {
          unauthorized: "Could not sign out. Reload the page and try again.",
        });
        error.hidden = false;
        signOutButton.disabled = false;
        signOutAllButton.disabled = false;
      }
    }

    return details;
  }

  // One listener for the app's lifetime rather than one per rendered menu, so
  // replacing the menu cannot leave a listener behind holding a detached node.
  document.addEventListener("pointerdown", (event) => {
    const open = slot.querySelector("details[open]");
    if (open && !open.contains(event.target)) open.open = false;
  });

  store.subscribe(render);
  render();
  return slot;
}
