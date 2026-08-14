/**
 * Profile CRUD against the webapp's own `/api/profiles` routes, plus the payload
 * cache the library view needs and the plain-language error copy every caller
 * shares.
 *
 * One surface for both modes on purpose. In local mode these routes are the YAML
 * repository; in hosted mode `webapp/server.py` builds a caller-scoped
 * `HttpProfileRepository` and forwards them to `bierre-ca` with the user's token.
 * A view that spoke to `/accounts/api/profiles` directly would work only hosted,
 * and the download has to keep working with no network at all.
 *
 * The cache exists because a profile *list* carries no `default_question` and no
 * concept count — those live in the payload — so a library of twelve cards is
 * twelve `GET`s that would otherwise repeat on every visit to the route. It is
 * keyed by id, and **dropped whenever the signed-in identity changes**: two
 * users may each own the slug `my-review`, since slugs are scoped per owner and
 * are never globally unique. Keeping A's payload under that key while B is
 * signed in would show B someone else's data.
 */

import { ApiError, request } from "./api.js";
import { sanitiseProfile } from "./profile-file.js";

const payloads = new Map();
let cacheOwner = null;

/** Plain-language copy for what the profile routes can answer. */
const MESSAGES = {
  400: "The server did not accept this profile.",
  401: "Sign in to manage profiles.",
  403: "Built-in profiles cannot be changed. Duplicate it to make your own copy.",
  404: "That profile no longer exists.",
  409: "That label produced an id another profile already uses. Try a slightly different label.",
  413: "That profile is too large to save.",
  429: "Too many profile changes in a short time. Wait a moment, then try again.",
};

const OFFLINE_MESSAGE = "Cannot reach the profile store. Check your connection and try again.";
const SERVER_MESSAGE = "Something went wrong at our end. Try again in a moment.";

/** Statuses whose wire message describes the user's own data and is worth showing. */
const DETAILED_STATUSES = new Set([400, 409]);

/**
 * @param {*} error Anything a `catch` block received.
 * @returns {{message: string, detail: ?string}} `message` is the sentence to
 *   show; `detail` is the server's own wording, which is useful for a rejected
 *   payload and is presented as secondary technical text — never as the whole
 *   error, because the wire strings come from a validation library and are
 *   written for a developer.
 */
export function describeProfileError(error) {
  if (!(error instanceof ApiError)) return { message: OFFLINE_MESSAGE, detail: null };

  const message =
    MESSAGES[error.status] || (error.status >= 500 || error.status === 0 ? SERVER_MESSAGE : MESSAGES[400]);
  const detail = DETAILED_STATUSES.has(error.status) && error.message ? error.message : null;
  return { message, detail };
}

export function profilePath(profileId) {
  return `/api/profiles/${encodeURIComponent(profileId)}`;
}

/**
 * Refresh `store.profiles` and `store.defaultProfile` from the server.
 *
 * @param {{get: function(): Object, set: function(Object): void}} store
 * @returns {Promise<Array<Object>>} The summaries, newest first as the server
 *   ordered them.
 */
export async function refreshProfileList(store) {
  const owner = store.get().user?.id ?? null;
  if (owner !== cacheOwner) {
    payloads.clear();
    cacheOwner = owner;
  }

  const data = await request("/api/profiles");
  // `profiles_meta` is the shape both repositories return; the bare `profiles`
  // list is the fallback for an older server that only sends ids.
  const profiles = Array.isArray(data.profiles_meta) && data.profiles_meta.length
    ? data.profiles_meta
    : (data.profiles || []).map((id) => ({ id, label: id, is_builtin: false }));

  const live = new Set(profiles.map((profile) => profile.id));
  for (const id of [...payloads.keys()]) {
    if (!live.has(id)) payloads.delete(id);
  }

  store.set({ profiles, defaultProfile: data.default });
  return profiles;
}

/**
 * @param {string} profileId
 * @param {Object} [options]
 * @param {boolean} [options.refresh] Bypass the cache. Editing always does: the
 *   editor must open on what the server holds, not on what a card showed.
 * @returns {Promise<Object>} The payload.
 */
export async function loadProfilePayload(profileId, { refresh = false } = {}) {
  if (!refresh && payloads.has(profileId)) return payloads.get(profileId);

  const data = await request(profilePath(profileId));
  const payload = data.profile || {};
  payloads.set(profileId, payload);
  return payload;
}

/** The payload if it has already been fetched, else null. Never a request. */
export function cachedProfilePayload(profileId) {
  return payloads.get(profileId) || null;
}

/**
 * @param {Object} payload
 * @returns {Promise<{id: string, profile: Object}>} The id the server assigned,
 *   which is derived from `label` and is not necessarily what a caller expected.
 */
export async function createProfile(payload) {
  // `name` is stripped by `sanitiseProfile`: bierre-ca ignores a client id, the
  // YAML repository honours one, and a client that sends it makes the two modes
  // disagree about which profile it just wrote.
  const created = await request("/api/profiles", { method: "POST", body: sanitiseProfile(payload) });
  payloads.set(created.id, created.profile);
  return created;
}

export async function updateProfile(profileId, payload) {
  const updated = await request(profilePath(profileId), {
    method: "PUT",
    body: sanitiseProfile(payload),
  });
  payloads.set(updated.id ?? profileId, updated.profile);
  return updated;
}

export async function deleteProfile(profileId) {
  await request(profilePath(profileId), { method: "DELETE" });
  payloads.delete(profileId);
}
