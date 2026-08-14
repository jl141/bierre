/**
 * "Generate with AI": the one dialog UI PRD §6.2 keeps.
 *
 * It stays a modal because it is genuinely modal — three lines of prose, one
 * button, and a result that lands in the editor behind it. Everything else about
 * the old profile dialog moved onto `#/profiles/:id`.
 *
 * Two things are deliberate:
 *
 * 1. **The OpenAI round trip is disclosed here, at the point of use.** A
 *    researcher's unpublished direction is sensitive in a way ordinary user data
 *    is not, and "it is in the privacy policy" is not disclosure. This is UI PRD
 *    §6.2, item 6.
 * 2. **Generation is cancellable rather than locked.** The request is a stream
 *    that can take a while; an `AbortController` on the Cancel button and on
 *    Escape means the user is never trapped watching a progress bar. An aborted
 *    request is not an error and produces no message.
 */

import { h } from "../lib/dom.js";
import { readNdjson, stream } from "../lib/api.js";
import { createStatus } from "./status.js";

const GENERATE_PATH = "/bierre-ca/api/profiles/generate";
const PROGRESS_MESSAGE = "Drafting a profile…";

/**
 * @param {Object} options
 * @param {function(Object): void} options.onDraft Receives a profile payload to
 *   load into the editor. Called only on success.
 * @returns {{element: HTMLDialogElement, open: function(string=): void}}
 */
export function createAiProfileDialog({ onDraft }) {
  let inFlight = null;
  let labelHint = "";

  const description = h("textarea", {
    id: "ai-research-description",
    name: "research_description",
    rows: 7,
    required: true,
    "aria-describedby": "ai-dialog-note ai-disclosure",
    placeholder: "Describe your topic, what counts as evidence, and what you want to exclude.",
  });

  const statusElement = h("p", { class: "status", id: "ai-status", hidden: true });
  const status = createStatus(statusElement);

  const submitButton = h("button", { type: "submit" }, "Generate draft");
  const closeButton = h("button", { type: "button", class: "btn-ghost", onClick: () => dismiss() }, "Close");

  const form = h(
    "form",
    { class: "profile-form", noValidate: true, onSubmit: generate },
    h(
      "div",
      { class: "profile-modal-head" },
      h("h2", { id: "ai-dialog-title" }, "Generate a profile with AI"),
    ),
    h(
      "p",
      { class: "profile-modal-note", id: "ai-dialog-note" },
      "Describe what you are researching. The draft opens in the editor for you to review before anything is saved.",
    ),
    h(
      "div",
      { class: "field-block" },
      h("label", { for: "ai-research-description" }, "Research description"),
      description,
      h(
        "p",
        { class: "field-hint", id: "ai-disclosure" },
        "Your description is sent to OpenAI to draft the profile. It is not stored by bierre.",
      ),
    ),
    statusElement,
    h("div", { class: "profile-modal-actions" }, closeButton, submitButton),
  );

  const element = h(
    "dialog",
    {
      class: "profile-modal profile-ai-modal",
      "aria-labelledby": "ai-dialog-title",
      "aria-describedby": "ai-dialog-note",
    },
    form,
  );

  // Escape fires `cancel`, and a generation in flight has to be abandoned rather
  // than left running against a dialog that is no longer on screen.
  element.addEventListener("cancel", () => abort());
  element.addEventListener("close", () => abort());

  function setGenerating(generating) {
    submitButton.disabled = generating;
    description.readOnly = generating;
    closeButton.textContent = generating ? "Cancel" : "Close";
  }

  function abort() {
    inFlight?.abort();
    inFlight = null;
    setGenerating(false);
    status.workingVisible(false);
  }

  function dismiss() {
    abort();
    if (element.open) element.close();
    status.clear();
  }

  async function generate(event) {
    event.preventDefault();
    if (inFlight) {
      abort();
      status.text("Generation cancelled.");
      return;
    }

    const researchDescription = description.value.trim();
    if (!researchDescription) {
      status.text("Describe what you are researching first.", { error: true });
      description.focus();
      return;
    }

    const controller = new AbortController();
    inFlight = controller;
    setGenerating(true);
    status.progress(PROGRESS_MESSAGE, { step: 0, total: 0, label: "Starting…" });

    const body = { research_description: researchDescription };
    if (labelHint) body.label_hint = labelHint;

    try {
      const response = await stream(GENERATE_PATH, {
        method: "POST",
        body,
        signal: controller.signal,
      });
      const draft = await readNdjson(response, {
        onProgress: (progressEvent) => status.progress(PROGRESS_MESSAGE, progressEvent),
      });

      onDraft(draftToPayload(draft));
      element.close();
      status.clear();
    } catch (error) {
      // An abort is the user's own decision, not a failure to report.
      if (controller.signal.aborted) return;
      status.text(
        "The draft could not be generated. Try again, or write the profile yourself — every field below is editable.",
        { error: true },
      );
    } finally {
      if (inFlight === controller) inFlight = null;
      setGenerating(false);
      status.workingVisible(false);
    }
  }

  return {
    element,

    /** @param {string} [hint] The label already typed, offered to the generator. */
    open(hint = "") {
      labelHint = String(hint || "").trim();
      status.clear();
      description.value = "";
      setGenerating(false);
      element.showModal();
      description.focus();
    },
  };
}

/**
 * The generator answers with a profile-shaped object, but nothing forces it to
 * be complete — a missing list must become an empty one rather than reach the
 * editor as `undefined` and silently drop the section.
 */
function draftToPayload(draft) {
  const source = draft && typeof draft === "object" ? draft : {};
  const object = (value) => (value && typeof value === "object" && !Array.isArray(value) ? value : {});
  const array = (value) => (Array.isArray(value) ? value : []);

  return {
    // A generator that named the profile but did not label it still gives the
    // user something to recognise; the id is derived from the label, not this.
    label: String(source.label || "").trim() || String(source.name || "").replace(/[-_]+/g, " ").trim(),
    default_question: String(source.default_question || "").trim(),
    concepts: array(source.concepts),
    query_groups: object(source.query_groups),
    off_topic_terms: array(source.off_topic_terms),
    journal_terms: array(source.journal_terms),
    term_groups: object(source.term_groups),
    intents: object(source.intents),
    buckets: array(source.buckets),
    extraction_fields: array(source.extraction_fields),
  };
}
