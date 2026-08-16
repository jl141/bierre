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
  let launchDialog = null;
  let launchEmailInput = null;
  let launchStatus = null;
  let launchSubmitButton = null;
  let launchCloseButton = null;

  void store;

  function setLaunchSubmitting(submitting) {
    if (launchSubmitButton) launchSubmitButton.disabled = submitting;
    if (launchCloseButton) launchCloseButton.disabled = submitting;
    if (launchEmailInput) launchEmailInput.readOnly = submitting;
  }

  function openLaunchDialog() {
    if (!launchDialog) return;
    launchStatus?.clear();
    launchEmailInput.value = "";
    launchDialog.showModal();
    launchEmailInput.focus();
  }

  function closeLaunchDialog() {
    if (!launchDialog?.open) return;
    launchDialog.close();
    launchStatus?.clear();
    setLaunchSubmitting(false);
  }

  async function submitLaunchEmail(event) {
    event.preventDefault();

    const email = String(launchEmailInput?.value || "").trim();
    if (!email || !launchEmailInput?.validity.valid) {
      launchStatus.text("Enter a valid email address first.", { error: true });
      launchEmailInput.focus();
      return;
    }

    setLaunchSubmitting(true);
    launchStatus.progress("Submitting your email…", { label: "Please wait" });

    try {
      await request("/api/launchlist", {
        method: "POST",
        body: { email },
      });
      launchStatus.text("You are on the launch list. We will email you soon.");
      launchEmailInput.value = "";
    } catch {
      launchStatus.text("Could not submit your email. Try again.", { error: true });
    } finally {
      launchStatus.workingVisible(false);
      setLaunchSubmitting(false);
    }
  }

  function build() {
    const launchStatusElement = h("p", { class: "status", id: "launch-status", hidden: true });
    launchStatus = createStatus(launchStatusElement);

    launchEmailInput = h("input", {
      id: "launch-email",
      type: "email",
      name: "email",
      required: true,
      autocomplete: "email",
      placeholder: "you@university.edu",
    });

    launchCloseButton = h(
      "button",
      {
        type: "button",
        class: "btn-ghost",
        onClick: closeLaunchDialog,
      },
      "Close",
    );

    launchSubmitButton = h("button", { type: "submit" }, "Join launch list");

    launchDialog = h(
      "dialog",
      {
        class: "profile-modal home-launch-modal",
        "aria-labelledby": "launch-modal-title",
        "aria-describedby": "launch-modal-note",
      },
      h(
        "form",
        {
          class: "profile-form home-launch-form",
          method: "dialog",
          onSubmit: submitLaunchEmail,
        },
        h(
          "div",
          { class: "profile-modal-head" },
          h("h2", { id: "launch-modal-title" }, "Get notified when bierre launches"),
        ),
        h(
          "p",
          { class: "profile-modal-note", id: "launch-modal-note" },
          "Enter your email and we will let you know when the app download is live.",
        ),
        h(
          "div",
          { class: "field-block" },
          h("label", { for: "launch-email" }, "Email address"),
          launchEmailInput,
        ),
        launchStatusElement,
        h("div", { class: "profile-modal-actions" }, launchCloseButton, launchSubmitButton),
      ),
    );

    launchDialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeLaunchDialog();
    });

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
          h(
            "button",
            {
              type: "button",
              class: "btn-ghost home-cta-ghost",
              onClick: openLaunchDialog,
            },
            "Get notified when it launches",
          ),
        ),
      ),
    );

    return h("div", { class: "view view-home" }, homePanel, launchDialog);
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
