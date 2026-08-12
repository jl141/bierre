/**
 * Hash router.
 *
 * Hash rather than History API because the app must work from any mount point
 * and from `file://` — someone who downloaded the project and opened the folder
 * gets a working UI without a rewrite rule on a server they do not run.
 *
 * Accessibility is the router's job, not each view's: after a navigation the
 * focus moves to the new view's `<h1>` and `document.title` changes, which is
 * what makes a screen reader announce that the page changed. Focus is *not*
 * moved on the first render — on initial load the user has not navigated
 * anywhere and belongs at the top of the document.
 */

import { clear } from "./dom.js";

const APP_NAME = "bierre";

/**
 * @param {Object} options
 * @param {HTMLElement} options.outlet Container the active view is mounted in.
 * @param {Array<{path: string, title: string,
 *                view: {mount: function(HTMLElement, Object): void,
 *                       unmount?: function(): void}}>} options.routes
 *   Patterns are `/`-separated, with `:name` segments captured into params.
 * @param {string} [options.fallback] Path to redirect an unknown hash to.
 */
export function createRouter({ outlet, routes, fallback = "/" }) {
  const listeners = new Set();
  let active = null;
  let rendered = false;

  function render() {
    const path = currentPath();
    const matched = resolve(routes, path);

    if (!matched) {
      // Replace rather than push: a typo'd hash should not sit in history.
      location.replace(`#${fallback}`);
      return;
    }

    active?.route.view.unmount?.();
    clear(outlet);
    matched.route.view.mount(outlet, matched.params);
    document.title = `${matched.route.title} — ${APP_NAME}`;

    if (rendered) focusHeading(outlet);
    rendered = true;
    active = matched;

    for (const listener of [...listeners]) listener(matched);
  }

  return {
    start() {
      window.addEventListener("hashchange", render);
      if (!location.hash) location.replace(`#${fallback}`);
      render();
    },

    /** @param {string} path e.g. `/profiles/new` */
    navigate(path) {
      const next = `#${path}`;
      if (location.hash === next) return;
      location.hash = next;
    },

    current() {
      return active;
    },

    /** Notified after every mount; returns the unsubscribe function. */
    subscribe(listener) {
      listeners.add(listener);
      if (active) listener(active);
      return () => listeners.delete(listener);
    },
  };
}

/** The path part of the current hash, always starting with `/`. */
export function currentPath() {
  const hash = location.hash.replace(/^#/, "");
  return hash.startsWith("/") ? hash : "/";
}

function resolve(routes, path) {
  for (const route of routes) {
    const params = matchPath(route.path, path);
    if (params) return { route, params, path };
  }
  return null;
}

function matchPath(pattern, path) {
  const patternSegments = pattern.split("/").filter(Boolean);
  const pathSegments = path.split("/").filter(Boolean);
  if (patternSegments.length !== pathSegments.length) return null;

  const params = {};
  for (const [index, segment] of patternSegments.entries()) {
    if (segment.startsWith(":")) {
      params[segment.slice(1)] = decodeURIComponent(pathSegments[index]);
    } else if (segment !== pathSegments[index]) {
      return null;
    }
  }
  return params;
}

function focusHeading(outlet) {
  const heading = outlet.querySelector("h1");
  if (!heading) return;
  // -1 keeps the heading out of the tab order while making it focusable.
  heading.tabIndex = -1;
  heading.focus();
}
