/**
 * Account view — `#/account`. Reads and writes the two fields this slice owns,
 * `display_name` and `locale`, through `GET` and `PATCH /auth/me`.
 *
 * The email address is shown but not editable: changing it needs the
 * verification pipeline that arrives with A2. Connected logins, data export and
 * account deletion are the rest of this route in UI PRD §5 and land with their
 * own phases; nothing is stubbed here, because a control that does nothing is
 * worse than a control that is absent.
 *
 * `GET /me` runs on every visit rather than reading the store: this is the
 * screen where a user checks what the server actually holds about them, so a
 * cached answer would defeat the point.
 */

import { clear, h } from "../lib/dom.js";
import { createStatus } from "../components/status.js";
import { describeAuthError } from "../lib/session.js";
import { getLocale } from "../lib/format.js";

const DISPLAY_NAME_MAX_LENGTH = 120; // Mirrors `users.display_name` in bierre-ca.

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @param {Object} options.session `lib/session.js`
 * @param {{navigate: function(string): void}} options.router
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createAccountView({ store, session, router }) {
  let element = null;
  let status = null;
  let loaded = null;
  let saving = false;

  const emailValue = h("dd", { class: "account-value" });

  const displayNameInput = h("input", {
    id: "account-display-name",
    name: "display_name",
    type: "text",
    autocomplete: "name",
    maxLength: DISPLAY_NAME_MAX_LENGTH,
    "aria-describedby": "account-display-name-hint",
  });

  const localeSelect = h("select", { id: "account-locale", name: "locale" });

  const saveButton = h("button", { type: "submit" }, "Save changes");

  function build() {
    const statusElement = h("p", { class: "status", id: "account-status", hidden: true });
    status = createStatus(statusElement);

    return h(
      "div",
      { class: "view view-account" },
      h(
        "section",
        { class: "panel account-panel" },
        h("h1", null, "Account"),
        h(
          "dl",
          { class: "account-facts" },
          h("dt", null, "Email address"),
          emailValue,
        ),
        statusElement,
        h(
          "form",
          { class: "auth-form", noValidate: true, onSubmit: onSubmit },
          h(
            "div",
            { class: "field-block" },
            h("label", { for: "account-display-name" }, "Display name"),
            displayNameInput,
            h(
              "p",
              { class: "field-hint", id: "account-display-name-hint" },
              "Shown in place of your email address. Leave it empty to use the address.",
            ),
          ),
          h(
            "div",
            { class: "field-block" },
            h("label", { for: "account-locale" }, "Language"),
            localeSelect,
          ),
          saveButton,
        ),
      ),
    );
  }

  /**
   * One option per locale with a shipped catalogue. Named through
   * `Intl.DisplayNames` in the *active* locale, so the list a French reader sees
   * is in French — a hardcoded label table would need translating itself.
   */
  function renderLocaleOptions(selected) {
    const locales = store.get().capabilities?.locales || ["en"];
    let describe = (tag) => tag;
    try {
      const names = new Intl.DisplayNames([getLocale()], { type: "language" });
      describe = (tag) => names.of(tag) || tag;
    } catch {
      // An engine without DisplayNames still gets usable tags.
    }

    clear(localeSelect);
    localeSelect.append(...locales.map((tag) => h("option", { value: tag }, describe(tag))));
    if (locales.includes(selected)) localeSelect.value = selected;
  }

  function fill(user) {
    loaded = user;
    emailValue.textContent = user.email || "Not set";
    displayNameInput.value = user.display_name || "";
    renderLocaleOptions(user.locale);
  }

  /** Only what changed. An empty patch is a `400`, and a no-op is not a request. */
  function collectChanges() {
    const patch = {};
    const displayName = displayNameInput.value.trim();
    if (displayName !== (loaded?.display_name || "")) patch.display_name = displayName;
    if (localeSelect.value !== loaded?.locale) patch.locale = localeSelect.value;
    return patch;
  }

  async function load() {
    status.text("Loading your account…");
    try {
      fill(await session.loadUser());
      status.clear();
    } catch (error) {
      status.text(describeAuthError(error), { error: true });
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (saving || !loaded) return;

    const patch = collectChanges();
    if (!Object.keys(patch).length) {
      status.text("Nothing to save — those are the current values.");
      return;
    }

    saving = true;
    saveButton.disabled = true;
    status.text("Saving…");
    try {
      fill(await session.updateUser(patch));
      status.text("Account updated.");
    } catch (error) {
      status.text(describeAuthError(error), { error: true });
    } finally {
      saving = false;
      saveButton.disabled = false;
    }
  }

  return {
    mount(outlet) {
      if (!element) element = build();
      outlet.append(element);

      // Route guard. bierre-ca answers 401 to an anonymous `GET /me` regardless;
      // this exists so the user sees a sign-in form instead of an error.
      if (!session.isSignedIn()) {
        store.set({ authNotice: { message: "Sign in to see your account." } });
        router.navigate("/signin");
        return;
      }
      load();
    },

    unmount() {},
  };
}
