/**
 * Search view: the question form, the profile picker, the settings panel and
 * the results table. The `#/` route.
 *
 * Profile *management* is not here any more. The dropdown stays — it is the
 * right primitive for switching quickly, and UI PRD §6.2 says so explicitly —
 * but creating, editing, duplicating, importing and deleting moved to
 * `#/profiles`, so this view only links to them. What is left in the store is
 * the coupling: the library sets `profileSelection` and this view follows it,
 * which is how "Use this profile" lands the user back on a prepared search box.
 */

import { h } from "../lib/dom.js";
import { readNdjson, stream } from "../lib/api.js";
import { appStorage } from "../lib/storage.js";
import { describeProfileError, refreshProfileList } from "../lib/profiles.js";
import { createStatus } from "../components/status.js";
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
      // The store holds the current choice so the library and this view cannot
      // disagree about which profile the next run uses.
      store.set({ profileSelection: selectedProfileId() });
    },
  });

  const offlineInput = h("input", {
    type: "checkbox",
    id: "offline",
    name: "offline",
    onChange: saveQueryState,
  });

  const runButton = h("button", { type: "submit", id: "run-btn" }, "Run search");

  const newProfileLink = h("a", {
    id: "profile-new-link",
    class: "btn-ghost btn-link",
    href: "#/profiles/new",
  }, "New");

  const editProfileLink = h("a", {
    id: "profile-edit-link",
    class: "btn-ghost btn-link",
    href: "#/profiles",
  }, "Edit");

  const libraryLink = h("a", {
    id: "profile-library-link",
    class: "btn-ghost btn-link",
    href: "#/profiles",
  }, "All profiles");

  const profileActions = h("span", { class: "profile-actions" });
  let writable = null;

  /**
   * Write affordances are absent, never disabled, when this client may not write.
   *
   * `profile_write` answers for the *current caller*, so it flips when the user
   * signs in or out and this cannot be read once at build time — the view's DOM
   * is built once and kept across navigations. The library link is not gated:
   * reading the built-ins needs no account.
   */
  function renderProfileActions() {
    const allowed = store.get().capabilities?.profile_write !== false;
    if (allowed === writable) return;

    writable = allowed;
    profileActions.replaceChildren(
      ...(allowed ? [newProfileLink, editProfileLink, libraryLink] : [libraryLink]),
    );
  }

  /**
   * Re-render on the two store changes this view depends on: the profile list
   * (something was created or deleted on `#/profiles`) and the selection (the
   * library's "Use" action).
   */
  let renderedProfiles = null;
  store.subscribe((state) => {
    renderProfileActions();
    if (state.profiles !== renderedProfiles) {
      renderedProfiles = state.profiles;
      renderProfileOptions(state.profileSelection);
    } else if (state.profileSelection && state.profileSelection !== profileSelect.value) {
      renderProfileOptions(state.profileSelection);
    }
  });

  function build() {
    const statusElement = h("p", { class: "status", id: "status", hidden: true });
    status = createStatus(statusElement);
    results = createResultsPanel({ store });
    settingsPanel = createSettingsPanel({ store });

    renderProfileActions();

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
            h("div", { class: "profile-select-row" }, profileSelect, profileActions),
          ),
          // TODO: remove this button and associated logic
          // h("label", { class: "checkbox" }, offlineInput, " Offline test (mock data)"),
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

  /**
   * The Edit link points at the selected profile, and says which one it is: five
   * identical "Edit" links in a screen reader's link list are five dead ends.
   * With nothing selected there is nothing to edit, so the link is absent.
   */
  function updateProfileActions() {
    const profileId = selectedProfileId();
    const label = store.get().profiles.find((profile) => profile.id === profileId)?.label || profileId;

    editProfileLink.hidden = !profileId;
    if (!profileId) return;
    editProfileLink.href = `#/profiles/${encodeURIComponent(profileId)}`;
    editProfileLink.setAttribute("aria-label", `Edit profile ${label}`);
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
    // No list yet (the first store notification arrives before the fetch
    // resolves): leaving early keeps `saveQueryState` from writing an empty
    // selection over the profile the user had chosen in a previous session.
    if (!profiles.length) return;

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

  /** The store subscription above renders the options this resolves. */
  async function loadProfiles() {
    try {
      await refreshProfileList(store);
    } catch (error) {
      const { message } = describeProfileError(error);
      status.text(message, { error: true });
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
      const response = await stream("/api/run", {
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
      }
      outlet.append(element);
      // Refreshed on every visit, not only the first: a profile may have been
      // created, renamed or deleted on `#/profiles` since this view was built.
      loadProfiles();
    },

    // The view keeps its DOM (and the last result) between navigations; the
    // router detaches it, so there is nothing to tear down.
    unmount() {},
  };
}
