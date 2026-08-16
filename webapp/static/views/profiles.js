/**
 * The profile library (`#/profiles`) and the profile editor (`#/profiles/new`,
 * `#/profiles/:id`).
 *
 * Both live in one module because they share the same five operations and the
 * same error copy; splitting them would mean exporting half of this file to the
 * other half.
 *
 * The decisions worth knowing before changing anything here:
 *
 * - **A built-in is never edited, and a `403` never reaches the user.** Opening
 *   a built-in gives a read-only editor and a Duplicate action, so the forbidden
 *   request is not made rather than made and explained. That is the whole of the
 *   `ProtectedProfileError` requirement in UI PRD §6.2.
 * - **Deletion is immediate and undo re-creates.** The alternative — hold the
 *   delete for seven seconds and fire it on expiry — leaves the server holding a
 *   profile the UI says is gone, and loses the delete entirely if the tab is
 *   closed. So the row goes now, its payload is kept in memory, and Undo posts
 *   it back. The slug is freed by the delete, so the restored profile normally
 *   lands on the id it had.
 * - **Import is client-side in both modes.** It parses, pre-validates and
 *   previews the file here, then saves through the same `/api/profiles` routes
 *   as the editor. The hosted service also has `POST /accounts/api/profiles/import`,
 *   but using it would give the download a second code path that cannot work
 *   with no network — and the envelope has to be understood here anyway to show
 *   the preview.
 * - **Write affordances are absent, not disabled, when `profile_write` is
 *   false.** A hosted anonymous visitor sees the built-ins and a sign-in line.
 */

import { clear, h } from "../lib/dom.js";
import { formatCount, formatRelativeTime } from "../lib/format.js";
import {
  ProfileFileError,
  buildExportEnvelope,
  describeDifferences,
  exportFilename,
  readProfileFile,
  saveTextFile,
  serialiseEnvelope,
} from "../lib/profile-file.js";
import {
  cachedProfilePayload,
  createProfile,
  deleteProfile,
  describeProfileError,
  loadProfilePayload,
  refreshProfileList,
  updateProfile,
} from "../lib/profiles.js";
import { createAiProfileDialog } from "../components/profile-ai-dialog.js";
import { createProfileEditor } from "../components/profile-editor.js";
import { createStatus } from "../components/status.js";
import { createToastRegion } from "../components/toast.js";

/** Concurrent payload fetches while filling in the cards. */
const DETAIL_CONCURRENCY = 4;

const UNDO_MS = 7000;

// --- library -----------------------------------------------------------------

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @param {{navigate: function(string): void}} options.router
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createProfilesView({ store, router }) {
  let element = null;
  let status = null;
  let toasts = null;
  /** Card element per profile id, so a late payload can fill one in place. */
  const cards = new Map();

  const builtinList = h("ul", { class: "profile-card-list" });
  const ownList = h("ul", { class: "profile-card-list" });

  const ownRegion = h("section", {
    class: "profile-group",
    // Focus lands here after a deletion removed the card that had it.
    tabIndex: -1,
    "aria-labelledby": "profiles-own-heading",
  });

  const importInput = h("input", {
    type: "file",
    id: "profile-import",
    class: "file-input",
    accept: ".json,.yaml,.yml,application/json,application/yaml,text/yaml",
    onChange: onImportPicked,
  });

  const toolbar = h("div", { class: "profiles-toolbar" });

  function build() {
    const statusElement = h("p", { class: "status", id: "profiles-status", hidden: true });
    status = createStatus(statusElement);
    toasts = createToastRegion();

    return h(
      "div",
      { class: "view view-profiles" },
      h(
        "section",
        { class: "panel" },
        h("h1", { class: "panel-title" }, "Domain profiles"),
        h(
          "p",
          { class: "view-intro" },
          "A profile is how bierre expands your question into searches and decides which papers matter. Start from a built-in, duplicate it, and tune it.",
        ),
        toolbar,
        statusElement,
      ),
      h(
        "section",
        { class: "panel profile-group", "aria-labelledby": "profiles-builtin-heading" },
        h("h2", { class: "panel-title", id: "profiles-builtin-heading" }, "Built-in"),
        h(
          "p",
          { class: "field-hint" },
          "Shared with everyone and read-only. Duplicate one to make a version you can change.",
        ),
        builtinList,
      ),
      ownRegion,
      toasts.element,
    );
  }

  /**
   * Only the affordances this caller may actually use (UI PRD §4). Rebuilt on
   * every render rather than once at build time: `profile_write` answers for the
   * current caller, so it flips when the user signs in or out, and this view's
   * DOM outlives that.
   */
  function renderToolbar() {
    if (!isWritable(store)) {
      toolbar.replaceChildren(
        h(
          "p",
          { class: "field-hint" },
          "Built-in profiles are available to everyone. ",
          h("a", { href: "#/signin" }, "Sign in"),
          " to create, import and keep your own.",
        ),
      );
      return;
    }

    toolbar.replaceChildren(
      h("a", { class: "account-link", href: "#/profiles/new" }, "New profile"),
      h(
        "div",
        { class: "field-block import-field" },
        h("label", { for: "profile-import" }, "Import a profile file"),
        importInput,
        h(
          "p",
          { class: "field-hint" },
          "JSON or YAML, exported from bierre or written by hand. You review it before anything is saved.",
        ),
      ),
    );
  }

  function render() {
    const profiles = store.get().profiles || [];
    cards.clear();

    const builtins = profiles.filter((profile) => profile.is_builtin);
    const own = profiles.filter((profile) => !profile.is_builtin);

    renderToolbar();
    builtinList.replaceChildren(...builtins.map(buildCard));
    renderOwnGroup(own);
    fillDetails(profiles);
  }

  function renderOwnGroup(own) {
    const writable = isWritable(store);
    clear(ownRegion);
    ownRegion.className = "panel profile-group";
    ownRegion.append(
      h("h2", { class: "panel-title", id: "profiles-own-heading" }, "Yours"),
      own.length
        ? ownList
        : h(
            "p",
            { class: "field-hint" },
            writable
              ? "You have no profiles yet. Duplicating a built-in is the quickest start — it gives you a working example to change."
              : "Profiles you create while signed in appear here.",
          ),
    );
    if (own.length) ownList.replaceChildren(...own.map(buildCard));
  }

  function buildCard(profile) {
    const writable = isWritable(store);
    const editable = writable && !profile.is_builtin;

    const question = h("p", { class: "profile-card-question" });
    const facts = h("p", { class: "profile-card-facts" });

    const actions = h(
      "div",
      { class: "profile-card-actions" },
      action("Use", `Use profile ${profile.label}`, () => useProfile(profile)),
      h(
        "a",
        {
          class: "btn-ghost btn-link",
          href: `#/profiles/${encodeURIComponent(profile.id)}`,
          "aria-label": `${editable ? "Edit" : "View"} profile ${profile.label}`,
        },
        editable ? "Edit" : "View",
      ),
      writable ? action("Duplicate", `Duplicate profile ${profile.label}`, () => duplicate(profile)) : null,
      buildExportMenu(profile),
      editable
        ? action("Delete", `Delete profile ${profile.label}`, (event) => remove(profile, event), "btn-danger-ghost")
        : null,
    );

    const card = h(
      "li",
      { class: "profile-card" },
      h(
        "div",
        { class: "profile-card-head" },
        h("h3", { class: "profile-card-title" }, profile.label || profile.id),
        profile.is_builtin ? h("span", { class: "badge" }, "Built-in") : null,
      ),
      question,
      facts,
      actions,
    );

    cards.set(profile.id, { card, question, facts, profile });
    applyDetail(profile.id);
    return card;
  }

  function buildExportMenu(profile) {
    const menu = h(
      "details",
      { class: "export-menu" },
      h("summary", { class: "btn-ghost", "aria-label": `Export profile ${profile.label}` }, "Export"),
      h(
        "div",
        { class: "export-menu-panel" },
        h("button", { type: "button", class: "export-option", onClick: () => exportAs(profile, "json") }, "JSON file"),
        h("button", { type: "button", class: "export-option", onClick: () => exportAs(profile, "yaml") }, "YAML file"),
      ),
    );

    menu.addEventListener("click", (event) => {
      if (event.target.closest(".export-option")) menu.open = false;
    });
    menu.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !menu.open) return;
      menu.open = false;
      menu.querySelector("summary").focus();
    });
    return menu;
  }

  function action(label, accessibleName, onClick, extraClass = "btn-ghost") {
    return h("button", { type: "button", class: extraClass, "aria-label": accessibleName, onClick }, label);
  }

  /**
   * A profile *list* has no default question and no concept count — those live in
   * the payload — so the cards render immediately from the summary and fill in as
   * the payloads arrive. A failed fetch leaves a card without the extra detail
   * rather than replacing the whole library with an error.
   */
  async function fillDetails(profiles) {
    const queue = profiles.filter((profile) => !cachedProfilePayload(profile.id)).map((profile) => profile.id);
    const workers = Array.from({ length: Math.min(DETAIL_CONCURRENCY, queue.length) }, async () => {
      while (queue.length) {
        const id = queue.shift();
        try {
          await loadProfilePayload(id);
          applyDetail(id);
        } catch {
          // The card keeps its label; nothing else here is essential.
        }
      }
    });
    await Promise.all(workers);
  }

  function applyDetail(id) {
    const entry = cards.get(id);
    const payload = cachedProfilePayload(id);
    if (!entry || !payload) return;

    const defaultQuestion = String(payload.default_question || "").trim();
    entry.question.textContent = defaultQuestion || "No default question.";
    entry.question.classList.toggle("is-empty", !defaultQuestion);
    entry.facts.replaceChildren(...describeFacts(payload, entry.profile));
  }

  function describeFacts(payload, profile) {
    const concepts = Array.isArray(payload.concepts) ? payload.concepts.length : 0;
    const buckets = Array.isArray(payload.buckets) ? payload.buckets.length : 0;
    const facts = [
      `${formatCount(concepts)} ${concepts === 1 ? "concept" : "concepts"}`,
      `${formatCount(buckets)} ${buckets === 1 ? "bucket" : "buckets"}`,
    ];

    const updated = profile.updated_at ? formatRelativeTime(profile.updated_at) : "";
    return [
      facts.join(" · "),
      updated ? " · " : null,
      updated ? h("time", { dateTime: profile.updated_at }, `updated ${updated}`) : null,
    ].filter((part) => part !== null);
  }

  // --- operations ------------------------------------------------------------

  function useProfile(profile) {
    // The search view owns the dropdown; it watches the store for this.
    store.set({ profileSelection: profile.id });
    router.navigate("/search");
  }

  async function exportAs(profile, format) {
    try {
      const payload = await loadProfilePayload(profile.id);
      const { text, mediaType } = serialiseEnvelope(buildExportEnvelope(payload), format);
      saveTextFile(exportFilename(profile.id, format), text, mediaType);
      status.text(`Exported “${profile.label}” as ${format.toUpperCase()}.`);
    } catch (error) {
      report(error);
    }
  }

  async function duplicate(profile) {
    status.text(`Duplicating “${profile.label}”…`);
    try {
      await duplicateProfile({ store, router, profile });
    } catch (error) {
      report(error);
    }
  }

  /**
   * Delete now, keep the payload, offer it back.
   *
   * Focus is the subtle part: the button that was just pressed no longer exists.
   * A keyboard activation (`event.detail === 0`) moves focus onto the toast's
   * Undo button, because a keyboard user would otherwise have to tab past every
   * remaining card to reach it before it expires. A pointer activation moves
   * focus to the list region instead, which is where that user is looking.
   */
  async function remove(profile, event) {
    const fromKeyboard = event?.detail === 0;
    status.clear();

    try {
      const payload = await loadProfilePayload(profile.id);
      await deleteProfile(profile.id);
      await refreshProfileList(store);
      render();

      const toast = toasts.show({
        message: `Deleted “${profile.label}”.`,
        actionLabel: "Undo",
        duration: UNDO_MS,
        onAction: () => restore(payload, profile.label),
      });

      if (fromKeyboard) toast.focusAction();
      else ownRegion.focus();
    } catch (error) {
      report(error);
    }
  }

  async function restore(payload, label) {
    try {
      await createProfile(payload);
      await refreshProfileList(store);
      render();
      status.text(`Restored “${label}”.`);
    } catch (error) {
      report(error);
      // Rethrown so the toast keeps its Undo button live for a second attempt.
      throw error;
    }
  }

  async function onImportPicked(event) {
    const [file] = event.target.files || [];
    // Cleared so that picking the same file twice still fires `change`.
    importInput.value = "";
    if (!file) return;

    status.text(`Reading ${file.name}…`);
    try {
      const document = await readProfileFile(file);
      status.clear();
      store.set({ profileDraft: document });
      router.navigate("/profiles/new");
    } catch (error) {
      if (error instanceof ProfileFileError || error.name === "YamlError") {
        status.text(error.message, { error: true });
      } else {
        report(error);
      }
    }
  }

  function report(error) {
    const { message, detail } = describeProfileError(error);
    status.text(detail ? `${message} (${detail})` : message, { error: true });
  }

  /**
   * @param {?string} notice A message the route that navigated here left behind,
   *   shown after the list has loaded so "Loading profiles…" does not overwrite
   *   it — and so the live region announces it once, not twice.
   */
  async function load(notice) {
    status.text(notice || "Loading profiles…");
    try {
      await refreshProfileList(store);
      render();
      if (!notice) status.clear();
    } catch (error) {
      report(error);
    }
  }

  return {
    mount(outlet) {
      if (!element) element = build();
      outlet.append(element);
      load(takeNotice(store));
    },

    unmount() {
      // Every toast owns an interval; leaving the route has to stop them.
      toasts.clear();
    },
  };
}

// --- editor ------------------------------------------------------------------

/**
 * One view for three routes: `#/profiles/new`, the same route carrying an
 * imported draft, and `#/profiles/:id`. They differ by which actions are on the
 * page and what happens on save, so one component with a mode is honest; three
 * near-identical views would drift.
 *
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @param {{navigate: function(string): void}} options.router
 * @returns {{mount: function(HTMLElement, Object): void, unmount: function(): void}}
 */
export function createProfileEditorView({ store, router }) {
  let element = null;
  let status = null;
  let editor = null;
  let aiDialog = null;

  let mode = "create";
  let profileId = null;
  /** The caller's own profile an import would overwrite, if any. */
  let overwriteTarget = null;
  let saving = false;
  /**
   * Incremented every time the view is put into a mode. A profile fetch that
   * resolves after the user has navigated on — `#/profiles/a` then straight to
   * `#/profiles/new`, which a hash router makes instant — must not load itself
   * over the mode that replaced it.
   */
  let generation = 0;

  const heading = h("h1", null, "New profile");
  const banner = h("div", { class: "editor-banner", hidden: true });
  const actions = h("div", { class: "editor-actions" });

  function build() {
    const statusElement = h("p", { class: "status", id: "editor-status", hidden: true });
    status = createStatus(statusElement);
    editor = createProfileEditor();
    aiDialog = createAiProfileDialog({
      onDraft: (payload) => {
        editor.load(payload);
        status.text("Draft loaded. Review every section, then save.");
        editor.focusFirstField();
      },
    });

    return h(
      "div",
      { class: "view view-profile-editor" },
      h(
        "section",
        { class: "panel" },
        h("p", { class: "editor-back" }, h("a", { href: "#/profiles" }, "← All profiles")),
        heading,
        banner,
        statusElement,
      ),
      editor.element,
      h("section", { class: "panel editor-actions-panel" }, actions),
      aiDialog.element,
    );
  }

  // --- modes -----------------------------------------------------------------

  function startCreate(notice) {
    generation += 1;
    mode = "create";
    profileId = null;
    overwriteTarget = null;
    heading.textContent = "New profile";
    editor.setReadOnly(false);
    editor.load(null);
    showBanner(null);
    renderActions();
    if (notice) status.text(notice);
    else status.clear();
  }

  function startImport(draft) {
    const attempt = (generation += 1);
    mode = "import";
    profileId = null;
    heading.textContent = draft.profile.label ? `Import: ${draft.profile.label}` : "Import profile";
    editor.setReadOnly(false);
    editor.load(draft.profile);

    overwriteTarget =
      (store.get().profiles || []).find(
        (profile) => profile.id === draft.derivedId && !profile.is_builtin,
      ) || null;

    showBanner([
      h(
        "p",
        null,
        `Read ${draft.filename} as ${draft.format.toUpperCase()}${draft.enveloped ? "" : " (a bare profile, with no export envelope)"}. Nothing has been saved yet — review the fields below, then choose an action.`,
      ),
    ]);
    renderActions();

    if (overwriteTarget) describeOverwrite(draft.profile, attempt);
  }

  /** The Overwrite decision needs to say what would change, not just warn. */
  async function describeOverwrite(incoming, attempt) {
    const target = overwriteTarget;
    try {
      const current = await loadProfilePayload(target.id);
      if (attempt !== generation) return;
      const differences = describeDifferences(current, incoming);
      showBanner([
        ...banner.querySelectorAll("p"),
        h(
          "p",
          null,
          `Your profile “${target.label}” already uses the id ${target.id}. `,
          differences.length
            ? `Overwriting it would change: ${differences.join(", ")}.`
            : "The file matches it exactly, so overwriting would change nothing.",
        ),
      ]);
    } catch {
      // Without the current payload the difference list is unavailable; the
      // Overwrite button still says which profile it would replace.
    }
  }

  async function openExisting(id, notice) {
    const attempt = (generation += 1);
    mode = "edit";
    profileId = id;
    overwriteTarget = null;
    heading.textContent = "Profile";
    showBanner(null);
    clear(actions);
    status.text(notice || "Loading profile…");

    try {
      if (!(store.get().profiles || []).length) await refreshProfileList(store);
      const payload = await loadProfilePayload(id, { refresh: true });
      if (attempt !== generation) return;

      const meta = (store.get().profiles || []).find((profile) => profile.id === id);
      const builtin = Boolean(meta?.is_builtin);

      mode = builtin || !isWritable(store) ? "readonly" : "edit";
      heading.textContent = payload.label || meta?.label || id;
      editor.load(payload);
      editor.setReadOnly(mode === "readonly");
      showBanner(mode === "readonly" ? readOnlyBanner(builtin) : null);
      renderActions();
      if (!notice) status.clear();
    } catch (error) {
      if (attempt !== generation) return;
      const { message } = describeProfileError(error);
      showBanner([
        h("p", null, message),
        h("p", null, h("a", { href: "#/profiles" }, "Back to the profile library")),
      ]);
      clear(actions);
      status.clear();
    }
  }

  function readOnlyBanner(builtin) {
    if (builtin) {
      return [
        h(
          "p",
          null,
          "This is a built-in profile. It is shared with everyone and cannot be changed — duplicate it to get a copy of your own.",
        ),
      ];
    }
    return [
      h("p", null, "You are viewing this profile read-only. ", h("a", { href: "#/signin" }, "Sign in"), " to edit it."),
    ];
  }

  function showBanner(children) {
    if (!children) {
      banner.hidden = true;
      clear(banner);
      return;
    }
    banner.hidden = false;
    banner.replaceChildren(...[children].flat().filter(Boolean));
  }

  // --- actions ---------------------------------------------------------------

  function renderActions() {
    const buttons = [];

    if (mode === "create" || mode === "import") {
      buttons.push(primary("Create profile", () => save({})));
      if (overwriteTarget) {
        buttons.push(
          h(
            "button",
            {
              type: "button",
              class: "btn-danger",
              onClick: () => save({ overwriteId: overwriteTarget.id }),
            },
            `Overwrite “${overwriteTarget.label}”`,
          ),
        );
      }
    } else if (mode === "edit") {
      buttons.push(primary("Save changes", () => save({})));
    } else if (isWritable(store)) {
      buttons.push(primary("Duplicate to edit", duplicateCurrent));
    }

    if (mode === "create") {
      buttons.push(
        h(
          "button",
          { type: "button", class: "btn-ghost", onClick: () => aiDialog.open(currentLabel()) },
          "Generate with AI",
        ),
      );
    }

    buttons.push(h("a", { class: "btn-ghost btn-link editor-cancel", href: "#/profiles" }, "Cancel"));
    actions.replaceChildren(...buttons);
  }

  function primary(label, onClick) {
    return h("button", { type: "button", onClick }, label);
  }

  function currentLabel() {
    try {
      return editor.collect().label;
    } catch {
      return "";
    }
  }

  async function save({ overwriteId = null }) {
    if (saving) return;

    let payload;
    try {
      payload = editor.collect();
    } catch (error) {
      // A missing label is the only client-side rejection; `collect()` has
      // already moved focus to the field that has to change.
      status.text(error.message, { error: true });
      return;
    }

    const targetId = overwriteId || (mode === "edit" ? profileId : null);
    setSaving(true);
    status.text("Saving…");

    try {
      if (targetId) await updateProfile(targetId, payload);
      else await createProfile(payload);

      await refreshProfileList(store);
      store.set({
        profileNotice: {
          message: targetId ? `Saved “${payload.label}”.` : `Created “${payload.label}”.`,
        },
      });
      router.navigate("/profiles");
    } catch (error) {
      const { message, detail } = describeProfileError(error);
      status.text(detail ? `${message} (${detail})` : message, { error: true });
    } finally {
      setSaving(false);
    }
  }

  async function duplicateCurrent() {
    if (!profileId) return;
    const meta = (store.get().profiles || []).find((profile) => profile.id === profileId);
    status.text("Duplicating…");
    try {
      await duplicateProfile({ store, router, profile: meta || { id: profileId, label: heading.textContent } });
    } catch (error) {
      const { message, detail } = describeProfileError(error);
      status.text(detail ? `${message} (${detail})` : message, { error: true });
    }
  }

  function setSaving(active) {
    saving = active;
    editor.setBusy(active);
    for (const button of actions.querySelectorAll("button")) button.disabled = active;
  }

  return {
    mount(outlet, params) {
      if (!element) element = build();
      outlet.append(element);

      const notice = takeNotice(store);
      const requestedId = params?.id || null;
      if (requestedId) {
        openExisting(requestedId, notice);
        return;
      }

      // Creating needs write authority; a hosted anonymous visitor is sent to
      // sign in rather than shown a form whose save cannot succeed.
      if (!isWritable(store)) {
        store.set({ authNotice: { message: "Sign in to create profiles." } });
        router.navigate("/signin");
        return;
      }

      const draft = store.get().profileDraft;
      if (draft) {
        store.set({ profileDraft: null });
        startImport(draft);
      } else {
        startCreate(notice);
      }
    },

    unmount() {},
  };
}

// --- shared ------------------------------------------------------------------

function isWritable(store) {
  return store.get().capabilities?.profile_write !== false;
}

/**
 * Read and clear the one-line message the previous route left behind.
 *
 * Returned rather than displayed, because the caller has to decide *when*: a
 * view that shows it and then overwrites it with "Loading…" has thrown it away,
 * and one that shows it twice makes the live region announce it twice.
 */
function takeNotice(store) {
  const notice = store.get().profileNotice;
  if (!notice) return null;
  store.set({ profileNotice: null });
  return notice.message;
}

/**
 * Fork a profile and open the copy. This is how a built-in is edited, so it has
 * to work from both the library and the read-only editor.
 *
 * The label carries "(copy)" because the server derives the id from the label:
 * an identical label would collide and be resolved to `…-2`, which is a worse
 * name than the user can choose for themselves in the editor that opens next.
 */
async function duplicateProfile({ store, router, profile }) {
  const payload = await loadProfilePayload(profile.id);
  const label = `${String(payload.label || profile.label || profile.id)} (copy)`;
  const created = await createProfile({ ...payload, label });

  await refreshProfileList(store);
  store.set({
    profileNotice: { message: `Copied “${profile.label || profile.id}”. This copy is yours to change.` },
  });
  router.navigate(`/profiles/${encodeURIComponent(created.id)}`);
}
