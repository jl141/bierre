"use strict";

// Minimal vanilla front-end. Calls the JSON API and renders the result.
// Dependency-free and build-free.

// ── Column definitions ────────────────────────────────────────────────────────
const COLUMNS = [
  { id: "rank",      label: "#",         num: true,  minWidth: 36,  defaultWidth: 48  },
  { id: "relevance", label: "Relevance", num: true,  minWidth: 90,  defaultWidth: 90  },
  { id: "bucket",    label: "Bucket",    num: false, minWidth: 96,  defaultWidth: 108 },
  { id: "status",    label: "Status",    num: false, minWidth: 96,  defaultWidth: 108 },
  { id: "paper",     label: "Paper",     num: false, minWidth: 200, defaultWidth: null },
];

const STORAGE_WIDTHS  = "bierre_col_widths_v1";
const STORAGE_VISIBLE = "bierre_col_visible_v1";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const form           = document.getElementById("search-form");
const runBtn         = document.getElementById("run-btn");
const statusEl       = document.getElementById("status");
const resultsPanel   = document.getElementById("results-panel");
const summaryEl      = document.getElementById("summary");
const tableBody      = document.getElementById("results-body");
const selectedOnly   = document.getElementById("selected-only");
const profileSelect  = document.getElementById("profile");
const resetWidthsBtn = document.getElementById("reset-widths-btn");
const colPickerList  = document.getElementById("col-picker-list");

let lastResult = null;

// ── Persistence helpers ───────────────────────────────────────────────────────
function loadWidths() {
  try { return JSON.parse(localStorage.getItem(STORAGE_WIDTHS))  || {}; }
  catch { return {}; }
}
function loadVisible() {
  try { return JSON.parse(localStorage.getItem(STORAGE_VISIBLE)) || {}; }
  catch { return {}; }
}
function saveWidths(w)  { localStorage.setItem(STORAGE_WIDTHS,  JSON.stringify(w)); }
function saveVisible(v) { localStorage.setItem(STORAGE_VISIBLE, JSON.stringify(v)); }

function colWidth(id, stored) {
  if (stored[id] != null) return stored[id];
  return COLUMNS.find(c => c.id === id)?.defaultWidth ?? null;
}
function colVisible(id, stored) {
  return stored[id] != null ? stored[id] : true;
}

// ── Header & colgroup ─────────────────────────────────────────────────────────
function buildHeader() {
  const storedW = loadWidths();
  const storedV = loadVisible();
  const visible = COLUMNS.filter(c => colVisible(c.id, storedV));

  // Rebuild <colgroup>
  const colgroup = document.getElementById("col-group");
  colgroup.innerHTML = "";
  for (const col of visible) {
    const el = document.createElement("col");
    el.id = "col-" + col.id;
    const w = colWidth(col.id, storedW);
    if (w != null) el.style.width = w + "px";
    colgroup.appendChild(el);
  }

  // Rebuild <thead> row
  const headRow = document.getElementById("results-head-row");
  headRow.innerHTML = "";
  for (let i = 0; i < visible.length; i++) {
    const col    = visible[i];
    const th     = document.createElement("th");
    if (col.num) th.className = "num";

    const labelSpan = document.createElement("span");
    labelSpan.textContent = col.label;
    th.appendChild(labelSpan);

    // Resize handle on every column except the last visible one
    if (i < visible.length - 1) {
      const handle = document.createElement("span");
      handle.className = "col-resize";
      handle.addEventListener("mousedown", makeResizeHandler(col.id));
      th.appendChild(handle);
    }
    headRow.appendChild(th);
  }
}

// ── Column resize ─────────────────────────────────────────────────────────────
function makeResizeHandler(colId) {
  return function(e) {
    e.preventDefault();
    const th     = e.currentTarget.closest("th");
    const startX = e.clientX;
    const startW = th.offsetWidth;
    const minW   = COLUMNS.find(c => c.id === colId)?.minWidth ?? 40;

    function onMove(ev) {
      const w     = Math.max(minW, startW + (ev.clientX - startX));
      const colEl = document.getElementById("col-" + colId);
      if (colEl) colEl.style.width = w + "px";
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup",   onUp);
      const colEl = document.getElementById("col-" + colId);
      if (colEl) {
        const stored = loadWidths();
        stored[colId] = parseInt(colEl.style.width, 10);
        saveWidths(stored);
      }
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup",   onUp);
  };
}

// ── Column picker ─────────────────────────────────────────────────────────────
function buildColPicker() {
  colPickerList.innerHTML = "";
  const storedV = loadVisible();
  for (const col of COLUMNS) {
    const label = document.createElement("label");
    label.className = "checkbox";
    const cb = document.createElement("input");
    cb.type    = "checkbox";
    cb.checked = colVisible(col.id, storedV);
    cb.addEventListener("change", () => {
      const v = loadVisible();
      v[col.id] = cb.checked;
      saveVisible(v);
      buildHeader();
      if (lastResult) render(lastResult);
    });
    label.appendChild(cb);
    label.append(" " + col.label);
    colPickerList.appendChild(label);
  }
}

// Close picker when clicking outside
document.addEventListener("click", (e) => {
  const picker = document.getElementById("col-picker");
  if (picker?.open && !picker.contains(e.target)) picker.open = false;
});

// ── Reset column widths ───────────────────────────────────────────────────────
resetWidthsBtn.addEventListener("click", () => {
  saveWidths({});
  buildHeader();
});

// ── Profile dropdown ──────────────────────────────────────────────────────────
fetch("/api/profiles")
  .then(r => r.json())
  .then(data => {
    for (const name of data.profiles || []) {
      const opt       = document.createElement("option");
      opt.value       = name;
      opt.textContent = name;
      if (name === data.default) opt.selected = true;
      profileSelect.appendChild(opt);
    }
  })
  .catch(() => {});

// ── Form submit ───────────────────────────────────────────────────────────────
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const offline = document.getElementById("offline").checked;
  runBtn.disabled = true;
  setStatus(
    offline
      ? "Running offline test…"
      : "Searching free scholarly sources — this can take 1–3 minutes.",
    false, true
  );

  try {
    const response = await fetch("/api/run", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: document.getElementById("question").value,
        profile:  profileSelect.value,
        offline,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "Run failed");
    lastResult = data;
    render(data);
    statusEl.hidden = true;
  } catch (err) {
    setStatus("Error: " + err.message, true, false);
  } finally {
    runBtn.disabled = false;
  }
});

selectedOnly.addEventListener("change", () => {
  if (lastResult) render(lastResult);
});

// ── Rendering ─────────────────────────────────────────────────────────────────
function setStatus(text, isError, working) {
  statusEl.hidden    = false;
  statusEl.className = "status" + (isError ? " error" : "");
  statusEl.innerHTML = escapeHtml(text) + (working ? '<span class="bar"></span>' : "");
}

function render(data) {
  resultsPanel.hidden = false;
  summaryEl.textContent =
    `Profile "${data.profile}" · ${data.mode} · found ${data.counts.found} papers, ` +
    `selected ${data.counts.selected}. Sources: ${(data.apis_used || []).join(", ") || "none"}.`;

  buildHeader();

  // Lists every paper found — includes non-selected rows with reasons for transparency.
  const papers = selectedOnly.checked
    ? data.papers.filter(p => p.selected)
    : data.papers;

  tableBody.innerHTML = "";
  for (const p of papers) tableBody.appendChild(buildRow(p));
}

function buildRow(p) {
  const storedV = loadVisible();
  const tr      = document.createElement("tr");
  if (p.selected) tr.className = "selected";

  const link = p.url
    ? `<a href="${escapeAttr(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
    : escapeHtml(p.title);
  const meta = [p.year, p.journal, (p.sources || []).join(", ")]
    .filter(Boolean).map(escapeHtml).join(" · ");

  for (const col of COLUMNS) {
    if (!colVisible(col.id, storedV)) continue;
    const td = document.createElement("td");
    if (col.num) td.className = "num";
    switch (col.id) {
      case "rank":
        td.textContent = p.rank;
        break;
      case "relevance":
        td.textContent = p.relevance_percent + "%";
        break;
      case "bucket":
        td.innerHTML = `<span class="badge">${escapeHtml(p.bucket)}</span>`;
        break;
      case "status":
        td.innerHTML = `<span class="badge ${p.selected ? "on" : ""}">${escapeHtml(p.status)}</span>`;
        break;
      case "paper":
        td.innerHTML = `
          <div class="title">${link}</div>
          <div class="meta">${meta}</div>
          <div class="reason">${escapeHtml(p.reason)}</div>`;
        break;
    }
    tr.appendChild(td);
  }
  return tr;
}

// ── Escape helpers ────────────────────────────────────────────────────────────
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
function escapeAttr(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}

// ── Init ──────────────────────────────────────────────────────────────────────
buildColPicker();
