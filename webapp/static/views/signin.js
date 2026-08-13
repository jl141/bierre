/**
 * Sign-in and create-account views — `#/signin` and `#/signup`.
 *
 * One module, two modes, because the two screens differ by four strings and one
 * request. They are separate *routes* rather than a toggle inside one view so
 * that each is linkable, each gets its own `document.title`, and the router's
 * focus-and-announce step happens on the switch between them (UI PRD §8).
 *
 * What renders is decided by `capabilities.auth_methods`. This slice ships
 * `password` only; magic link, Google and ORCID produce **no control at all**
 * when absent, rather than a disabled one — an affordance the backend cannot
 * service should not be on screen (UI PRD §4).
 *
 * Validation runs client-side first, and deliberately duplicates the server's
 * password floor. The server stays the authority — a policy change there must
 * not need a front-end release to be enforced — but a round trip to be told
 * "12 characters" is a bad first impression, and the wire error is written for
 * a developer, not a user.
 */

import { h } from "../lib/dom.js";
import { createStatus } from "../components/status.js";
import { describeAuthError } from "../lib/session.js";

/** Mirrors `passwords.MIN_LENGTH` in bierre-ca. The server re-checks it. */
const PASSWORD_MIN_LENGTH = 12;

/**
 * Deliberately loose: `something@something.tld`. The server owns real address
 * validation, and a stricter regex here would reject valid academic addresses.
 */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const SIGNUP_NOTICE =
  "If that address is new, the account is ready. Sign in to continue.";

const COPY = {
  signin: {
    heading: "Sign in",
    intro: "Sign in to keep your domain profiles with your account.",
    submit: "Sign in",
    working: "Signing you in…",
    alternate: { text: "New here?", label: "Create an account", href: "#/signup" },
    passwordAutocomplete: "current-password",
    unauthorized: "Invalid email or password.",
  },
  signup: {
    heading: "Create an account",
    intro: "Email address and password only — nothing else is asked for or stored.",
    submit: "Create account",
    working: "Creating your account…",
    alternate: { text: "Already have an account?", label: "Sign in", href: "#/signin" },
    passwordAutocomplete: "new-password",
    unauthorized: "Invalid email or password.",
  },
};

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @param {Object} options.session `lib/session.js`
 * @param {{navigate: function(string): void}} options.router
 * @param {"signin"|"signup"} [options.mode]
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createSigninView({ store, session, router, mode = "signin" }) {
  const copy = COPY[mode];
  const idPrefix = `${mode}-`;

  let element = null;
  let status = null;
  let submitting = false;

  const emailField = createField({
    id: `${idPrefix}email`,
    label: "Email address",
    type: "email",
    autocomplete: "username",
    // An address is never capitalised, and the email keyboard on a touch device
    // saves the user two taps.
    extras: { inputMode: "email", autocapitalize: "none" },
  });

  const passwordField = createField({
    id: `${idPrefix}password`,
    label: "Password",
    type: "password",
    autocomplete: copy.passwordAutocomplete,
    hint: mode === "signup" ? `At least ${PASSWORD_MIN_LENGTH} characters.` : null,
  });

  const submitButton = h("button", { type: "submit" }, copy.submit);

  function build() {
    const statusElement = h("p", { class: "status", id: `${idPrefix}status`, hidden: true });
    status = createStatus(statusElement);

    const passwordAvailable = (store.get().capabilities?.auth_methods || []).includes("password");

    return h(
      "div",
      { class: "view view-auth" },
      h(
        "section",
        { class: "panel auth-panel" },
        h("h1", null, copy.heading),
        h("p", { class: "auth-intro" }, copy.intro),
        statusElement,
        passwordAvailable ? buildForm() : buildUnavailableNotice(),
      ),
    );
  }

  function buildForm() {
    return h(
      "form",
      {
        class: "auth-form",
        // Validation is ours: the browser's bubbles are unstyled, untranslated,
        // and cannot be pointed at a live region.
        noValidate: true,
        onSubmit: onSubmit,
      },
      emailField.element,
      passwordField.element,
      submitButton,
      buildConsent(),
      h(
        "p",
        { class: "auth-alternate" },
        `${copy.alternate.text} `,
        h("a", { href: copy.alternate.href }, copy.alternate.label),
      ),
    );
  }

  /**
   * Consent for the terms, per UI PRD §6.1. The URLs come from capabilities
   * because the hosted and local builds point at different documents; in this
   * slice they are placeholders, and public hosted signup does not open until
   * the real pages ship (U6).
   */
  function buildConsent() {
    const legal = store.get().capabilities?.legal_urls || {};
    if (!legal.terms || !legal.privacy) return null;

    return h(
      "p",
      { class: "auth-consent" },
      "By continuing you agree to the ",
      h("a", { href: legal.terms }, "Terms"),
      " and ",
      h("a", { href: legal.privacy }, "Privacy Policy"),
      ".",
    );
  }

  function buildUnavailableNotice() {
    return h(
      "p",
      { class: "auth-unavailable" },
      "This deployment has no sign-in method enabled. Nothing here needs an account — search and profiles work without one.",
    );
  }

  /** Show the message another route left behind, and prefill the address. */
  function consumeNotice() {
    const notice = store.get().authNotice;
    if (!notice) return;

    store.set({ authNotice: null });
    if (notice.email) emailField.input.value = notice.email;
    // Called after the element is in the document: a live region announces
    // mutations, so text present before insertion is silently missed.
    if (notice.message) status.text(notice.message);
  }

  function validate() {
    const email = emailField.input.value.trim();
    // Never trimmed: a leading or trailing space is part of the password, and
    // the server hashes what it is given.
    const password = passwordField.input.value;

    const problems = [];
    if (!email) {
      problems.push([emailField, "Enter your email address."]);
    } else if (!EMAIL_SHAPE.test(email)) {
      problems.push([emailField, "Enter a complete email address, like name@university.edu."]);
    }

    if (!password) {
      problems.push([passwordField, "Enter your password."]);
    } else if (mode === "signup" && password.length < PASSWORD_MIN_LENGTH) {
      problems.push([passwordField, `Use at least ${PASSWORD_MIN_LENGTH} characters.`]);
    }
    return { email, password, problems };
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;

    emailField.clearError();
    passwordField.clearError();

    const { email, password, problems } = validate();
    if (problems.length) {
      for (const [field, message] of problems) field.showError(message);
      status.text("Check the fields marked below.", { error: true });
      // Focus the first offender, not the form: the user needs to be where the
      // fix happens, and the error text is `aria-describedby` from there.
      problems[0][0].input.focus();
      return;
    }

    setSubmitting(true);
    status.text(copy.working);
    try {
      if (mode === "signup") {
        await session.signUp({ email, password });
        store.set({ authNotice: { message: SIGNUP_NOTICE, email } });
        router.navigate("/signin");
      } else {
        await session.signIn({ email, password });
        status.clear();
        // Post-sign-in lands on Search, not on a settings wizard (UI PRD §6.1).
        router.navigate("/");
      }
    } catch (error) {
      status.text(describeAuthError(error, { unauthorized: copy.unauthorized }), { error: true });
      // The credential is wrong, not the address, and re-typing it is the next
      // step; `.select()` would be wrong on a password manager's fill.
      passwordField.input.focus();
    } finally {
      setSubmitting(false);
    }
  }

  function setSubmitting(active) {
    submitting = active;
    submitButton.disabled = active;
  }

  return {
    mount(outlet) {
      if (!element) element = build();
      outlet.append(element);

      // Already signed in: this screen has nothing to offer, and leaving it
      // reachable invites a second sign-in that rotates a working session.
      if (session.isSignedIn()) {
        router.navigate("/");
        return;
      }
      passwordField.input.value = "";
      consumeNotice();
    },

    unmount() {
      // A password must not survive in a detached DOM node waiting for the next
      // visit to this route.
      passwordField.input.value = "";
    },
  };
}

/**
 * One labelled control with its hint, its error slot, and the wiring between
 * them: `aria-describedby` naming both, `aria-invalid` while it is wrong.
 *
 * @returns {{element: HTMLElement, input: HTMLInputElement,
 *            showError: function(string): void, clearError: function(): void}}
 */
function createField({ id, label, type, autocomplete, hint = null, extras = {} }) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  const errorElement = h("p", { class: "field-error", id: errorId, hidden: true });
  const hintElement = hint ? h("p", { class: "field-hint", id: hintId }, hint) : null;

  const input = h("input", {
    id,
    name: id,
    type,
    autocomplete,
    required: true,
    "aria-describedby": [hint ? hintId : null, errorId].filter(Boolean).join(" "),
    ...extras,
  });

  // Typing is the user fixing the problem; keeping the message on screen while
  // they do reads as though the fix is not working.
  input.addEventListener("input", clearError);

  function showError(message) {
    input.setAttribute("aria-invalid", "true");
    errorElement.hidden = false;
    errorElement.textContent = message;
  }

  function clearError() {
    input.removeAttribute("aria-invalid");
    errorElement.hidden = true;
    errorElement.textContent = "";
  }

  return {
    element: h(
      "div",
      { class: "field-block" },
      h("label", { for: id }, label),
      input,
      hintElement,
      errorElement,
    ),
    input,
    showError,
    clearError,
  };
}
