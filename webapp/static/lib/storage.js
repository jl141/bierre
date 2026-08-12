/**
 * Namespaced, versioned `localStorage`.
 *
 * Every read and write is guarded: Safari in private mode throws on `setItem`,
 * a quota-full profile throws on write, and a value hand-edited into invalid
 * JSON must not take the app down at boot. Losing a stored column width is not
 * worth an exception.
 *
 * Never put a credential in here. `lib/api.js` keeps the access token in a
 * module variable precisely so it cannot reach this file.
 */

/**
 * @param {string} namespace Key prefix, e.g. `bierre`.
 * @param {number} version Bumped when a stored shape changes incompatibly;
 *   old keys are simply orphaned rather than migrated.
 */
export function createStorage(namespace, version) {
  const keyFor = (name) => `${namespace}_${name}_v${version}`;

  return {
    read(name, fallback = null) {
      try {
        const raw = localStorage.getItem(keyFor(name));
        return raw == null ? fallback : (JSON.parse(raw) ?? fallback);
      } catch {
        return fallback;
      }
    },

    write(name, value) {
      try {
        localStorage.setItem(keyFor(name), JSON.stringify(value));
        return true;
      } catch {
        return false;
      }
    },

    remove(name) {
      try {
        localStorage.removeItem(keyFor(name));
      } catch {
        // Nothing useful to do if even removal is denied.
      }
    },
  };
}

/**
 * The app's own store. The key layout (`bierre_<name>_v1`) is unchanged from
 * the single-file version, so a user's saved widths and settings survive this
 * refactor.
 */
export const appStorage = createStorage("bierre", 1);
