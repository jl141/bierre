/**
 * Profile editor dialog, plus the short "generate with AI" dialog.
 *
 * The markup stays in `index.html` and this module wires it, because U4 moves
 * the editor out of the `<dialog>` and onto `#/profiles/:id` — rebuilding it in
 * JavaScript first would be work thrown away twice.
 */

import { h } from "../lib/dom.js";
import { readNdjson, request, stream } from "../lib/api.js";
import { createStatus } from "./status.js";

const GENERATE_PATH = "/bierre-ca/api/profiles/generate";

/**
 * @param {Object} options
 * @param {{get: function(): Object}} options.store
 * @param {function(string): Promise<void>|void} options.onSaved Receives the id
 *   to select after a create or update.
 * @param {function(string): void} options.onError Page-level error reporting for
 *   failures that happen before the dialog is on screen.
 */
export function createProfileDialog({ store, onSaved, onError }) {
  const byId = (id) => document.getElementById(id);

  const modal = byId("profile-modal");
  const form = byId("profile-form");
  const title = byId("profile-modal-title");
  const closeButton = byId("profile-modal-close");
  const saveButton = byId("profile-save-btn");
  const formStatus = createStatus(byId("profile-form-status"));
  const aiOpenButton = byId("profile-ai-open-btn");

  const aiModal = byId("profile-ai-modal");
  const aiForm = byId("profile-ai-form");
  const aiCloseButton = byId("profile-ai-close");
  const aiGenerateButton = byId("profile-ai-generate-btn");
  const aiStatus = createStatus(byId("profile-ai-status"));
  const aiResearchInput = byId("profile-ai-research");

  const labelInput = byId("profile-label");
  const defaultQuestionInput = byId("profile-default-question");
  const offTopicInput = byId("profile-off-topic");
  const journalTermsInput = byId("profile-journal-terms");
  const termGroupsInput = byId("profile-term-groups");
  const bucketsInput = byId("profile-buckets");
  const extractionInput = byId("profile-extraction-fields");

  const sections = {
    concepts: {
      listEl: byId("profile-concepts-list"),
      addBtn: byId("profile-concepts-add"),
      emptyItem: () => ({ name: "", triggers: [], terms: [] }),
      fields: [
        { key: "name", label: "Concept name", type: "input", placeholder: "e.g. N-halamine coatings" },
        { key: "triggers", label: "Triggers", type: "textarea", rows: 2, className: "profile-subfield-compact", placeholder: "term, phrase" },
        { key: "terms", label: "Terms", type: "textarea", rows: 2, className: "profile-subfield-compact", placeholder: "expanded term, synonym" },
      ],
      normalize(value) {
        return Array.isArray(value)
          ? value.map((item) => ({
              name: String(item?.name || "").trim(),
              triggers: Array.isArray(item?.triggers) ? item.triggers : [],
              terms: Array.isArray(item?.terms) ? item.terms : [],
            }))
          : [];
      },
      serialize(items) {
        return items
          .map((item) => ({
            name: String(item.name || "").trim(),
            triggers: parseCommaList(item.triggers),
            terms: parseCommaList(item.terms),
          }))
          .filter((item) => item.name || item.triggers.length || item.terms.length);
      },
      format(field, value) {
        return field.key === "name" ? String(value || "") : listToCommaText(value);
      },
    },
    queryGroups: {
      listEl: byId("profile-query-groups-list"),
      addBtn: byId("profile-query-groups-add"),
      emptyItem: () => ({ name: "", queries: [] }),
      fields: [
        { key: "name", label: "Group name", type: "input", placeholder: "e.g. mechanism" },
        { key: "queries", label: "Queries", type: "textarea", rows: 2, className: "profile-subfield-wide", placeholder: "One query per line" },
      ],
      normalize(value) {
        if (typeof value !== "object" || value == null || Array.isArray(value)) return [];
        return Object.entries(value).map(([name, queries]) => ({
          name,
          queries: Array.isArray(queries) ? queries : [],
        }));
      },
      serialize(items) {
        const pairs = items
          .map((item) => ({
            name: String(item.name || "").trim(),
            queries: parseLineList(item.queries),
          }))
          .filter((item) => item.name || item.queries.length)
          .map((item) => [item.name, item.queries]);
        return Object.fromEntries(pairs.filter(([name]) => name));
      },
      format(field, value) {
        return field.key === "name" ? String(value || "") : listToLines(value);
      },
    },
    intents: {
      listEl: byId("profile-intents-list"),
      addBtn: byId("profile-intents-add"),
      emptyItem: () => ({ name: "", terms: [] }),
      fields: [
        { key: "name", label: "Intent name", type: "input", placeholder: "e.g. antimicrobial" },
        { key: "terms", label: "Target terms", type: "textarea", rows: 2, className: "profile-subfield-wide", placeholder: "antibacterial, biofilm" },
      ],
      normalize(value) {
        if (typeof value !== "object" || value == null || Array.isArray(value)) return [];
        return Object.entries(value).map(([name, terms]) => ({
          name,
          terms: Array.isArray(terms) ? terms : [],
        }));
      },
      serialize(items) {
        const pairs = items
          .map((item) => ({
            name: String(item.name || "").trim(),
            terms: parseCommaList(item.terms),
          }))
          .filter((item) => item.name || item.terms.length)
          .map((item) => [item.name, item.terms]);
        return Object.fromEntries(pairs.filter(([name]) => name));
      },
      format(field, value) {
        return field.key === "name" ? String(value || "") : listToCommaText(value);
      },
    },
  };

  let mode = "create";
  let editingProfileId = null;
  let generating = false;

  // --- structured list sections ----------------------------------------------

  function createItem(section, initialValue) {
    const body = h("div", {
      class: `profile-item-body${section.addBtn?.id ? ` ${section.addBtn.id}-body` : ""}`,
    }, section.fields.map((field) => createField(field, section.format(field, initialValue[field.key]))));

    const item = h("div", { class: "profile-item" });
    item.append(body, h("button", {
      type: "button",
      class: "btn-icon btn-danger profile-item-remove",
      "aria-label": "Remove item",
      title: "Remove item",
      onClick: () => item.remove(),
    }, "x"));
    return item;
  }

  function createField(field, value) {
    const control = h(field.type === "textarea" ? "textarea" : "input", {
      class: "profile-item-input",
      dataset: { field: field.key, ...(field.type === "textarea" ? { autosize: "profile" } : {}) },
      type: field.type === "textarea" ? null : "text",
      rows: field.type === "textarea" ? field.rows || 3 : null,
      placeholder: field.placeholder || null,
      value,
    });

    return h(
      "label",
      { class: `profile-subfield${field.className ? ` ${field.className}` : ""}` },
      h("span", { class: "profile-subfield-label" }, field.label),
      control,
    );
  }

  function renderSection(section, values) {
    section.listEl.replaceChildren(...values.map((value) => createItem(section, value)));
  }

  function appendItem(section) {
    const item = createItem(section, section.emptyItem());
    section.listEl.append(item);
    autosizeAll();
    item.querySelector("input, textarea")?.focus();
  }

  function collectItems(section) {
    return [...section.listEl.querySelectorAll(".profile-item")].map((item) => {
      const entry = {};
      for (const field of item.querySelectorAll("[data-field]")) {
        entry[field.dataset.field] = field.value;
      }
      return entry;
    });
  }

  function autosizeAll() {
    for (const textarea of form.querySelectorAll("textarea")) autosize(textarea);
  }

  // --- form state --------------------------------------------------------------

  function resetForm(profile) {
    labelInput.value = profile.label || "";
    defaultQuestionInput.value = profile.default_question || "";
    renderSection(sections.concepts, sections.concepts.normalize(profile.concepts));
    renderSection(sections.queryGroups, sections.queryGroups.normalize(profile.query_groups));
    offTopicInput.value = listToLines(profile.off_topic_terms);
    journalTermsInput.value = listToLines(profile.journal_terms);
    renderSection(sections.intents, sections.intents.normalize(profile.intents));
    termGroupsInput.value = prettyJson(profile.term_groups, {});
    bucketsInput.value = prettyJson(profile.buckets, []);
    extractionInput.value = prettyJson(profile.extraction_fields, []);
    autosizeAll();
    formStatus.clear();
  }

  function collectPayload() {
    const label = String(labelInput.value || "").trim();
    if (!label) throw new Error("Profile label is required.");

    const termGroups = parseJsonField(termGroupsInput.value, {}, "Term groups");
    const buckets = parseJsonField(bucketsInput.value, [], "Buckets");
    const extractionFields = parseJsonField(extractionInput.value, [], "Extraction fields");

    ensureType(termGroups, "object", "Term groups");
    ensureType(buckets, "array", "Buckets");
    ensureType(extractionFields, "array", "Extraction fields");

    return {
      label,
      default_question: String(defaultQuestionInput.value || "").trim(),
      concepts: sections.concepts.serialize(collectItems(sections.concepts)),
      query_groups: sections.queryGroups.serialize(collectItems(sections.queryGroups)),
      off_topic_terms: parseDelimitedList(offTopicInput.value),
      journal_terms: parseDelimitedList(journalTermsInput.value),
      intents: sections.intents.serialize(collectItems(sections.intents)),
      term_groups: termGroups,
      buckets,
      extraction_fields: extractionFields,
    };
  }

  async function save(event) {
    event.preventDefault();
    try {
      const payload = collectPayload();
      saveButton.disabled = true;

      let selectedAfterSave;
      if (mode === "edit" && editingProfileId) {
        await request(profilePath(editingProfileId), { method: "PUT", body: payload });
        selectedAfterSave = editingProfileId;
      } else {
        const created = await request("/api/profiles", { method: "POST", body: payload });
        selectedAfterSave = created.id;
      }

      await onSaved(selectedAfterSave);
      close();
    } catch (error) {
      formStatus.text(`Error: ${error.message}`, { error: true });
    } finally {
      saveButton.disabled = false;
    }
  }

  function open() {
    modal.showModal();
    // Textareas can only be sized once they have been laid out.
    requestAnimationFrame(autosizeAll);
    labelInput.focus();
  }

  function close() {
    if (generating) return;
    if (aiModal.open) aiModal.close();
    modal.close();
    formStatus.clear();
  }

  // --- AI draft ----------------------------------------------------------------

  function setAiLocked(locked) {
    generating = locked;
    aiGenerateButton.disabled = locked;
    aiCloseButton.disabled = locked;
    aiResearchInput.disabled = locked;
    aiOpenButton.disabled = locked;
    closeButton.disabled = locked;
  }

  function openAi() {
    if (generating) return;
    aiStatus.clear();
    aiResearchInput.value = "";
    aiModal.showModal();
    requestAnimationFrame(() => aiResearchInput.focus());
  }

  function closeAi() {
    if (generating) return;
    aiModal.close();
    aiStatus.clear();
  }

  async function generate(event) {
    event.preventDefault();
    const researchDescription = String(aiResearchInput.value || "").trim();
    if (!researchDescription) {
      aiStatus.text("Research description is required.", { error: true });
      return;
    }

    const labelHint = String(labelInput.value || "").trim();
    const body = { research_description: researchDescription };
    if (labelHint) body.label_hint = labelHint;

    const baseMessage = "Generating profile draft...";
    setAiLocked(true);
    aiStatus.progress(baseMessage, { step: 0, total: 0, label: "Starting..." });

    try {
      const response = await stream(GENERATE_PATH, { method: "POST", body });
      const draft = await readNdjson(response, {
        onProgress: (progressEvent) => aiStatus.progress(baseMessage, progressEvent),
      });

      applyDraft(draft);
      // Only close on success: closing on failure would take the explanation
      // with it, which is what the single-file version did.
      closeAiAfterSuccess();
    } catch (error) {
      aiStatus.text(`Error: ${error.message}`, { error: true });
    } finally {
      aiStatus.workingVisible(false);
      setAiLocked(false);
    }
  }

  function closeAiAfterSuccess() {
    aiModal.close();
    aiStatus.clear();
    formStatus.text("AI profile draft loaded. Review and save.");
    labelInput.focus();
  }

  function applyDraft(draft) {
    resetForm({ ...profileTemplate(), ...normalizeDraft(draft) });
    if (!labelInput.value && draft?.name) {
      labelInput.value = String(draft.name).replace(/[-_]+/g, " ");
    }
    autosizeAll();
  }

  // --- wiring --------------------------------------------------------------------

  for (const section of Object.values(sections)) {
    section.addBtn.addEventListener("click", () => appendItem(section));
  }

  form.addEventListener("submit", save);
  form.addEventListener("input", (event) => {
    if (event.target instanceof HTMLTextAreaElement) autosize(event.target);
  });
  closeButton.addEventListener("click", close);
  modal.addEventListener("cancel", (event) => {
    if (generating) {
      event.preventDefault();
      return;
    }
    formStatus.clear();
  });
  modal.addEventListener("close", () => hideTip());

  aiOpenButton.addEventListener("click", openAi);
  aiForm.addEventListener("submit", generate);
  aiCloseButton.addEventListener("click", closeAi);
  aiModal.addEventListener("cancel", (event) => {
    if (generating) {
      event.preventDefault();
      return;
    }
    aiStatus.clear();
  });

  const hideTip = initTooltips(modal);

  return {
    openCreate() {
      mode = "create";
      editingProfileId = null;
      title.textContent = "Create profile";
      aiOpenButton.hidden = false;
      saveButton.textContent = "Create profile";
      resetForm(profileTemplate());
      open();
    },

    async openEdit(profileId) {
      if (!profileId) return;
      try {
        const data = await request(profilePath(profileId));
        mode = "edit";
        editingProfileId = profileId;
        title.textContent = `Edit profile: ${labelOf(store, profileId)}`;
        aiOpenButton.hidden = true;
        saveButton.textContent = "Save changes";
        resetForm(data.profile || profileTemplate());
        open();
      } catch (error) {
        onError(`Error: ${error.message}`);
      }
    },
  };
}

// --- helpers -------------------------------------------------------------------

function profilePath(profileId) {
  return `/api/profiles/${encodeURIComponent(profileId)}`;
}

function labelOf(store, profileId) {
  return store.get().profiles.find((item) => item.id === profileId)?.label || profileId;
}

function profileTemplate() {
  return {
    label: "",
    default_question: "",
    concepts: null,
    query_groups: null,
    off_topic_terms: null,
    journal_terms: null,
    intents: null,
    term_groups: null,
    buckets: [
      { id: "all", label: "Relevant", boost: 0.0, fallback: true },
    ],
    extraction_fields: null,
  };
}

function normalizeDraft(draft) {
  const object = (value) => (typeof value === "object" && value && !Array.isArray(value) ? value : {});
  const array = (value) => (Array.isArray(value) ? value : []);

  return {
    label: String(draft?.label || "").trim(),
    default_question: String(draft?.default_question || "").trim(),
    concepts: array(draft?.concepts),
    query_groups: object(draft?.query_groups),
    off_topic_terms: array(draft?.off_topic_terms),
    journal_terms: array(draft?.journal_terms),
    intents: object(draft?.intents),
    term_groups: object(draft?.term_groups),
    buckets: array(draft?.buckets),
    extraction_fields: array(draft?.extraction_fields),
  };
}

function autosize(textarea) {
  if (!(textarea instanceof HTMLTextAreaElement)) return;
  textarea.style.overflowY = "hidden";
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

function parseDelimitedList(value) {
  return String(value || "").split(/\n|,/).map((part) => part.trim()).filter(Boolean);
}

function parseCommaList(value) {
  return String(value || "").split(",").map((part) => part.trim()).filter(Boolean);
}

function parseLineList(value) {
  return String(value || "").split("\n").map((part) => part.trim()).filter(Boolean);
}

function listToLines(values) {
  return Array.isArray(values) ? values.map(String).join("\n") : "";
}

function listToCommaText(values) {
  return Array.isArray(values) ? values.map(String).join(", ") : "";
}

function prettyJson(value, fallback) {
  return JSON.stringify(value == null ? fallback : value, null, 2);
}

function parseJsonField(raw, fallback, label) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
}

function ensureType(value, expected, label) {
  if (expected === "array" && !Array.isArray(value)) {
    throw new Error(`${label} must be a JSON array.`);
  }
  if (expected === "object" && (typeof value !== "object" || value == null || Array.isArray(value))) {
    throw new Error(`${label} must be a JSON object.`);
  }
}

/**
 * The `?` hover tips. Unchanged behaviour: the a11y rebuild (a real toggle
 * button with `aria-expanded` and `aria-describedby`) is UI PRD §8.3, phase 1.
 *
 * @returns {function(HTMLElement=): void} `hideTip`, for the dialog's close.
 */
function initTooltips(root) {
  const tip = h("div", { class: "hover-tip", hidden: true });
  root.append(tip);
  let anchor = null;

  function position(target) {
    const margin = 8;
    const rect = target.getBoundingClientRect();

    tip.style.left = "0px";
    tip.style.top = "0px";
    const tipRect = tip.getBoundingClientRect();

    const centeredX = rect.left + rect.width / 2 - tipRect.width / 2;
    const x = clamp(centeredX, margin, window.innerWidth - tipRect.width - margin);
    const preferredTop = rect.top - tipRect.height - margin;
    const top = preferredTop >= margin
      ? preferredTop
      : clamp(rect.bottom + margin, margin, window.innerHeight - tipRect.height - margin);

    tip.style.left = `${Math.round(x)}px`;
    tip.style.top = `${Math.round(top)}px`;
  }

  function show(target) {
    const text = String(target.dataset.tip || "").trim();
    if (!text) return;
    anchor = target;
    tip.textContent = text;
    tip.hidden = false;
    position(target);
  }

  function hide(target) {
    if (target && anchor !== target) return;
    anchor = null;
    tip.hidden = true;
    tip.textContent = "";
  }

  for (const target of root.querySelectorAll(".tip[data-tip]")) {
    target.addEventListener("mouseenter", () => show(target));
    target.addEventListener("mouseleave", () => hide(target));
    target.addEventListener("focus", () => show(target));
    target.addEventListener("blur", () => hide(target));
  }

  window.addEventListener("scroll", () => anchor && position(anchor), true);
  window.addEventListener("resize", () => anchor && position(anchor));

  return hide;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
