/**
 * Account slot in the header.
 *
 * Returns null when the deployment has no sign-in flow. That is the whole point
 * of the capability gate: local mode gets no account affordance at all, not a
 * disabled one with a tooltip explaining why (UI PRD §4). Someone who ran a
 * Python script on their own machine is already authenticated by owning it.
 *
 * WS-F replaces the Sign in link with the real menu (display name, Sign out,
 * Sign out everywhere) once `#/signin` and `#/account` exist.
 */

import { h } from "../lib/dom.js";

/**
 * @param {Object} options
 * @param {{get: function(): Object}} options.store
 * @returns {?HTMLElement}
 */
export function createAccountMenu({ store }) {
  const capabilities = store.get().capabilities;
  if (!capabilities?.auth) return null;

  return h("a", { class: "account-link", href: "#/signin" }, "Sign in");
}
