/**
 * Session lifecycle: the one module that changes who the app thinks it is.
 *
 * `lib/api.js` owns the access token; this owns everything that has to happen
 * around it. Three of those are easy to forget at a call site and are therefore
 * not left to one:
 *
 * 1. **Capabilities are refetched after every sign-in and sign-out.**
 *    `profile_write` answers for *this caller*, so the boot-time copy is wrong
 *    the moment the caller changes identity.
 * 2. **The active locale is negotiated, not adopted.** A user whose account says
 *    `de` on a deployment that ships only `en` gets English strings, so
 *    `document.documentElement.lang` must say `en` too — a screen reader
 *    pronouncing English text with German phonetics is worse than no hint.
 * 3. **A failed sign-out leaves the user signed in.** The refresh cookie is
 *    `HttpOnly` and only the server can revoke the session behind it; clearing
 *    the token locally would look like a sign-out and silently restore the
 *    session on the next reload.
 *
 * The error copy lives here too. Every message a user sees for a failed session
 * operation is written below, keyed by status, because the wire bodies are
 * developer-facing (`password: Value error, Password must be at least 12
 * characters.`) and a raw exception string in the UI is both unhelpful and a
 * disclosure risk.
 */

import { ApiError, authPath, isSignedIn, refreshSession, request, setAccessToken } from "./api.js";
import { setLocale } from "./format.js";

const FALLBACK_LOCALE = "en";

/** Plain-language copy for the failures the auth routes can produce. */
const MESSAGES = {
  400: "Some of those details were not accepted. Check the fields and try again.",
  403: "That action is not allowed on this account.",
  404: "That account no longer exists.",
  409: "That request conflicts with something already saved.",
  413: "That was too large to send.",
  429: "Too many attempts. Wait a few minutes, then try again.",
  502: "The account service is unavailable. Try again shortly.",
  503: "The account service is unavailable. Try again shortly.",
  504: "The account service is unavailable. Try again shortly.",
};

const OFFLINE_MESSAGE = "Cannot reach the account service. Check your connection and try again.";
const EXPIRED_MESSAGE = "Your session has expired. Sign in again.";
const SERVER_MESSAGE = "Something went wrong at our end. Try again in a moment.";

/**
 * @param {*} error Anything a `catch` block received.
 * @param {Object} [options]
 * @param {string} [options.unauthorized] Copy for a `401`, which means
 *   "credentials rejected" on the sign-in routes and "session gone" everywhere
 *   else — only the caller knows which.
 * @returns {string}
 */
export function describeAuthError(error, { unauthorized = EXPIRED_MESSAGE } = {}) {
  // A network failure never reaches `fetch`'s response, so it arrives as a
  // TypeError rather than an ApiError and has no status to key on.
  if (!(error instanceof ApiError)) return OFFLINE_MESSAGE;
  if (error.status === 401) return unauthorized;
  if (MESSAGES[error.status]) return MESSAGES[error.status];
  return error.status >= 500 || error.status === 0 ? SERVER_MESSAGE : MESSAGES[400];
}

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 */
export function createSession({ store }) {
  function capabilities() {
    return store.get().capabilities || {};
  }

  /** Full auth path, or a thrown error rather than a request to `"null/..."`. */
  function endpoint(suffix) {
    const path = authPath(suffix);
    if (!path) throw new Error("This deployment has no account service.");
    return path;
  }

  /** The closest locale that actually has a string catalogue. */
  function negotiateLocale(preferred) {
    const { locales = [], default_locale: fallback = FALLBACK_LOCALE } = capabilities();
    return locales.includes(preferred) ? preferred : fallback;
  }

  /** Make `user` (or anonymity) the app's current identity. */
  function adopt(user) {
    const locale = negotiateLocale(user?.locale);
    setLocale(locale);
    document.documentElement.lang = locale;
    store.set({ user: user || null });
  }

  async function syncCapabilities() {
    try {
      store.set({ capabilities: await request("/api/capabilities") });
    } catch {
      // The boot-time answer is stale but coherent; a blank one is neither.
    }
  }

  return {
    isSignedIn,

    /**
     * Silent refresh at boot. Anonymous is a valid outcome, so a failure here is
     * never surfaced: the refresh cookie is absent on a first visit and expired
     * on a stale tab, and neither is something to tell the user about.
     *
     * @returns {Promise<boolean>} Whether a session was restored.
     */
    async restore() {
      if (!capabilities().auth) return false;
      if (!(await refreshSession())) return false;

      try {
        await loadUser();
      } catch {
        // A refresh that yields a token the account service then rejects is not
        // a session. Drop the token rather than keep a half-signed-in state.
        setAccessToken(null);
        return false;
      }
      await syncCapabilities();
      return true;
    },

    /** @returns {Promise<Object>} The signed-in user. */
    async signIn({ email, password }) {
      const session = await request(endpoint("/login"), {
        method: "POST",
        body: { email, password },
        // A stale bearer token on a sign-in request would be retried through
        // `/refresh` on a 401, turning a wrong password into a confusing bounce.
        auth: false,
      });

      setAccessToken(session.access_token);
      adopt(session.user);
      await syncCapabilities();
      return session.user;
    },

    /**
     * Create an account. Answers `202` whether or not the address was free — the
     * non-enumeration guarantee — so the caller learns nothing about the address
     * and must not word its success message as though it did.
     */
    signUp({ email, password }) {
      return request(endpoint("/signup"), {
        method: "POST",
        body: { email, password, locale: negotiateLocale(capabilities().default_locale) },
        auth: false,
      });
    },

    /** End this session. Throws — and stays signed in — if the server did not confirm it. */
    signOut() {
      return revoke("/logout");
    },

    /** End every session of this user, on every device. */
    signOutEverywhere() {
      return revoke("/logout-all");
    },

    /** `GET /auth/me`, for a view that needs the server's copy, not the store's. */
    loadUser,

    /**
     * @param {{display_name?: string, locale?: string}} patch At least one field;
     *   the account service rejects an empty patch with a `400`.
     */
    async updateUser(patch) {
      const user = await request(endpoint("/me"), { method: "PATCH", body: patch });
      adopt(user);
      return user;
    },
  };

  async function loadUser() {
    const user = await request(endpoint("/me"));
    adopt(user);
    return user;
  }

  /**
   * Ask the server to end a session, then forget it locally.
   *
   * A `401` is treated as success: it means the credential this call would have
   * revoked is already invalid, so there is nothing left to end and reporting a
   * failure would strand the user in a session they cannot leave. Any other
   * failure propagates and the user stays signed in — the refresh cookie is
   * `HttpOnly`, so only the server can really end a session, and a local-only
   * clear would restore it on the next reload.
   */
  async function revoke(suffix) {
    try {
      await request(endpoint(suffix), { method: "POST" });
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
    }
    await discard();
  }

  async function discard() {
    setAccessToken(null);
    adopt(null);
    await syncCapabilities();
  }
}
