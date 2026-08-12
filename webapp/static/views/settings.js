/**
 * Search settings panel.
 *
 * Still an inline `<details>` inside the search view, as before. It is its own
 * module because §5 of the UI PRD moves it to `#/settings`, and a self-contained
 * panel with a `collect()` contract is a route away from that.
 *
 * Two states are kept apart on purpose: `settingsDefaults` is what the server
 * reports, `settings` is that with the user's saved overrides applied. The reset
 * buttons need the pristine copy, so overlaying in place would destroy it.
 */

import { h } from "../lib/dom.js";
import { request } from "../lib/api.js";
import { appStorage } from "../lib/storage.js";

const ALL_SOURCES = ["openalex", "crossref", "pubmed", "europepmc", "semantic_scholar"];

const FALLBACK_SETTINGS = {
  contact_email: "",
  api_keys: { openalex: "", semantic_scholar: "", ncbi: "" },
  search: {
    max_results_per_query: 10,
    max_queries_per_run: 12,
    concurrent_workers: 8,
    timeout_seconds: 20,
    enabled_sources: [...ALL_SOURCES],
  },
  selection: { top_n: 25 },
};

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @returns {{element: HTMLElement, load: function(): Promise<void>,
 *            collect: function(): Object, close: function(): void}}
 */
export function createSettingsPanel({ store }) {
  const basicGroup = h("div", { class: "settings-group", id: "basic-settings" });
  const advancedGroup = h("div", { class: "settings-group", id: "advanced-settings" });

  const advanced = h(
    "details",
    { class: "settings-advanced", id: "advanced-details" },
    h(
      "summary",
      null,
      h("span", { class: "settings-summary-label" }, "Advanced configuration"),
      h(
        "span",
        { class: "settings-summary-actions" },
        h("button", {
          type: "button",
          id: "reset-advanced-btn",
          class: "btn-ghost btn-small",
          onClick: (event) => {
            stopSummaryToggle(event);
            resetAdvanced();
          },
        }, "Reset"),
      ),
    ),
    advancedGroup,
  );

  const element = h(
    "details",
    { class: "panel settings-panel", id: "settings-details" },
    h(
      "summary",
      null,
      h("span", { class: "settings-summary-label" }, "Search settings"),
      h(
        "span",
        { class: "settings-summary-actions" },
        h("button", {
          type: "button",
          id: "reset-basic-btn",
          class: "btn-ghost btn-small",
          onClick: (event) => {
            stopSummaryToggle(event);
            resetBasic();
          },
        }, "Reset to defaults"),
      ),
    ),
    h("div", { class: "settings-body" }, basicGroup, advanced),
  );

  // Any edit anywhere in the panel is persisted; `input` covers typing and
  // `change` covers the checkboxes and the numeric stepper.
  element.addEventListener("change", persist);
  element.addEventListener("input", persist);

  function persist() {
    if (!store.get().settings) return;
    appStorage.write("settings", collect());
  }

  function collect() {
    const overrides = { search: {}, selection: {}, api_keys: {} };

    for (const control of element.querySelectorAll(".num-ctl[data-path]")) {
      const value = control.querySelector(".num-val");
      const input = control.querySelector(".num-inline");
      if (value) {
        setNestedPath(overrides, control.dataset.path, parseInt(value.textContent, 10));
      } else if (input) {
        setNestedPath(overrides, control.dataset.path, parseInt(input.value, 10));
      }
    }

    for (const input of element.querySelectorAll(".setting-text[data-path]")) {
      setNestedPath(overrides, input.dataset.path, input.value);
    }

    const sources = [...advancedGroup.querySelectorAll("input[data-source]")]
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => checkbox.dataset.source);
    if (sources.length) overrides.search.enabled_sources = sources;

    return overrides;
  }

  async function load() {
    let settings;
    try {
      settings = await request("/api/settings");
    } catch {
      // A settings fetch that failed must not take the search form with it.
      settings = FALLBACK_SETTINGS;
    }

    const defaults = structuredClone(settings);
    const saved = appStorage.read("settings", null);
    if (saved) deepMerge(settings, saved);

    store.set({ settings, settingsDefaults: defaults });
    build(settings);
  }

  function build(settings) {
    basicGroup.replaceChildren(
      settingRow("Max queries per run",
        numControl("search.max_queries_per_run", settings.search.max_queries_per_run, 1, 100, 1)),
      settingRow("Results per query",
        numControl("search.max_results_per_query", settings.search.max_results_per_query, 1, 100, 1)),
      settingRow("Selected papers",
        numControl("selection.top_n", settings.selection.top_n, 1, 100, 1)),
    );

    advancedGroup.replaceChildren(
      settingRow("Contact email",
        textControl("contact_email", settings.contact_email, "user@example.com")),
      settingRow("OpenAlex API key",
        textControl("api_keys.openalex", settings.api_keys?.openalex)),
      settingRow("Semantic Scholar key",
        textControl("api_keys.semantic_scholar", settings.api_keys?.semantic_scholar)),
      settingRow("NCBI API key",
        textControl("api_keys.ncbi", settings.api_keys?.ncbi)),
      settingRow("Concurrent workers",
        numControl("search.concurrent_workers", settings.search.concurrent_workers, 1, 24, 1)),
      settingRow("Timeout (seconds)",
        numControl("search.timeout_seconds", settings.search.timeout_seconds, 10, 100, 10)),
      settingRow("Sources", sourcesControl(settings.search.enabled_sources || ALL_SOURCES)),
    );
  }

  function setNumValue(path, value) {
    const control = element.querySelector(`.num-ctl[data-path="${path}"] .num-val`);
    if (!control) return;
    control.textContent = value;
    control.setAttribute("aria-valuenow", String(value));
  }

  function setTextValue(path, value) {
    const control = element.querySelector(`.setting-text[data-path="${path}"]`);
    if (control) control.value = value ?? "";
  }

  function resetBasic() {
    const defaults = store.get().settingsDefaults;
    if (!defaults) return;
    setNumValue("search.max_queries_per_run", defaults.search.max_queries_per_run);
    setNumValue("search.max_results_per_query", defaults.search.max_results_per_query);
    setNumValue("selection.top_n", defaults.selection.top_n);
    persist();
  }

  function resetAdvanced() {
    const defaults = store.get().settingsDefaults;
    if (!defaults) return;
    setNumValue("search.concurrent_workers", defaults.search.concurrent_workers);
    setNumValue("search.timeout_seconds", defaults.search.timeout_seconds);
    setTextValue("contact_email", defaults.contact_email);
    setTextValue("api_keys.openalex", defaults.api_keys?.openalex);
    setTextValue("api_keys.semantic_scholar", defaults.api_keys?.semantic_scholar);
    setTextValue("api_keys.ncbi", defaults.api_keys?.ncbi);

    const enabled = defaults.search.enabled_sources ?? ALL_SOURCES;
    for (const checkbox of advancedGroup.querySelectorAll("input[data-source]")) {
      checkbox.checked = enabled.includes(checkbox.dataset.source);
    }
    persist();
  }

  return {
    element,
    load,
    collect,
    close() {
      element.open = false;
    },
  };
}

function settingRow(labelText, control) {
  return h("div", { class: "setting-row" }, h("span", { class: "setting-label" }, labelText), control);
}

/** Inline-editable number with − / + buttons, exposed as an ARIA spinbutton. */
function numControl(path, value, min, max, step) {
  const valueSpan = h("span", {
    class: "num-val",
    title: "Click to edit",
    tabIndex: 0,
    role: "spinbutton",
    "aria-label": path.split(".").at(-1).replace(/_/g, " "),
    "aria-valuemin": String(min),
    "aria-valuemax": String(max),
    "aria-valuenow": String(value),
  }, String(value));

  const wrapper = h("div", { class: "num-ctl", dataset: { path } });
  let editing = false;

  const clamp = (candidate) => Math.min(max, Math.max(min, Number.isNaN(candidate) ? min : candidate));
  const current = () => parseInt(valueSpan.textContent, 10);

  function commitValue(next, source) {
    valueSpan.textContent = next;
    valueSpan.setAttribute("aria-valuenow", String(next));
    source.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function startEditing() {
    if (editing) return;
    editing = true;

    const input = h("input", {
      type: "number",
      class: "num-inline",
      min,
      max,
      step,
      value: current(),
    });

    function commit() {
      const next = clamp(parseInt(input.value, 10));
      input.replaceWith(valueSpan);
      editing = false;
      commitValue(next, valueSpan);
    }
    function cancel() {
      input.replaceWith(valueSpan);
      editing = false;
    }

    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      }
      if (event.key === "Escape") cancel();
    });

    valueSpan.replaceWith(input);
    input.focus();
    input.select();
  }

  valueSpan.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      startEditing();
    }
  });
  valueSpan.addEventListener("focus", startEditing);
  valueSpan.addEventListener("click", startEditing);

  wrapper.append(
    h("button", {
      type: "button",
      class: "num-btn",
      onClick: () => commitValue(clamp(current() - step), wrapper),
    }, "-"),
    valueSpan,
    h("button", {
      type: "button",
      class: "num-btn",
      onClick: () => commitValue(clamp(current() + step), wrapper),
    }, "+"),
  );
  return wrapper;
}

function textControl(path, value, placeholder) {
  return h("input", {
    type: "text",
    class: "setting-text",
    dataset: { path },
    value: value || "",
    placeholder: placeholder || null,
  });
}

function sourcesControl(enabled) {
  return h("div", { class: "sources-wrap" }, ALL_SOURCES.map((source) => h(
    "label",
    { class: "checkbox" },
    h("input", { type: "checkbox", dataset: { source }, checked: enabled.includes(source) }),
    ` ${source}`,
  )));
}

/** A button inside a `<summary>` would otherwise open or close the disclosure. */
function stopSummaryToggle(event) {
  event.preventDefault();
  event.stopPropagation();
}

/** `setNestedPath({}, "search.top_n", 5)` → `{search: {top_n: 5}}`. */
function setNestedPath(target, path, value) {
  const parts = path.split(".");
  let node = target;
  for (const part of parts.slice(0, -1)) {
    if (node[part] == null) node[part] = {};
    node = node[part];
  }
  node[parts.at(-1)] = value;
}

/** Deep-merge `source` into `target` in place. Arrays replace, never merge. */
function deepMerge(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (value === null || value === undefined) continue;
    if (typeof value === "object" && !Array.isArray(value)) {
      if (target[key] == null) target[key] = {};
      deepMerge(target[key], value);
    } else {
      target[key] = value;
    }
  }
}
