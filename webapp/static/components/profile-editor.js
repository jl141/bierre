/**
 * The domain-profile form.
 *
 * This is the editor UI PRD §6.2 asks for, in three respects:
 *
 * 1. **It is not in a `<dialog>` any more.** Fifteen fields with nested
 *    disclosures do not fit a modal with internal scroll, and a modal cannot be
 *    deep-linked — profiles get shared between lab members ("use my profile for
 *    the antimicrobial review"), so the editor is a route and this is the
 *    component it mounts.
 * 2. **Term groups, buckets and extraction fields are structured.** They were
 *    raw JSON `<textarea>`s, which asked a biologist to hand-write
 *    `[{"id":"core","boost":15,"requires":["signal"]}]`. Every field in the
 *    payload now has a real control, so a profile can be authored without
 *    knowing that the transport is JSON.
 * 3. **The `?` hover tips are gone, not ported.** They were `<span
 *    role="button">`s that only revealed their text on hover, which is unusable
 *    on a touch device and invisible to a screen reader that is not tracking the
 *    pointer. On a full-width page there is room for the same sentences as
 *    permanent hint text, tied to their control with `aria-describedby` — which
 *    is both simpler and the accessible version of what the tips were for.
 *
 * The component owns no network calls and no routing: it renders a payload, it
 * hands one back, and it throws a plain-language `Error` when what is on screen
 * cannot be turned into one. `bierre-ca` re-validates everything.
 */

import { clear, h } from "../lib/dom.js";
import { emptyProfile } from "../lib/profile-file.js";

/**
 * How one control converts between a payload value and its input value. Parsing
 * is total: it either returns a value or throws a sentence a user can act on.
 */
const CONTROL_TYPES = {
  text: {
    tag: "input",
    read: (value) => stringOf(value),
    parse: (raw) => raw.trim(),
    isEmpty: (value) => value === "",
  },
  number: {
    tag: "input",
    read: (value) => (value == null || value === "" ? "" : String(value)),
    parse: (raw, field) => {
      if (raw.trim() === "") return 0;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) throw new Error(`${field.label} must be a number.`);
      return parsed;
    },
    isEmpty: (value) => value === 0,
  },
  checkbox: {
    tag: "input",
    read: (value) => Boolean(value),
    parse: (raw) => raw === true,
    isEmpty: (value) => value === false,
  },
  comma: {
    tag: "textarea",
    read: (value) => listOf(value).join(", "),
    parse: (raw) => splitOn(raw, /,/),
    isEmpty: (value) => value.length === 0,
  },
  lines: {
    tag: "textarea",
    read: (value) => listOf(value).join("\n"),
    parse: (raw) => splitOn(raw, /\n/),
    isEmpty: (value) => value.length === 0,
  },
};

/**
 * The repeating sections, in the order the form presents them.
 *
 * `shape: "list"` maps onto an array of objects in the payload; `shape: "map"`
 * maps onto `{name: [terms]}`, where the first control *is* the key. Both are
 * rendered by the same code, which is what keeps the six sections consistent
 * with each other rather than each growing its own quirks.
 */
const SECTIONS = [
  {
    key: "concepts",
    shape: "list",
    panel: "expansion",
    title: "Concepts",
    singular: "concept",
    hint: "A concept fires when the question mentions one of its triggers, and then adds its terms to the searches. Keep triggers to the words a researcher would actually type; put synonyms and abbreviations in terms.",
    fields: [
      { key: "name", label: "Concept name", type: "text", placeholder: "e.g. N-halamine coatings" },
      { key: "triggers", label: "Triggers", type: "comma", rows: 2, placeholder: "n-halamine, hydantoin", hint: "Comma separated." },
      { key: "terms", label: "Terms added to searches", type: "comma", rows: 2, placeholder: "n-halamine, halamine, chloramine", hint: "Comma separated." },
    ],
  },
  {
    key: "query_groups",
    shape: "map",
    panel: "expansion",
    title: "Query groups",
    singular: "query group",
    hint: "Searches that run whenever any concept is active. Groups only organise them for you — results are not separated by group.",
    fields: [
      { key: "name", label: "Group name", type: "text", placeholder: "e.g. mechanism" },
      { key: "queries", label: "Queries", type: "lines", rows: 3, placeholder: "One query per line", hint: "One per line.", wide: true },
    ],
  },
  {
    key: "intents",
    shape: "map",
    panel: "relevance",
    title: "Intents",
    singular: "intent",
    hint: "What a good paper should be about. Keep the terms action-oriented — inhibition, induction, persistence — rather than naming the material again.",
    fields: [
      { key: "name", label: "Intent name", type: "text", placeholder: "e.g. antimicrobial" },
      { key: "terms", label: "Target terms", type: "comma", rows: 2, placeholder: "antibacterial, biofilm", hint: "Comma separated.", wide: true },
    ],
  },
  {
    key: "term_groups",
    shape: "map",
    panel: "advanced",
    title: "Term groups",
    singular: "term group",
    hint: "Named vocabulary sets that buckets test against. Splitting them by role — signal, matrix, function — is what lets a bucket require one without requiring the others.",
    fields: [
      { key: "name", label: "Group name", type: "text", placeholder: "e.g. signal" },
      { key: "terms", label: "Terms", type: "comma", rows: 2, placeholder: "n-halamine, hydantoin", hint: "Comma separated.", wide: true },
    ],
  },
  {
    key: "buckets",
    shape: "list",
    panel: "advanced",
    title: "Buckets",
    singular: "bucket",
    hint: "Relevance categories, tested in order: the first match wins, so put the strict ones first and end with one fallback that catches everything else. Boost moves a paper up or down the ranking.",
    fields: [
      { key: "id", label: "Id", type: "text", placeholder: "core", hint: "Lowercase, no spaces." },
      { key: "label", label: "Shown as", type: "text", placeholder: "Core" },
      { key: "boost", label: "Boost", type: "number", step: "0.5", placeholder: "15" },
      { key: "requires", label: "Requires term groups", type: "comma", rows: 2, placeholder: "signal, function", hint: "Comma separated." },
      { key: "exclude_off_topic", label: "Exclude off-topic papers", type: "checkbox" },
      { key: "fallback", label: "Fallback (catches the rest)", type: "checkbox" },
    ],
  },
  {
    key: "extraction_fields",
    shape: "list",
    panel: "advanced",
    title: "Extraction fields",
    singular: "extraction field",
    hint: "Columns of the evidence table. Turn on “needs a number” for measured quantities — active chlorine %, log reduction, recharge cycles — so a sentence that only mentions the topic is not extracted as a result.",
    fields: [
      { key: "name", label: "Column name", type: "text", placeholder: "Active chlorine" },
      { key: "terms", label: "Sentence must mention", type: "comma", rows: 2, placeholder: "active chlorine, cl+", hint: "Comma separated." },
      { key: "require_numeric", label: "Needs a number", type: "checkbox" },
    ],
  },
];

const PANEL_TITLES = {
  expansion: "Search expansion",
  relevance: "Relevance and scoring",
};

/**
 * @returns {{element: HTMLElement,
 *            load: function(Object): void,
 *            collect: function(): Object,
 *            setReadOnly: function(boolean): void,
 *            setBusy: function(boolean): void,
 *            focusFirstField: function(): void}}
 */
export function createProfileEditor() {
  let readOnly = false;

  const labelInput = h("input", {
    id: "editor-label",
    name: "label",
    type: "text",
    required: true,
    maxLength: 200,
    "aria-describedby": "editor-label-hint",
    placeholder: "e.g. N-halamine antimicrobial coatings",
  });

  const defaultQuestionInput = h("textarea", {
    id: "editor-default-question",
    name: "default_question",
    rows: 2,
    "aria-describedby": "editor-default-question-hint",
    placeholder: "Optional. Used when the search box is left empty.",
  });

  const offTopicInput = h("textarea", {
    id: "editor-off-topic",
    name: "off_topic_terms",
    rows: 4,
    "aria-describedby": "editor-off-topic-hint",
    placeholder: "e.g. silver\ngold",
  });

  const journalTermsInput = h("textarea", {
    id: "editor-journal-terms",
    name: "journal_terms",
    rows: 4,
    "aria-describedby": "editor-journal-terms-hint",
    placeholder: "e.g. nature\nscience",
  });

  const sections = new Map(SECTIONS.map((spec) => [spec.key, createSection(spec)]));

  const element = h(
    "div",
    { class: "profile-editor" },
    panel(
      "Basics",
      fieldBlock({
        id: "editor-label",
        label: "Label",
        control: labelInput,
        hint: "The name you will see in the profile dropdown.",
      }),
      fieldBlock({
        id: "editor-default-question",
        label: "Default question",
        control: defaultQuestionInput,
        hint: "Runs when the search box is empty. Keep it specific enough to be a real question about your topic.",
      }),
    ),
    panel(
      PANEL_TITLES.expansion,
      sections.get("concepts").element,
      sections.get("query_groups").element,
    ),
    panel(
      PANEL_TITLES.relevance,
      fieldBlock({
        id: "editor-off-topic",
        label: "Off-topic terms",
        control: offTopicInput,
        hint: "One per line. These push a paper down, so only true distractors belong here — a borderline-relevant term costs you real results.",
      }),
      fieldBlock({
        id: "editor-journal-terms",
        label: "Journal terms",
        control: journalTermsInput,
        hint: "One per line. Papers from journals whose name contains one of these get a small boost.",
      }),
      sections.get("intents").element,
    ),
    h(
      "details",
      { class: "panel profile-advanced-panel" },
      h("summary", null, "Advanced: term groups, buckets and extraction fields"),
      h(
        "div",
        { class: "profile-advanced-body" },
        h(
          "p",
          { class: "field-hint" },
          "These three decide how a paper is classified and what is pulled out of it. The defaults work; tune them once you have seen a run.",
        ),
        sections.get("term_groups").element,
        sections.get("buckets").element,
        sections.get("extraction_fields").element,
      ),
    ),
  );

  // One listener for the whole form rather than one per textarea, and it also
  // covers the textareas that sections create later.
  element.addEventListener("input", (event) => {
    if (event.target instanceof HTMLTextAreaElement) autosize(event.target);
  });

  function load(profile) {
    const payload = { ...emptyProfile(), ...(profile || {}) };
    labelInput.value = stringOf(payload.label);
    defaultQuestionInput.value = stringOf(payload.default_question);
    offTopicInput.value = listOf(payload.off_topic_terms).join("\n");
    journalTermsInput.value = listOf(payload.journal_terms).join("\n");
    for (const [key, section] of sections) section.load(payload[key]);
    // Textareas can only be measured once they are laid out.
    requestAnimationFrame(() => autosizeAll(element));
  }

  function collect() {
    const label = labelInput.value.trim();
    if (!label) {
      labelInput.focus();
      throw new Error("A profile needs a label.");
    }

    const payload = {
      label,
      default_question: defaultQuestionInput.value.trim(),
      off_topic_terms: splitOn(offTopicInput.value, /\n/),
      journal_terms: splitOn(journalTermsInput.value, /\n/),
    };
    for (const [key, section] of sections) payload[key] = section.collect();
    return payload;
  }

  function setReadOnly(nextReadOnly) {
    readOnly = nextReadOnly;
    for (const control of element.querySelectorAll("input, textarea")) {
      if (control.type === "checkbox" || control.type === "number") {
        control.disabled = readOnly;
      } else {
        control.readOnly = readOnly;
      }
    }
    for (const button of element.querySelectorAll("button")) button.hidden = readOnly;
    element.classList.toggle("is-read-only", readOnly);
  }

  return {
    element,
    load,
    collect,
    setReadOnly,

    /** Locks the form while a save is in flight, without changing read-only. */
    setBusy(busy) {
      for (const control of element.querySelectorAll("input, textarea, button")) {
        control.disabled = busy || (readOnly && (control.type === "checkbox" || control.type === "number"));
      }
    },

    focusFirstField() {
      labelInput.focus();
    },
  };
}

// --- repeating sections ------------------------------------------------------

function createSection(spec) {
  const listId = `editor-${spec.key}-list`;
  const hintId = `editor-${spec.key}-hint`;

  const list = h("div", {
    id: listId,
    class: "profile-list",
    // An added or removed row is announced, which is the only feedback a
    // non-sighted user gets that the button did anything.
    "aria-live": "polite",
  });

  const addButton = h(
    "button",
    {
      type: "button",
      class: "btn-ghost btn-small",
      onClick: () => {
        const item = createItem(spec, {});
        list.append(item);
        autosizeAll(item);
        item.querySelector("input, textarea")?.focus();
      },
    },
    `Add ${spec.singular}`,
  );

  const element = h(
    "section",
    { class: "profile-section", "aria-labelledby": `${listId}-title` },
    h(
      "div",
      { class: "profile-section-head" },
      h("h3", { class: "profile-section-title", id: `${listId}-title` }, spec.title),
      addButton,
    ),
    h("p", { class: "field-hint", id: hintId }, spec.hint),
    list,
    h("p", { class: "profile-section-empty", hidden: true }, `No ${spec.singular}s yet.`),
  );

  const emptyNote = element.querySelector(".profile-section-empty");

  function syncEmptyNote() {
    emptyNote.hidden = list.children.length > 0;
  }

  list.addEventListener("profile-item-removed", syncEmptyNote);

  return {
    element,

    load(value) {
      clear(list);
      for (const record of toRecords(spec, value)) list.append(createItem(spec, record));
      syncEmptyNote();
    },

    collect() {
      const records = [...list.querySelectorAll(".profile-item")].map((item) => readItem(spec, item));
      return fromRecords(spec, records);
    },
  };
}

function createItem(spec, record) {
  const item = h("div", { class: "profile-item" });

  const controls = spec.fields.map((field) => createControl(field, record[field.key]));
  const body = h("div", { class: "profile-item-body" }, controls);

  const remove = h(
    "button",
    {
      type: "button",
      class: "btn-ghost btn-small profile-item-remove",
      onClick: () => {
        const list = item.parentElement;
        item.remove();
        list?.dispatchEvent(new CustomEvent("profile-item-removed", { bubbles: true }));
        // Focus would otherwise land on <body>, which drops a keyboard user at
        // the top of the document.
        list?.parentElement?.querySelector(".profile-section-head button")?.focus();
      },
    },
    "Remove",
  );

  // The accessible name says *which* row this removes, and keeps saying it as
  // the row is filled in — "Remove" six times over is not a usable list.
  const nameControl = body.querySelector("input[type='text']");
  const describeRemove = () => {
    const name = nameControl?.value.trim();
    remove.setAttribute("aria-label", name ? `Remove ${spec.singular} ${name}` : `Remove this ${spec.singular}`);
  };
  nameControl?.addEventListener("input", describeRemove);
  describeRemove();

  item.append(body, remove);
  return item;
}

function createControl(field, value) {
  const type = CONTROL_TYPES[field.type];
  const isCheckbox = field.type === "checkbox";
  const controlId = `editor-field-${field.key}-${nextControlId()}`;
  const hintId = field.hint ? `${controlId}-hint` : null;

  const control = h(type.tag, {
    id: controlId,
    class: "profile-item-input",
    dataset: { field: field.key },
    type: type.tag === "input" ? (isCheckbox ? "checkbox" : field.type === "number" ? "number" : "text") : null,
    step: field.step || null,
    rows: type.tag === "textarea" ? field.rows || 2 : null,
    placeholder: field.placeholder || null,
    "aria-describedby": hintId,
    checked: isCheckbox ? type.read(value) : null,
    value: isCheckbox ? null : type.read(value),
  });

  const classes = ["profile-subfield"];
  if (field.wide) classes.push("profile-subfield-wide");
  if (isCheckbox) classes.push("profile-subfield-check");

  return h(
    "div",
    { class: classes.join(" ") },
    isCheckbox
      ? h("label", { class: "checkbox", for: controlId }, control, ` ${field.label}`)
      : [h("label", { for: controlId }, field.label), control],
    hintId ? h("p", { class: "field-hint", id: hintId }, field.hint) : null,
  );
}

function readItem(spec, item) {
  const record = {};
  for (const field of spec.fields) {
    const control = item.querySelector(`[data-field="${field.key}"]`);
    const type = CONTROL_TYPES[field.type];
    const raw = field.type === "checkbox" ? control.checked : control.value;
    record[field.key] = type.parse(raw, field);
  }
  return record;
}

/** Payload value → the records the rows are built from. */
function toRecords(spec, value) {
  if (spec.shape === "map") {
    if (!isPlainObject(value)) return [];
    const [, valueField] = spec.fields;
    return Object.entries(value).map(([name, entries]) => ({ name, [valueField.key]: entries }));
  }
  return Array.isArray(value) ? value.filter(isPlainObject) : [];
}

/** Records → payload value, dropping rows the user left blank. */
function fromRecords(spec, records) {
  const meaningful = records.filter((record) =>
    spec.fields.some((field) => !CONTROL_TYPES[field.type].isEmpty(record[field.key])),
  );

  if (spec.shape === "map") {
    const [, valueField] = spec.fields;
    // A nameless row has nowhere to live in a mapping, so it is dropped rather
    // than saved under "" — the server would reject the empty key anyway.
    return Object.fromEntries(
      meaningful.filter((record) => record.name).map((record) => [record.name, record[valueField.key]]),
    );
  }
  return meaningful;
}

// --- small helpers -----------------------------------------------------------

function panel(title, ...children) {
  return h("section", { class: "panel profile-panel" }, h("h2", { class: "panel-title" }, title), children);
}

function fieldBlock({ id, label, control, hint }) {
  return h(
    "div",
    { class: "field-block" },
    h("label", { for: id }, label),
    control,
    h("p", { class: "field-hint", id: `${id}-hint` }, hint),
  );
}

let controlSequence = 0;
function nextControlId() {
  controlSequence += 1;
  return controlSequence;
}

function autosize(textarea) {
  textarea.style.overflowY = "hidden";
  textarea.style.blockSize = "auto";
  textarea.style.blockSize = `${textarea.scrollHeight}px`;
}

function autosizeAll(root) {
  for (const textarea of root.querySelectorAll("textarea")) autosize(textarea);
}

function stringOf(value) {
  return value == null ? "" : String(value);
}

function listOf(value) {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function splitOn(raw, separator) {
  return String(raw || "")
    .split(separator)
    .map((part) => part.trim())
    .filter(Boolean);
}

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
