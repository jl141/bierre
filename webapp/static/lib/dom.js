/**
 * Element builder.
 *
 * Replaces `innerHTML` plus hand-written `escapeHtml`/`escapeAttr`. Text and
 * attribute values reach the DOM through `Node.append` and property assignment,
 * so paper titles, journal names and URLs coming from five third-party APIs are
 * never parsed as markup. There is no string to escape, so no call site can
 * forget to escape it.
 */

/**
 * @param {string} tag
 * @param {Object<string, *>|null} [props] Event handlers as `onClick`, dataset
 *   and style as objects, everything else as a property when the element has
 *   one and as an attribute otherwise. `null`, `undefined` and `false` values
 *   are skipped, so `{hidden: someCondition}` reads naturally.
 * @param {...*} children Nodes, strings, numbers, or (nested) arrays of them.
 *   `null`, `undefined` and booleans are skipped so `cond && h(...)` is safe.
 * @returns {HTMLElement}
 */
export function h(tag, props = null, ...children) {
  const el = document.createElement(tag);
  // Children first: `<select value="x">` only takes the value once its
  // <option>s exist, and the same trap applies to any element whose property
  // validates against its content.
  append(el, children);
  if (props) applyProps(el, props);
  return el;
}

/** Document fragment with the same child rules as `h()`. */
export function frag(...children) {
  const fragment = document.createDocumentFragment();
  append(fragment, children);
  return fragment;
}

/** Remove every child of `node`. */
export function clear(node) {
  node.replaceChildren();
  return node;
}

function applyProps(el, props) {
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;

    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "class") {
      el.className = value;
    } else if (key === "dataset" || key === "style") {
      // Both are read-only accessors over a writable object.
      Object.assign(el[key], value);
    } else if (key in el) {
      // Properties over attributes: they coerce correctly (`disabled = true`)
      // and skip the attribute-name mapping (`htmlFor`, `className`).
      // Read-only properties (`form`, `list`) throw here rather than silently
      // doing nothing — pass those as data attributes instead.
      el[key] = value;
    } else {
      // `aria-*`, `role` on older engines, `for`, and any custom attribute.
      el.setAttribute(key, value === true ? "" : String(value));
    }
  }
}

function append(parent, children) {
  for (const child of children) {
    if (child == null || typeof child === "boolean") continue;
    if (Array.isArray(child)) {
      append(parent, child);
      continue;
    }
    parent.append(child);
  }
}
