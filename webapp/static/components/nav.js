/**
 * Primary navigation. Items appear only when the deployment has the route, and
 * the active one carries `aria-current="page"`.
 */

import { h } from "../lib/dom.js";

/**
 * Nav order is by frequency of use (UI PRD §5). History, Profiles and
 * Subscriptions join the list as their routes land; `visible` is where their
 * capability gate goes.
 */
const NAV_ITEMS = [
  { path: "/", label: "Search", visible: () => true },
];

/**
 * @param {Object} options
 * @param {{get: function(): Object}} options.store
 * @param {{subscribe: function(function(Object): void): function(): void}} options.router
 * @returns {HTMLElement} The `<ul>` for the shell's `<nav>`.
 */
export function createNav({ store, router }) {
  const capabilities = store.get().capabilities;
  const items = NAV_ITEMS.filter((item) => item.visible(capabilities));

  const links = items.map((item) => h("a", { href: `#${item.path}` }, item.label));
  const list = h("ul", null, links.map((link) => h("li", null, link)));

  router.subscribe(({ path }) => {
    items.forEach((item, index) => {
      if (item.path === path) {
        links[index].setAttribute("aria-current", "page");
      } else {
        links[index].removeAttribute("aria-current");
      }
    });
  });

  return list;
}
