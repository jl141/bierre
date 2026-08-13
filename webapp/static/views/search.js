/**
 * Search view: the question form, the profile picker, the settings panel and
 * the results table. The `#/` route.
 */

import { h } from "../lib/dom.js";
import { readNdjson, request, stream } from "../lib/api.js";
import { appStorage } from "../lib/storage.js";
import { createStatus } from "../components/status.js";
import { createProfileDialog } from "../components/profile-dialog.js";
import { createResultsPanel } from "./results.js";
import { createSettingsPanel } from "./settings.js";

const QUESTION_PLACEHOLDER =
  "e.g. What evidence is there to support the sentience or consciousness of fish?";

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createSearchView({ store }) {
  let element = null;
  let status = null;
  let results = null;
  let settingsPanel = null;
  let dialog = null;

  const questionInput = h("textarea", {
    id: "question",
    name: "question",
    rows: 2,
    placeholder: QUESTION_PLACEHOLDER,
    onInput: saveQueryState,
  });

  const profileSelect = h("select", {
    id: "profile",
    name: "profile",
    onChange: () => {
      saveQueryState();
      updateProfileActions();
    },
  });

  const offlineInput = h("input", {
    type: "checkbox",
    id: "offline",
    name: "offline",
    onChange: saveQueryState,
  });

  const runButton = h("button", { type: "submit", id: "run-btn" }, "Run search");

  const createProfileButton = h("button", {
    type: "button",
    id: "profile-create-btn",
    class: "btn-icon",
    "aria-label": "Create profile",
    title: "Create profile",
    onClick: () => dialog.openCreate(),
  }, "+");

  const editProfileButton = h("button", {
    type: "button",
    id: "profile-edit-btn",
    class: "btn-icon btn-ghost",
    "aria-label": "Edit selected profile",
    title: "Edit selected profile",
    onClick: () => dialog.openEdit(selectedProfileId()),
  }, "Edit");

  const deleteProfileButton = h("button", {
    type: "button",
    id: "profile-delete-btn",
    class: "btn-icon btn-danger",
    "aria-label": "Delete selected profile",
    title: "Delete selected profile",
    onClick: deleteSelectedProfile,
  }, "Delete");

  function build() {
    const statusElement = h("p", { class: "status", id: "status", hidden: true });
    status = createStatus(statusElement);
    results = createResultsPanel({ store });
    settingsPanel = createSettingsPanel({ store });
    dialog = createProfileDialog({
      store,
      onSaved: async (profileId) => {
        await loadProfiles(profileId);
        status.text("Profile saved.");
      },
      onError: (message) => status.text(message, { error: true }),
    });

    const writable = store.get().capabilities?.profile_write !== false;

    const searchPanel = h(
      "section",
      { class: "panel", id: "search-panel" },
      h("h1", { class: "panel-title" }, "Search"),
      h(
        "form",
        { id: "search-form", onSubmit: runSearch },
        h("label", { for: "question" }, "Research question"),
        questionInput,
        h(
          "div",
          { class: "controls" },
          h(
            "div",
            { class: "field" },
            h("label", { for: "profile" }, "Domain profile"),
            h(
              "div",
              { class: "profile-select-row" },
              profileSelect,
              // Absent rather than disabled when this client may not write —
              // an affordance that cannot work should not be on screen.
              writable ? createProfileButton : null,
              writable ? editProfileButton : null,
              // Deletion is reachable from the profile library in U4; the
              // button stays built but hidden so the wiring does not rot.
              writable ? h("span", { hidden: true }, deleteProfileButton) : null,
            ),
          ),
          h("label", { class: "checkbox" }, offlineInput, " Offline test (mock data)"),
          runButton,
        ),
      ),
      statusElement,
    );

    return h("div", { class: "view view-search" }, searchPanel, settingsPanel.element, results.element);
  }

  function selectedProfileId() {
    return String(profileSelect.value || "").trim();
  }

  function updateProfileActions() {
    const hasSelection = Boolean(selectedProfileId());
    editProfileButton.disabled = !hasSelection;
    deleteProfileButton.disabled = !hasSelection;
  }

  function saveQueryState() {
    appStorage.write("query", {
      question: questionInput.value,
      profile: profileSelect.value,
      offline: offlineInput.checked,
    });
  }

  function restoreQueryState() {
    const saved = appStorage.read("query", {}) || {};
    if (saved.question) questionInput.value = saved.question;
    if (saved.offline != null) offlineInput.checked = saved.offline;
  }

  function renderProfileOptions(preferred) {
    const { profiles, defaultProfile } = store.get();
    profileSelect.replaceChildren(
      ...profiles.map((profile) => h("option", { value: profile.id }, profile.label)),
    );

    const selectable = new Set(profiles.map((profile) => profile.id));
    const saved = (appStorage.read("query", {}) || {}).profile;
    for (const candidate of [preferred, saved, defaultProfile]) {
      if (candidate && selectable.has(candidate)) {
        profileSelect.value = candidate;
        break;
      }
    }
    if (!profileSelect.value && profiles.length) {
      profileSelect.value = profiles[0].id;
    }

    updateProfileActions();
    saveQueryState();
  }

  async function loadProfiles(preferred) {
    const data = await request("/api/profiles");
    const profiles = Array.isArray(data.profiles_meta)
      ? data.profiles_meta
      : (data.profiles || []).map((name) => ({ id: name, label: name }));

    store.set({ profiles, defaultProfile: data.default });
    renderProfileOptions(preferred);
  }

  async function deleteSelectedProfile() {
    const profileId = selectedProfileId();
    if (!profileId) return;

    const label = store.get().profiles.find((item) => item.id === profileId)?.label || profileId;
    if (!window.confirm(`Delete profile "${label}"? This cannot be undone.`)) return;

    try {
      await request(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
      await loadProfiles();
      status.text(`Profile "${label}" deleted.`);
    } catch (error) {
      status.text(`Error: ${error.message}`, { error: true });
    }
  }

  async function runSearch(event) {
    event.preventDefault();
    const offline = offlineInput.checked;
    const baseMessage = offline
      ? "Running offline test…"
      : "Searching free scholarly sources — this can take 1–3 minutes.";

    saveQueryState();
    runButton.disabled = true;
    status.progress(baseMessage, {
      step: 0,
      total: 0,
      label: offline ? "Starting…" : "Starting search…",
    });

    try {
      const response = await stream("/api/run/", {
        method: "POST",
        body: {
          question: questionInput.value,
          profile_id: profileSelect.value,
          offline,
          settings_overrides: settingsPanel.collect(),
        },
      });
      const result = await readNdjson(response, {
        onProgress: (progressEvent) => status.progress(baseMessage, progressEvent),
      });

      store.set({ lastResult: result });
      results.render(result);
      settingsPanel.close();
      status.clear();
    } catch (error) {
      status.text(`Error: ${error.message}`, { error: true });
    } finally {
      status.workingVisible(false);
      runButton.disabled = false;
    }
  }

  return {
    mount(outlet) {
      if (!element) {
        element = build();
        restoreQueryState();
        settingsPanel.load();
        loadProfiles().catch((error) => status.text(`Error: ${error.message}`, { error: true }));
      }
      outlet.append(element);
    },

    // The view keeps its DOM (and the last result) between navigations; the
    // router detaches it, so there is nothing to tear down.
    unmount() {},
  };
}
