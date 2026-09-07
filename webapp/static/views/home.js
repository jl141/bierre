/**
 * Home view: tool introduction, app download.
 * The `#/` route.
 */

import { h } from "../lib/dom.js";
import { createStatus } from "../components/status.js";
import { request } from "../lib/api.js";

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createHomeView({ store }) {
  let element = null;

  void store;

  function build() {
    const homePanel = h(
      "section",
      { class: "panel home-panel", id: "home-panel" },
      h(
        "section",
        { class: "home-hero" },
        h("p", { class: "home-kicker" }, "Research with confidence"),
        h("h1", { class: "home-hero-title" }, "How are you doing research in the age of AI?"),
        h(
          "p",
          { class: "home-copy" },
          "AI assistants can surface papers quickly, but you cannot see why they picked those papers, what they left out, or the biases baked into content policy. In a field built on transparent methods and disclosed sources, that is a strange thing to trust blindly.",
        ),
      ),
      h(
        "section",
        { class: "home-section" },
        h("h2", { class: "panel-title home-title" }, "Introducing bierre"),
        h(
          "p",
          { class: "home-copy" },
          h("span", { class: "gradient-text home-brand-inline" }, "bierre"),
          " is an open-source, deterministic search research tool. Every ranking decision is inspectable. Nothing is hidden behind a model you cannot question.",
        ),
      ),
      h(
        "section",
        { class: "home-section" },
        h("h2", { class: "panel-title home-title" }, "How it works"),
        h(
          "ol",
          { class: "home-steps" },
          h(
            "li",
            { class: "home-step" },
            h("h3", null, "Build a domain profile."),
            h(
              "p",
              { class: "home-copy" },
              "Tell bierre your field and intent, and it shapes how your search terms are expanded.",
            ),
          ),
          h(
            "li",
            { class: "home-step" },
            h("h3", null, "It searches where researchers actually publish."),
            h(
              "p",
              { class: "home-copy" },
              "OpenAlex, PubMed, Semantic Scholar, CrossRef, and Europe PMC are merged into one balanced result set.",
            ),
          ),
          h(
            "li",
            { class: "home-step" },
            h("h3", null, "Papers are ranked in the open."),
            h(
              "p",
              { class: "home-copy" },
              "bierre uses established open-source algorithms, BM-25 and TF-IDF, to score lexical and semantic match. No black box. No hidden weighting.",
            ),
          ),
        ),
      ),
      h(
        "section",
        { class: "home-section home-cta" },
        h("h2", { class: "panel-title home-title" }, "Try the full search right now, for free."),
        h(
          "div",
          { class: "home-cta-actions" },
          h("a", { class: "home-cta-button", href: "#/search" }, "Try bierre"),
        ),
      ),
    );

    return h("div", { class: "view view-home" }, homePanel);
  }

  return {
    mount(outlet) {
      if (!element) {
        element = build();
      }
      outlet.append(element);
    },

    // The view keeps its DOM (and the last result) between navigations; the
    // router detaches it, so there is nothing to tear down.
    unmount() {},
  };
}
