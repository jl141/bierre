/**
 * Minimal observable state container — the replacement for the module-level
 * mutable globals the single-file app used (`lastResult`, `serverDefaults`,
 * `profilesMeta`, `currentSettings`, …). Deliberately not a redux: one shallow
 * object, one notify.
 */

/**
 * @param {Object} [initialState]
 * @returns {{get: function(): Object,
 *            set: function(Object|function(Object): Object): void,
 *            subscribe: function(function(Object): void): function(): void}}
 */
export function createStore(initialState = {}) {
  let state = { ...initialState };
  const subscribers = new Set();

  return {
    /** The current state. Treat it as immutable: replace keys, never mutate. */
    get() {
      return state;
    },

    /** Shallow-merge a patch (or the result of `patch(state)`) and notify. */
    set(patch) {
      const changes = typeof patch === "function" ? patch(state) : patch;
      if (!changes) return;

      const changed = Object.keys(changes).some((key) => !Object.is(state[key], changes[key]));
      if (!changed) return;

      state = { ...state, ...changes };
      // Copy first: a subscriber may unsubscribe while we iterate.
      for (const subscriber of [...subscribers]) subscriber(state);
    },

    /** Returns the unsubscribe function. */
    subscribe(subscriber) {
      subscribers.add(subscriber);
      return () => subscribers.delete(subscriber);
    },
  };
}
