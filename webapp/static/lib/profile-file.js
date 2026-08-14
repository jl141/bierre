/**
 * The profile *file* format: the versioned export envelope, format detection,
 * and the client-side pre-checks an import runs before anything is sent.
 *
 * Three rules from `PRD-USER-ACCOUNTS.md` §8 and UI PRD §6.2 are enforced here
 * rather than at the call sites, because each one is easy to get wrong once and
 * then wrong everywhere:
 *
 * 1. **The envelope is the file format, never the API body.** `POST`/`PUT`
 *    bodies stay envelope-free; only a file carries `schema`, `schema_version`,
 *    `exported_at` and `exported_by`. An unknown `schema_version` is refused
 *    with a readable message instead of being half-applied.
 * 2. **An id in a file is never honoured.** The slug is re-derived from `label`,
 *    which is why `name` is stripped on both the way out and the way in. This
 *    matters more than it looks: `bierre-ca` ignores a client-supplied id, but
 *    the local YAML repository *accepts* one, so a file that kept its `name`
 *    would import onto a different id in the two modes — and could land on a
 *    file someone else's profile already owns.
 * 3. **Two id lengths, on purpose.** A slug derived from a label is ≤64; a
 *    stored slug is ≤96, because the extra 32 characters are headroom for the
 *    `-2`, `-3` collision suffix. Validation on the way in must accept 96, or a
 *    legitimately exported `…-2.bierre.yaml` fails to re-import.
 *
 * Server-side validation stays authoritative. Everything below exists to turn
 * the common failures into an instant, readable error instead of a round trip.
 */

import { dumpYaml, parseYaml, YamlError } from "./yaml.js";

export const EXPORT_SCHEMA = "bierre.domain-profile";
export const EXPORT_SCHEMA_VERSION = 1;
/** Mirrors `EXPORTED_BY` in `bierre-ca/app/schemas/profiles.py`. */
export const EXPORTED_BY = "bierre 1.0";

/** Mirrors `MAX_BODY_BYTES` in `bierre-ca/app/api/profiles.py`. */
export const MAX_FILE_BYTES = 256 * 1024;

export const PROFILE_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
/** A slug as stored and sent. */
export const MAX_ID_LENGTH = 96;
/** A slug as derived from a label, before any collision suffix. */
export const MAX_DERIVED_ID_LENGTH = 64;

/**
 * Every field a profile payload may carry, in the order the YAML repository
 * writes them. Used to reject unknown fields early and to keep an exported file
 * diffable against the checked-in `profiles/*.yaml`.
 */
export const PROFILE_FIELDS = [
  "label",
  "default_question",
  "concepts",
  "query_groups",
  "off_topic_terms",
  "journal_terms",
  "term_groups",
  "intents",
  "buckets",
  "extraction_fields",
];

const FIELD_LABELS = {
  label: "Label",
  default_question: "Default question",
  concepts: "Concepts",
  query_groups: "Query groups",
  off_topic_terms: "Off-topic terms",
  journal_terms: "Journal terms",
  term_groups: "Term groups",
  intents: "Intents",
  buckets: "Buckets",
  extraction_fields: "Extraction fields",
};

const MAPPING_FIELDS = ["query_groups", "term_groups", "intents"];
const LIST_OF_STRINGS_FIELDS = ["off_topic_terms", "journal_terms"];
const LIST_OF_OBJECTS_FIELDS = ["concepts", "buckets", "extraction_fields"];

/** A file that cannot be turned into a profile. The message is user-facing. */
export class ProfileFileError extends Error {
  constructor(message) {
    super(message);
    this.name = "ProfileFileError";
  }
}

/** A blank payload, with the one bucket a profile cannot work without. */
export function emptyProfile() {
  return {
    label: "",
    default_question: "",
    concepts: [],
    query_groups: {},
    off_topic_terms: [],
    journal_terms: [],
    term_groups: {},
    intents: {},
    // Every paper has to land somewhere, so a profile needs one fallback bucket;
    // `bierre-ca` rejects a payload with none.
    buckets: [{ id: "all", label: "Relevant", boost: 0, requires: [], exclude_off_topic: false, fallback: true }],
    extraction_fields: [],
  };
}

/**
 * The slug a label would produce, mirroring `generate_profile_id()` in
 * `core/repositories/yaml_profile_repository.py` verb for verb — including the
 * 64-character truncation *before* slugifying — so a profile exported from local
 * mode lands on the same id when it is imported into the hosted service.
 *
 * @param {string} label
 * @returns {string} A slug matching `PROFILE_ID_PATTERN`, never empty.
 */
export function slugFromLabel(label) {
  const truncated = String(label || "").slice(0, MAX_DERIVED_ID_LENGTH);
  const ascii = truncated
    // NFKD then dropping the combining marks is what Python's
    // `unicodedata.normalize("NFKD", …).encode("ascii", "ignore")` does: "Zürich"
    // becomes "zurich" rather than "z-rich".
    .normalize("NFKD")
    .replace(/\p{M}+/gu, "")
    // Non-ASCII only. A tab or a newline *is* ASCII and has to reach the next
    // step, where it becomes a hyphen — which is what Python's
    // `encode("ascii", "ignore")` followed by `re.sub(r"[^a-z0-9]+", "-", …)`
    // does with it. Dropping it here would silently produce a different slug.
    .replace(/[^\p{ASCII}]+/gu, "");

  const slug = ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");

  return slug || "profile";
}

export function isValidProfileId(id) {
  return (
    typeof id === "string" && id.length <= MAX_ID_LENGTH && PROFILE_ID_PATTERN.test(id)
  );
}

// --- export ------------------------------------------------------------------

/**
 * Wrap a payload in the versioned exchange envelope.
 *
 * @param {Object} profile A payload as `GET /api/profiles/{id}` returns it.
 * @param {Date} [now] Injectable so a test does not depend on the clock.
 */
export function buildExportEnvelope(profile, now = new Date()) {
  return {
    schema: EXPORT_SCHEMA,
    schema_version: EXPORT_SCHEMA_VERSION,
    exported_at: now.toISOString(),
    exported_by: EXPORTED_BY,
    profile: sanitiseProfile(profile),
  };
}

/** Known fields only, in canonical order, with any `name`/`id` dropped. */
export function sanitiseProfile(profile) {
  const source = profile && typeof profile === "object" ? profile : {};
  const payload = {};
  for (const field of PROFILE_FIELDS) {
    if (source[field] !== undefined) payload[field] = source[field];
  }
  return payload;
}

/**
 * @param {Object} envelope
 * @param {"json"|"yaml"} format
 * @returns {{text: string, mediaType: string}}
 */
export function serialiseEnvelope(envelope, format) {
  if (format === "yaml") {
    return { text: dumpYaml(envelope), mediaType: "application/yaml;charset=utf-8" };
  }
  return { text: `${JSON.stringify(envelope, null, 2)}\n`, mediaType: "application/json;charset=utf-8" };
}

/** `n-halamine.bierre.yaml` — the double extension is what UI PRD §6.2 asks for. */
export function exportFilename(profileId, format) {
  const stem = isValidProfileId(profileId) ? profileId : "profile";
  return `${stem}.bierre.${format === "yaml" ? "yaml" : "json"}`;
}

/**
 * Hand a generated file to the browser's download machinery.
 *
 * An object URL rather than a `data:` URI because a profile can be tens of
 * kilobytes and `data:` has a length ceiling in some engines. The URL is revoked
 * on the next frame: revoking it synchronously races the download in WebKit.
 */
export function saveTextFile(filename, text, mediaType) {
  const url = URL.createObjectURL(new Blob([text], { type: mediaType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  requestAnimationFrame(() => URL.revokeObjectURL(url));
}

// --- import ------------------------------------------------------------------

/**
 * Read, parse and pre-validate a profile file chosen by the user.
 *
 * @param {File} file
 * @returns {Promise<{profile: Object, format: "json"|"yaml", enveloped: boolean,
 *                    filename: string, derivedId: string}>}
 * @throws {ProfileFileError} With a message written for the person who picked
 *   the file, never a raw parser exception.
 */
export async function readProfileFile(file) {
  if (!file) throw new ProfileFileError("No file was selected.");
  if (file.size > MAX_FILE_BYTES) {
    throw new ProfileFileError(
      `That file is ${Math.round(file.size / 1024)} KB. A profile must be under ${MAX_FILE_BYTES / 1024} KB.`,
    );
  }

  const text = await file.text();
  if (!text.trim()) throw new ProfileFileError("That file is empty.");

  const { document: parsed, format } = parseDocument(text, file.name);
  const enveloped = isEnvelope(parsed);
  const profile = enveloped ? unwrapEnvelope(parsed) : parsed;

  if (!isPlainObject(profile)) {
    throw new ProfileFileError("That file does not contain a profile object.");
  }

  const problems = describeProblems(profile);
  if (problems.length) throw new ProfileFileError(problems[0]);

  return {
    profile: sanitiseProfile(profile),
    format,
    enveloped,
    filename: file.name,
    derivedId: slugFromLabel(profile.label),
  };
}

/**
 * Format is decided by extension and confirmed by parsing. A file named `.json`
 * that is really YAML still imports — the user should not have to know, and
 * "never make them pick from a dropdown" is the requirement.
 */
function parseDocument(text, filename) {
  const byExtension = formatFromFilename(filename);
  const bySniff = /^[[{]/.test(text.trimStart()) ? "json" : "yaml";
  const order = byExtension ? [byExtension, byExtension === "json" ? "yaml" : "json"] : [bySniff];

  let firstFailure = null;
  for (const format of order) {
    try {
      return { document: parseAs(text, format), format };
    } catch (error) {
      firstFailure = firstFailure || error;
    }
  }
  throw new ProfileFileError(`That file could not be read: ${firstFailure.message}`);
}

function parseAs(text, format) {
  if (format === "json") return JSON.parse(text);
  try {
    return parseYaml(text);
  } catch (error) {
    // A YamlError already carries a line number and plain-language cause.
    throw error instanceof YamlError ? error : new ProfileFileError(String(error.message));
  }
}

function formatFromFilename(filename) {
  const name = String(filename || "").toLowerCase();
  if (name.endsWith(".json")) return "json";
  if (name.endsWith(".yaml") || name.endsWith(".yml")) return "yaml";
  return null;
}

/**
 * An envelope is recognised by any of its own keys being present, not by all of
 * them: a file with `schema_version` but no `profile` is a broken envelope and
 * has to be reported as one, not silently treated as a bare profile.
 */
function isEnvelope(document) {
  if (!isPlainObject(document)) return false;
  return ["schema", "schema_version", "exported_at", "exported_by", "profile"].some(
    (key) => key in document,
  );
}

function unwrapEnvelope(envelope) {
  if (envelope.schema !== undefined && envelope.schema !== EXPORT_SCHEMA) {
    throw new ProfileFileError(
      `That file says it holds "${envelope.schema}", which is not a bierre domain profile.`,
    );
  }
  if (envelope.schema_version !== EXPORT_SCHEMA_VERSION) {
    throw new ProfileFileError(
      `That file uses profile format version ${envelope.schema_version}. This version of bierre reads version ${EXPORT_SCHEMA_VERSION}.`,
    );
  }
  if (!isPlainObject(envelope.profile)) {
    throw new ProfileFileError("That file has a profile envelope but no profile inside it.");
  }
  return envelope.profile;
}

// --- pre-validation ----------------------------------------------------------

/**
 * Problems a user can fix, most important first. Empty means "worth sending".
 *
 * Deliberately shallower than the server's schema: this catches the wrong file
 * and the wrong shape, and leaves rules that can change (bucket counts, list
 * ceilings, exactly-one-fallback) to `DomainProfilePayloadModel`, so a policy
 * change there does not need a front-end release to take effect.
 *
 * @param {Object} profile
 * @returns {string[]}
 */
export function describeProblems(profile) {
  if (!isPlainObject(profile)) return ["That file does not contain a profile object."];

  const problems = [];
  const unknown = Object.keys(profile).filter(
    (key) => key !== "name" && !PROFILE_FIELDS.includes(key),
  );
  if (unknown.length) problems.push(`Unknown profile fields: ${unknown.join(", ")}.`);

  if (!String(profile.label || "").trim()) problems.push("The profile has no label.");

  for (const field of MAPPING_FIELDS) {
    const value = profile[field];
    if (value == null) continue;
    if (!isPlainObject(value)) {
      problems.push(`${FIELD_LABELS[field]} must be a set of named lists.`);
    } else if (!Object.values(value).every(isStringList)) {
      problems.push(`Every entry in ${FIELD_LABELS[field].toLowerCase()} must be a list of terms.`);
    }
  }

  for (const field of LIST_OF_STRINGS_FIELDS) {
    if (profile[field] != null && !isStringList(profile[field])) {
      problems.push(`${FIELD_LABELS[field]} must be a list of terms.`);
    }
  }

  for (const field of LIST_OF_OBJECTS_FIELDS) {
    const value = profile[field];
    if (value == null) continue;
    if (!Array.isArray(value) || !value.every(isPlainObject)) {
      problems.push(`${FIELD_LABELS[field]} must be a list of entries.`);
    }
  }

  return problems;
}

/**
 * Which fields differ between a stored profile and an incoming one, phrased for
 * the Overwrite decision: "buckets (2 → 4)" is what tells a user whether the
 * file they are importing is the same profile with a tweak or a different one.
 *
 * @returns {string[]} Empty when the two payloads are equivalent.
 */
export function describeDifferences(existing, incoming) {
  const before = sanitiseProfile(existing);
  const after = sanitiseProfile(incoming);

  return PROFILE_FIELDS.filter(
    (field) => JSON.stringify(before[field] ?? null) !== JSON.stringify(after[field] ?? null),
  ).map((field) => {
    const from = countOf(before[field]);
    const to = countOf(after[field]);
    if (from === null || to === null) return FIELD_LABELS[field];
    return `${FIELD_LABELS[field]} (${from} → ${to})`;
  });
}

/** Entry count for a collection, or null for a scalar field. */
function countOf(value) {
  if (Array.isArray(value)) return value.length;
  if (isPlainObject(value)) return Object.keys(value).length;
  return null;
}

function isStringList(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string" || typeof item === "number");
}

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
