/**
 * Results table: column model, resize, column picker, row rendering.
 *
 * Mounted inside the search view for now. When `#/results/:runId` lands it
 * becomes a route of its own; nothing here knows how the run was produced.
 */

import { clear, h } from "../lib/dom.js";
import { appStorage } from "../lib/storage.js";
import { formatCount, formatDecimal, formatPercent } from "../lib/format.js";

const COLUMNS = [
  { id: "rank",      label: "#",         num: true,  minWidth: 36,  defaultWidth: 48  },
  { id: "relevance", label: "Relevance", num: true,  minWidth: 90,  defaultWidth: 90  },
  { id: "citations", label: "Citations", num: true,  minWidth: 80,  defaultWidth: 80  },
  { id: "impact",    label: "Impact",    tooltip: "Journal Impact Factor",
                                         num: true,  minWidth: 67,  defaultWidth: 67  },
  { id: "bucket",    label: "Bucket",    num: false, minWidth: 96,  defaultWidth: 108 },
  { id: "status",    label: "Status",    num: false, minWidth: 96,  defaultWidth: 108 },
  { id: "paper",     label: "Paper",     num: false, minWidth: 200, defaultWidth: null },
];

const EM_DASH = "—";

/**
 * @param {Object} options
 * @param {{get: function(): Object}} options.store Read for `profiles`
 *   (id → label) and `lastResult` (re-render when the filter changes).
 * @returns {{element: HTMLElement, render: function(Object): void,
 *            destroy: function(): void}}
 */
export function createResultsPanel({ store }) {
  const colgroup = h("colgroup", { id: "col-group" });
  const headRow = h("tr", { id: "results-head-row" });
  const tableBody = h("tbody", { id: "results-body" });
  const summary = h("p", { class: "summary", id: "summary" });
  const colPickerList = h("div", { class: "col-picker-list", id: "col-picker-list" });
  const colPicker = h("details", { id: "col-picker" }, h("summary", null, "Columns"), colPickerList);

  const selectedOnly = h("input", {
    type: "checkbox",
    id: "selected-only",
    onChange: () => renderRows(),
  });

  const element = h(
    "section",
    { class: "panel", id: "results-panel", hidden: true },
    h(
      "div",
      { class: "results-head" },
      h("h2", { class: "panel-title" }, "Results"),
      h(
        "div",
        { class: "results-controls" },
        h("label", { class: "checkbox" }, selectedOnly, " Selected only"),
        h("button", {
          type: "button",
          id: "reset-widths-btn",
          class: "btn-ghost",
          onClick: () => {
            appStorage.write("col_widths", {});
            buildHeader();
          },
        }, "Reset widths"),
        colPicker,
      ),
    ),
    summary,
    h(
      "div",
      { class: "table-wrap" },
      h("table", { id: "results-table" }, colgroup, h("thead", null, headRow), tableBody),
    ),
  );

  // Clicking outside the picker closes it. Document-level, so it is removed in
  // destroy() rather than leaking one listener per mount.
  const onDocumentClick = (event) => {
    if (colPicker.open && !colPicker.contains(event.target)) colPicker.open = false;
  };
  document.addEventListener("click", onDocumentClick);

  function widths() {
    return appStorage.read("col_widths", {}) || {};
  }
  function visibility() {
    return appStorage.read("col_visible", {}) || {};
  }
  function columnWidth(id, stored) {
    if (stored[id] != null) return stored[id];
    return COLUMNS.find((column) => column.id === id)?.defaultWidth ?? null;
  }
  function isVisible(id, stored) {
    return stored[id] != null ? stored[id] : true;
  }

  function buildHeader() {
    const storedWidths = widths();
    const storedVisible = visibility();
    const visible = COLUMNS.filter((column) => isVisible(column.id, storedVisible));

    clear(colgroup);
    for (const column of visible) {
      const width = columnWidth(column.id, storedWidths);
      colgroup.append(h("col", {
        id: `col-${column.id}`,
        style: width == null ? {} : { width: `${width}px` },
      }));
    }

    clear(headRow);
    visible.forEach((column, index) => {
      headRow.append(h(
        "th",
        {
          scope: "col",
          class: column.num ? "num" : null,
          title: column.tooltip || null,
        },
        h("span", null, column.label),
        // Every column except the last visible one gets a resize handle.
        index < visible.length - 1
          ? h("span", { class: "col-resize", onMousedown: resizeHandler(column.id) })
          : null,
      ));
    });
  }

  function resizeHandler(columnId) {
    return (event) => {
      event.preventDefault();
      const th = event.currentTarget.closest("th");
      const startX = event.clientX;
      const startWidth = th.offsetWidth;
      const minWidth = COLUMNS.find((column) => column.id === columnId)?.minWidth ?? 40;
      const col = document.getElementById(`col-${columnId}`);

      function onMove(moveEvent) {
        const width = Math.max(minWidth, startWidth + (moveEvent.clientX - startX));
        if (col) col.style.width = `${width}px`;
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        if (!col) return;
        appStorage.write("col_widths", { ...widths(), [columnId]: parseInt(col.style.width, 10) });
      }

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    };
  }

  function buildColPicker() {
    clear(colPickerList);
    const storedVisible = visibility();
    for (const column of COLUMNS) {
      const checkbox = h("input", {
        type: "checkbox",
        checked: isVisible(column.id, storedVisible),
        onChange: () => {
          appStorage.write("col_visible", { ...visibility(), [column.id]: checkbox.checked });
          buildHeader();
          renderRows();
        },
      });
      colPickerList.append(h("label", { class: "checkbox" }, checkbox, ` ${column.label}`));
    }
  }

  function profileLabel(profileId) {
    const match = store.get().profiles.find((item) => item.id === profileId);
    return match?.label || profileId;
  }

  function renderRows() {
    const result = store.get().lastResult;
    clear(tableBody);
    if (!result) return;

    const papers = selectedOnly.checked
      ? result.papers.filter((paper) => paper.selected)
      : result.papers;
    for (const paper of papers) tableBody.append(buildRow(paper));
  }

  function buildRow(paper) {
    const storedVisible = visibility();
    const row = h("tr", { class: paper.selected ? "selected" : null });

    for (const column of COLUMNS) {
      if (!isVisible(column.id, storedVisible)) continue;
      row.append(h("td", { class: column.num ? "num" : null }, cellContent(column.id, paper)));
    }
    return row;
  }

  buildColPicker();

  return {
    element,

    /** Show a run result. Pass it to the store first; this reads from there. */
    render(result) {
      element.hidden = false;
      summary.textContent =
        `Profile "${profileLabel(result.profile_id)}" · ${result.mode} · ` +
        `found ${result.counts.found} papers, selected ${result.counts.selected}. ` +
        `Sources: ${(result.apis_used || []).join(", ") || "none"}.`;
      buildHeader();
      renderRows();
    },

    destroy() {
      document.removeEventListener("click", onDocumentClick);
    },
  };
}

function cellContent(columnId, paper) {
  switch (columnId) {
    case "rank":
      return String(paper.rank);
    case "relevance":
      return formatPercent(paper.relevance_percent);
    case "citations":
      return paper.citation_count != null ? formatCount(paper.citation_count) : EM_DASH;
    case "impact":
      return paper.impact_factor != null ? formatDecimal(Number(paper.impact_factor), 1) : EM_DASH;
    case "bucket":
      return h("span", { class: "badge" }, paper.bucket);
    case "status":
      return h("span", { class: `badge${paper.selected ? " on" : ""}` }, paper.status);
    case "paper":
      return paperCell(paper);
    default:
      return "";
  }
}

function paperCell(paper) {
  const href = safeUrl(paper.url);
  const meta = [paper.year, paper.journal, (paper.sources || []).join(", ")]
    .filter(Boolean)
    .join(" · ");

  return [
    h(
      "div",
      { class: "title" },
      href ? h("a", { href, target: "_blank", rel: "noopener" }, paper.title) : paper.title,
    ),
    h("div", { class: "meta" }, meta),
    h("div", { class: "reason" }, paper.reason),
  ];
}

/**
 * `h()` stops a title from becoming markup, but an `href` is still executable:
 * `javascript:…` from a source adapter would run on click. Only http(s) links
 * are rendered as links; anything else degrades to plain text.
 */
function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value, location.href);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
