/**
 * The one place that talks to the network.
 *
 * Token handling, in order of importance:
 *
 * 1. The access token lives in the module variable below and nowhere else.
 *    Not `localStorage`, not `sessionStorage`, not a readable cookie — anything
 *    a script on the page can read, an injected script can exfiltrate. The cost
 *    is that a page reload loses it, which is exactly what the refresh cookie
 *    (HttpOnly, `Path=/accounts/api/auth`) is for.
 * 2. A `401` is retried exactly once, through `POST …/auth/refresh`. Once,
 *    because a refresh that fails and is retried is an infinite loop against
 *    the account service.
 * 3. The three cookie-authenticated routes carry the double-submit
 *    `X-CSRF-Token` header, read from the readable `bierre_csrf` cookie.
 *
 * In local mode there is no account service: `configureAuth()` is called with a
 * null base, and every branch above turns itself off.
 */

const CSRF_COOKIE = "bierre_csrf";

/** Routes that establish a session, so a 401 from them must not trigger a refresh. */
const SESSION_ROUTES = ["/refresh", "/login", "/signup"];

/** Cookie-authenticated routes, which need the double-submit CSRF header. */
const CSRF_ROUTES = ["/refresh", "/logout", "/logout-all"];

let accessToken = null;
let accountsBase = null;
let onUnauthenticated = null;
let refreshInFlight = null;

/** A failed request, carrying the status the caller needs to branch on. */
export class ApiError extends Error {
  constructor(message, { status = 0, path = "" } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

/**
 * @param {Object} options
 * @param {?string} options.accountsBase `capabilities.accounts_base`, or null
 *   in local mode, which disables bearer auth, refresh and CSRF entirely.
 * @param {?function(): void} options.onUnauthenticated Called after a refresh
 *   fails; the app uses it to bounce to sign-in.
 */
export function configureAuth({ accountsBase: base = null, onUnauthenticated: handler = null } = {}) {
  accountsBase = base;
  onUnauthenticated = handler;
}

/** Full path of an auth route, or null when the deployment has no accounts. */
export function authPath(suffix) {
  return accountsBase ? `${accountsBase}/api/auth${suffix}` : null;
}

export function setAccessToken(token) {
  accessToken = token || null;
}

export function isSignedIn() {
  return accessToken !== null;
}

/**
 * Exchange the refresh cookie for a new access token. Single-flight: several
 * requests failing with a 401 at once must produce one refresh, not five, or
 * refresh-token rotation revokes the family as a replay.
 *
 * @returns {Promise<boolean>} Whether a token is now held.
 */
export function refreshSession() {
  if (!accountsBase) return Promise.resolve(false);
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** JSON request. Resolves to the parsed body (null on 204), throws `ApiError`. */
export async function request(path, options = {}) {
  const response = await send(path, options);
  return parseJson(response, path);
}

/**
 * Request whose body is read as a stream by `readNdjson`. Returns the raw
 * `Response` — status handling belongs to the reader, because the server
 * reports mid-stream failures as an event rather than a status code.
 */
export function stream(path, options = {}) {
  return send(path, { ...options, accept: "application/x-ndjson, application/json" });
}

/**
 * Read one NDJSON run stream: `{type: "progress"|"result"|"error"}` per line.
 * A server that answered with plain JSON instead (an error handler, say) is
 * parsed as a normal response.
 *
 * @param {Response} response
 * @param {Object} [options]
 * @param {function(Object): void} [options.onProgress]
 * @returns {Promise<Object>} The `result` payload.
 */
export async function readNdjson(response, { onProgress } = {}) {
  const path = new URL(response.url, location.href).pathname;
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/x-ndjson") || !response.body) {
    return parseJson(response, path);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  const handle = (line) => {
    let event = null;
    try {
      event = JSON.parse(line);
    } catch {
      return; // Ignore a malformed line; later events may still be usable.
    }
    if (event?.type === "progress") {
      onProgress?.(event);
    } else if (event?.type === "result") {
      result = event.result || null;
    } else if (event?.type === "error") {
      throw new ApiError(event.error || "Run failed", { status: response.status, path });
    }
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newline = buffer.indexOf("\n");
      while (newline !== -1) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) handle(line);
        newline = buffer.indexOf("\n");
      }
    }

    // A stream may end without a trailing newline, so the tail is its own case.
    buffer += decoder.decode();
    for (const line of buffer.split("\n").map((part) => part.trim())) {
      if (line) handle(line);
    }
  } catch (error) {
    // An `error` event aborts the read; release the socket instead of leaving
    // the body locked and half-consumed.
    reader.cancel().catch(() => {});
    throw error;
  }

  if (!result) {
    throw new ApiError("Run finished without result payload", { status: response.status, path });
  }
  return result;
}

// --- internals ---------------------------------------------------------------

async function send(path, options) {
  let response = await fetch(path, buildInit(path, options));
  if (response.status !== 401 || !canRefresh(path)) return response;

  const refreshed = await refreshSession();
  if (!refreshed) {
    setAccessToken(null);
    onUnauthenticated?.();
    return response;
  }
  return fetch(path, buildInit(path, options));
}

function buildInit(path, { method = "GET", body, headers, signal, auth = true, accept = "application/json" }) {
  const requestHeaders = { Accept: accept, ...headers };
  const init = { method, headers: requestHeaders, credentials: "same-origin" };

  if (body !== undefined) {
    requestHeaders["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (auth && accessToken) {
    requestHeaders.Authorization = `Bearer ${accessToken}`;
  }
  if (isCsrfRoute(path)) {
    requestHeaders["X-CSRF-Token"] = readCookie(CSRF_COOKIE);
  }
  if (signal) init.signal = signal;
  return init;
}

function isCsrfRoute(path) {
  return CSRF_ROUTES.some((route) => path === authPath(route));
}

function canRefresh(path) {
  if (!accountsBase) return false;
  return !SESSION_ROUTES.some((route) => path === authPath(route));
}

async function performRefresh() {
  const path = authPath("/refresh");
  try {
    const response = await fetch(path, buildInit(path, { method: "POST", auth: false }));
    setAccessToken(response.ok ? (await readBody(response))?.access_token : null);
  } catch {
    // Offline, or no account service listening. Anonymous is a valid state.
    setAccessToken(null);
  }
  return isSignedIn();
}

async function readBody(response) {
  const body = await response.text();
  if (!body) return null;
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
}

async function parseJson(response, path) {
  const data = await readBody(response);

  if (!response.ok || data?.error) {
    throw new ApiError(data?.error || `Request failed (${response.status})`, {
      status: response.status,
      path,
    });
  }
  return data;
}

function readCookie(name) {
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}
