/**
 * Shell footer: legal links and the run-mode badge.
 *
 * The URLs come from `capabilities.legal_urls` because the hosted and local
 * builds point at different documents, and they are real server paths rather
 * than hash routes so a university legal office can link and print them.
 *
 * The language selector UI PRD §5 puts here arrives with U0's locale work; this
 * slice ships `en` only, and a one-item selector is noise.
 */

import { h } from "../lib/dom.js";

const LEGAL_LINKS = [
  ["privacy", "Privacy"],
  ["terms", "Terms"],
  ["sources", "Data sources"],
];

/**
 * @param {Object} options
 * @param {{get: function(): Object}} options.store
 * @returns {HTMLElement}
 */
export function createFooter({ store }) {
  const capabilities = store.get().capabilities;
  const legalUrls = capabilities?.legal_urls || {};

  return h(
    "ul",
    null,
    LEGAL_LINKS.map(([key, label]) => (
      legalUrls[key] ? h("li", null, h("a", { href: legalUrls[key] }, label)) : null
    )),
    capabilities?.mode === "local"
      ? h("li", null, h("span", { class: "local-badge" }, "Runs locally"))
      : null,
  );
}
