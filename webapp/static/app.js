"use strict";

// Minimal vanilla front-end. Calls the JSON API and renders the result.
// Dependency-free and build-free.

// ── Column definitions ────────────────────────────────────────────────────────
const COLUMNS = [
  { id: "rank",      label: "#",         num: true,  minWidth: 36,  defaultWidth: 48  },
  { id: "relevance", label: "Relevance", num: true,  minWidth: 90,  defaultWidth: 90  },
  { id: "citations", label: "Citations", num: true,  minWidth: 80,  defaultWidth: 80  },
  { id: "impact",    label: "Impact",    tooltip: "Influential citations (Semantic Scholar)",
                                         num: true,  minWidth: 67,  defaultWidth: 67  },
  { id: "bucket",    label: "Bucket",    num: false, minWidth: 96,  defaultWidth: 108 },
  { id: "status",    label: "Status",    num: false, minWidth: 96,  defaultWidth: 108 },
  { id: "paper",     label: "Paper",     num: false, minWidth: 200, defaultWidth: null },
];

const STORAGE_WIDTHS    = "bierre_col_widths_v1";
const STORAGE_VISIBLE   = "bierre_col_visible_v1";
const STORAGE_QUERY     = "bierre_query_v1";
const STORAGE_SETTINGS  = "bierre_settings_v1";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const form             = document.getElementById("search-form");
const runBtn           = document.getElementById("run-btn");
const statusEl         = document.getElementById("status");
const resultsPanel     = document.getElementById("results-panel");
const summaryEl        = document.getElementById("summary");
const tableBody        = document.getElementById("results-body");
const selectedOnly     = document.getElementById("selected-only");
const profileSelect    = document.getElementById("profile");
const resetWidthsBtn   = document.getElementById("reset-widths-btn");
const colPickerList    = document.getElementById("col-picker-list");
const settingsDetails  = document.getElementById("settings-details");
const resetBasicBtn    = document.getElementById("reset-basic-btn");
const resetAdvancedBtn = document.getElementById("reset-advanced-btn");
const profileCreateBtn = document.getElementById("profile-create-btn");
const profileEditBtn   = document.getElementById("profile-edit-btn");
const profileDeleteBtn = document.getElementById("profile-delete-btn");

const profileModal      = document.getElementById("profile-modal");
const profileForm       = document.getElementById("profile-form");
const profileModalTitle = document.getElementById("profile-modal-title");
const profileModalClose = document.getElementById("profile-modal-close");
const profileSaveBtn    = document.getElementById("profile-save-btn");
const profileFormStatus = document.getElementById("profile-form-status");

const profileLabelInput          = document.getElementById("profile-label");
const profileDefaultQuestionInput = document.getElementById("profile-default-question");
const profileConceptsInput       = document.getElementById("profile-concepts");
const profileQueryGroupsInput    = document.getElementById("profile-query-groups");
const profileOffTopicInput       = document.getElementById("profile-off-topic");
const profileJournalTermsInput   = document.getElementById("profile-journal-terms");
const profileIntentsInput        = document.getElementById("profile-intents");
const profileTermGroupsInput     = document.getElementById("profile-term-groups");
const profileBucketsInput        = document.getElementById("profile-buckets");
const profileExtractionInput     = document.getElementById("profile-extraction-fields");

let lastResult    = null;
let serverDefaults = null;
let profilesMeta = [];
let activeProfileMode = "create";
let editingProfileId = null;

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

// ── Query & settings persistence ──────────────────────────────────────────────
function loadQueryState() {
  try { return JSON.parse(localStorage.getItem(STORAGE_QUERY)) || {}; }
  catch { return {}; }
}
function loadSavedSettings() {
  try { return JSON.parse(localStorage.getItem(STORAGE_SETTINGS)) || null; }
  catch { return null; }
}
function saveQueryState() {
  localStorage.setItem(STORAGE_QUERY, JSON.stringify({
    question: document.getElementById("question").value,
    profile:  profileSelect.value,
    offline:  document.getElementById("offline").checked,
  }));
}
function saveSettingsState() {
  if (!currentSettings) return;
  localStorage.setItem(STORAGE_SETTINGS, JSON.stringify(collectSettings()));
}
function restoreQueryState() {
  const saved = loadQueryState();
  if (saved.question) document.getElementById("question").value = saved.question;
  if (saved.offline  != null) document.getElementById("offline").checked = saved.offline;
}

// Deep-merge source into target in-place. Arrays are replaced, not merged.
function deepMerge(target, source) {
  for (const [k, v] of Object.entries(source)) {
    if (v !== null && v !== undefined && typeof v === "object" && !Array.isArray(v)) {
      if (target[k] == null) target[k] = {};
      deepMerge(target[k], v);
    } else if (v !== null && v !== undefined) {
      target[k] = v;
    }
  }
}

function colWidth(id, stored) {
  if (stored[id] != null) return stored[id];
  return COLUMNS.find(c => c.id === id)?.defaultWidth ?? null;
}
function colVisible(id, stored) {
  return stored[id] != null ? stored[id] : true;
}

function profileLabel(profileId) {
  const match = profilesMeta.find(item => item.id === profileId);
  return match?.label || profileId;
}

function getSelectedProfileId() {
  return String(profileSelect.value || "").trim();
}

function setInlineStatus(el, text, isError) {
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.className = "status";
    return;
  }
  el.hidden = false;
  el.textContent = text;
  el.className = "status" + (isError ? " error" : "");
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
    if (col.num)     th.className = "num";
    if (col.tooltip) th.title     = col.tooltip;

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

// ── Profile CRUD + dropdown ───────────────────────────────────────────────────
async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function parseDelimitedList(value) {
  return String(value || "")
    .split(/\n|,/)
    .map(v => v.trim())
    .filter(Boolean);
}

function listToLines(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return values.map(v => String(v)).join("\n");
}

function prettyJson(value, fallback) {
  const source = value == null ? fallback : value;
  return JSON.stringify(source, null, 2);
}

function parseJsonField(raw, fallback, label) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
}

function ensureType(value, expected, label) {
  if (expected === "array" && !Array.isArray(value)) {
    throw new Error(`${label} must be a JSON array.`);
  }
  if (expected === "object" && (typeof value !== "object" || value == null || Array.isArray(value))) {
    throw new Error(`${label} must be a JSON object.`);
  }
}

function updateProfileActionState() {
  const hasSelection = Boolean(getSelectedProfileId());
  profileEditBtn.disabled = !hasSelection;
  profileDeleteBtn.disabled = !hasSelection;
}

function renderProfileOptions(defaultProfile, preferredProfile) {
  profileSelect.innerHTML = "";
  for (const meta of profilesMeta) {
    const opt = document.createElement("option");
    opt.value = meta.id;
    opt.textContent = meta.label;
    profileSelect.appendChild(opt);
  }

  const savedProfile = loadQueryState().profile;
  const candidates = [preferredProfile, savedProfile, defaultProfile];
  const selectable = new Set(profilesMeta.map(item => item.id));

  for (const candidate of candidates) {
    if (candidate && selectable.has(candidate)) {
      profileSelect.value = candidate;
      break;
    }
  }

  if (!profileSelect.value && profilesMeta.length) {
    profileSelect.value = profilesMeta[0].id;
  }

  updateProfileActionState();
  saveQueryState();
}

async function loadProfiles(preferredProfile) {
  const data = await fetchJson("/api/profiles");
  const metadata = Array.isArray(data.profiles_meta)
    ? data.profiles_meta
    : (data.profiles || []).map(name => ({ id: name, label: name }));

  profilesMeta = metadata;
  renderProfileOptions(data.default, preferredProfile);
}

function resetProfileForm(profile) {
  profileLabelInput.value = profile.label || "";
  profileDefaultQuestionInput.value = profile.default_question || "";
  profileConceptsInput.value = prettyJson(profile.concepts, []);
  profileQueryGroupsInput.value = prettyJson(profile.query_groups, {});
  profileOffTopicInput.value = listToLines(profile.off_topic_terms);
  profileJournalTermsInput.value = listToLines(profile.journal_terms);
  profileIntentsInput.value = prettyJson(profile.intents, {});
  profileTermGroupsInput.value = prettyJson(profile.term_groups, {});
  profileBucketsInput.value = prettyJson(profile.buckets, []);
  profileExtractionInput.value = prettyJson(profile.extraction_fields, []);
  setInlineStatus(profileFormStatus, "", false);
}

function profileTemplate() {
  return {
    label: "",
    default_question: "",
    concepts: [],
    query_groups: {},
    off_topic_terms: [],
    journal_terms: [],
    intents: {},
    term_groups: {},
    buckets: [
      { id: "all", label: "Relevant", boost: 0.0, fallback: true },
    ],
    extraction_fields: [],
  };
}

async function openCreateProfileModal() {
  activeProfileMode = "create";
  editingProfileId = null;
  profileModalTitle.textContent = "Create profile";
  profileSaveBtn.textContent = "Create profile";
  resetProfileForm(profileTemplate());
  profileModal.showModal();
  profileLabelInput.focus();
}

async function openEditProfileModal() {
  const profileId = getSelectedProfileId();
  if (!profileId) return;

  try {
    const data = await fetchJson(`/api/profiles/${encodeURIComponent(profileId)}`);
    activeProfileMode = "edit";
    editingProfileId = profileId;
    profileModalTitle.textContent = `Edit profile: ${profileLabel(profileId)}`;
    profileSaveBtn.textContent = "Save changes";
    resetProfileForm(data.profile || profileTemplate());
    profileModal.showModal();
    profileLabelInput.focus();
  } catch (err) {
    setStatus(`Error: ${err.message}`, true, false);
  }
}

function closeProfileModal() {
  profileModal.close();
  setInlineStatus(profileFormStatus, "", false);
}

function collectProfilePayload() {
  const label = String(profileLabelInput.value || "").trim();
  if (!label) throw new Error("Profile label is required.");

  const concepts = parseJsonField(profileConceptsInput.value, [], "Concepts");
  const queryGroups = parseJsonField(profileQueryGroupsInput.value, {}, "Query groups");
  const intents = parseJsonField(profileIntentsInput.value, {}, "Intents");
  const termGroups = parseJsonField(profileTermGroupsInput.value, {}, "Term groups");
  const buckets = parseJsonField(profileBucketsInput.value, [], "Buckets");
  const extractionFields = parseJsonField(profileExtractionInput.value, [], "Extraction fields");

  ensureType(concepts, "array", "Concepts");
  ensureType(queryGroups, "object", "Query groups");
  ensureType(intents, "object", "Intents");
  ensureType(termGroups, "object", "Term groups");
  ensureType(buckets, "array", "Buckets");
  ensureType(extractionFields, "array", "Extraction fields");

  return {
    label,
    default_question: String(profileDefaultQuestionInput.value || "").trim(),
    concepts,
    query_groups: queryGroups,
    off_topic_terms: parseDelimitedList(profileOffTopicInput.value),
    journal_terms: parseDelimitedList(profileJournalTermsInput.value),
    intents,
    term_groups: termGroups,
    buckets,
    extraction_fields: extractionFields,
  };
}

async function saveProfileFromModal(event) {
  event.preventDefault();
  try {
    const payload = collectProfilePayload();
    profileSaveBtn.disabled = true;

    let selectedAfterSave = getSelectedProfileId();
    if (activeProfileMode === "edit" && editingProfileId) {
      await fetchJson(`/api/profiles/${encodeURIComponent(editingProfileId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      selectedAfterSave = editingProfileId;
    } else {
      const created = await fetchJson("/api/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      selectedAfterSave = created.id;
    }

    await loadProfiles(selectedAfterSave);
    closeProfileModal();
    setStatus("Profile saved.", false, false);
  } catch (err) {
    setInlineStatus(profileFormStatus, `Error: ${err.message}`, true);
  } finally {
    profileSaveBtn.disabled = false;
  }
}

async function deleteSelectedProfile() {
  const profileId = getSelectedProfileId();
  if (!profileId) return;
  const label = profileLabel(profileId);
  const ok = window.confirm(`Delete profile \"${label}\"? This cannot be undone.`);
  if (!ok) return;

  try {
    await fetchJson(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
    await loadProfiles();
    setStatus(`Profile \"${label}\" deleted.`, false, false);
  } catch (err) {
    setStatus(`Error: ${err.message}`, true, false);
  }
}

// ── Form submit ───────────────────────────────────────────────────────────────
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const offline = document.getElementById("offline").checked;
  saveQueryState();
  saveSettingsState();
  runBtn.disabled = true;
  setStatus(
    offline
      ? "Running offline test…"
      : "Searching free scholarly sources — this can take 1–3 minutes.",
    false, !offline
  );

  try {
    const response = await fetch("/api/run", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: document.getElementById("question").value,
        profile:  profileSelect.value,
        offline,
        settings: collectSettings(),
      }),
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "Run failed");
    lastResult = data;
    render(data);
    settingsDetails.open = false;
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
  const profileName = profileLabel(data.profile);
  summaryEl.textContent =
    `Profile "${profileName}" · ${data.mode} · found ${data.counts.found} papers, ` +
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
      case "citations":
        td.textContent = p.citation_count != null ? p.citation_count.toLocaleString() : "—";
        break;
      case "impact":
        td.textContent = p.influential_citation_count != null ? p.influential_citation_count.toLocaleString() : "—";
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

// ── Profile form tooltips ────────────────────────────────────────────────────
let activeTipEl = null;
const hoverTip = document.createElement("div");
hoverTip.className = "hover-tip";
hoverTip.hidden = true;
profileModal.appendChild(hoverTip);

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function positionHoverTip(anchor) {
  const margin = 8;
  const rect = anchor.getBoundingClientRect();
  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;

  hoverTip.style.left = "0px";
  hoverTip.style.top = "0px";

  const tipRect = hoverTip.getBoundingClientRect();
  const centeredX = rect.left + (rect.width / 2) - (tipRect.width / 2);
  const x = clamp(centeredX, margin, viewportW - tipRect.width - margin);

  const preferredTop = rect.top - tipRect.height - margin;
  const top = preferredTop >= margin
    ? preferredTop
    : clamp(rect.bottom + margin, margin, viewportH - tipRect.height - margin);

  hoverTip.style.left = `${Math.round(x)}px`;
  hoverTip.style.top = `${Math.round(top)}px`;
}

function showHoverTip(anchor) {
  const text = String(anchor.dataset.tip || "").trim();
  if (!text) return;
  activeTipEl = anchor;
  hoverTip.textContent = text;
  hoverTip.hidden = false;
  positionHoverTip(anchor);
}

function hideHoverTip(anchor) {
  if (anchor && activeTipEl !== anchor) return;
  activeTipEl = null;
  hoverTip.hidden = true;
  hoverTip.textContent = "";
}

function initProfileTooltips() {
  document.querySelectorAll(".tip[data-tip]").forEach((tip) => {
    tip.addEventListener("mouseenter", () => showHoverTip(tip));
    tip.addEventListener("mouseleave", () => hideHoverTip(tip));
    tip.addEventListener("focus", () => showHoverTip(tip));
    tip.addEventListener("blur", () => hideHoverTip(tip));
  });

  window.addEventListener("scroll", () => {
    if (activeTipEl) positionHoverTip(activeTipEl);
  }, true);
  window.addEventListener("resize", () => {
    if (activeTipEl) positionHoverTip(activeTipEl);
  });
}

// ── Settings panel ────────────────────────────────────────────────────────────
const ALL_SOURCES = ["openalex", "crossref", "pubmed", "europepmc", "semantic_scholar"];

let currentSettings = null;

async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    currentSettings = await r.json();
  } catch {
    // Fall back to sensible defaults so the panel still renders.
    currentSettings = {
      contact_email: "",
      api_keys: { openalex: "", semantic_scholar: "", ncbi: "" },
      search: { max_results_per_query: 10, max_queries_per_run: 12,
                concurrent_workers: 8, timeout_seconds: 20,
                enabled_sources: [...ALL_SOURCES] },
      selection: { top_n: 25 },
    };
  }
  // Keep a pristine copy of server defaults for the reset buttons.
  serverDefaults = JSON.parse(JSON.stringify(currentSettings));

  // Overlay any saved user overrides on top of the server values.
  const saved = loadSavedSettings();
  if (saved) deepMerge(currentSettings, saved);

  buildSettingsPanel();
}

// Nested-path helper: setNestedPath({}, "search.top_n", 5) → {search:{top_n:5}}
function setNestedPath(obj, path, val) {
  const parts = path.split(".");
  let node = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (node[parts[i]] == null) node[parts[i]] = {};
    node = node[parts[i]];
  }
  node[parts[parts.length - 1]] = val;
}

// A label + control row.
function makeSettingRow(labelText, control) {
  const row = document.createElement("div");
  row.className = "setting-row";
  const lbl = document.createElement("span");
  lbl.className = "setting-label";
  lbl.textContent = labelText;
  row.appendChild(lbl);
  row.appendChild(control);
  return row;
}

// Inline-editable number control with − / + buttons.
function makeNumControl(path, value, min, max, step) {
  const wrap = document.createElement("div");
  wrap.className = "num-ctl";
  wrap.dataset.path = path;

  const downBtn = document.createElement("button");
  downBtn.type = "button";
  downBtn.className = "num-btn";
  downBtn.textContent = "-";

  const valSpan = document.createElement("span");
  valSpan.className = "num-val";
  valSpan.textContent = value;
  valSpan.title = "Click to edit";
  valSpan.tabIndex = 0;
  valSpan.setAttribute("role", "spinbutton");
  valSpan.setAttribute("aria-label", path.split(".").slice(-1)[0].replace(/_/g, " "));
  valSpan.setAttribute("aria-valuemin", String(min));
  valSpan.setAttribute("aria-valuemax", String(max));
  valSpan.setAttribute("aria-valuenow", String(value));

  const upBtn = document.createElement("button");
  upBtn.type = "button";
  upBtn.className = "num-btn";
  upBtn.textContent = "+";

  let editing = false;

  function clamp(v) { return Math.min(max, Math.max(min, isNaN(v) ? min : v)); }
  function getCurrent() { return parseInt(valSpan.textContent, 10); }
  function syncA11yValue(nextValue) {
    valSpan.setAttribute("aria-valuenow", String(nextValue));
  }

  function startEditing() {
    if (editing) return;
    editing = true;

    const input = document.createElement("input");
    input.type = "number";
    input.className = "num-inline";
    input.min = min; input.max = max; input.step = step;
    input.value = getCurrent();
    valSpan.replaceWith(input);
    input.focus();
    input.select();

    function commit() {
      const nextValue = clamp(parseInt(input.value, 10));
      valSpan.textContent = nextValue;
      syncA11yValue(nextValue);
      input.replaceWith(valSpan);
      editing = false;
      valSpan.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function cancel() {
      input.replaceWith(valSpan);
      editing = false;
    }

    input.addEventListener("blur", commit);
    input.addEventListener("keydown", e => {
      if (e.key === "Enter")  { e.preventDefault(); commit(); }
      if (e.key === "Escape") { cancel(); }
    });
  }

  downBtn.addEventListener("click", () => {
    const nextValue = clamp(getCurrent() - step);
    valSpan.textContent = nextValue;
    syncA11yValue(nextValue);
    wrap.dispatchEvent(new Event("change", { bubbles: true }));
  });
  upBtn.addEventListener("click", () => {
    const nextValue = clamp(getCurrent() + step);
    valSpan.textContent = nextValue;
    syncA11yValue(nextValue);
    wrap.dispatchEvent(new Event("change", { bubbles: true }));
  });

  valSpan.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      startEditing();
    }
  });
  valSpan.addEventListener("focus", startEditing);
  valSpan.addEventListener("click", startEditing);

  wrap.append(downBtn, valSpan, upBtn);
  return wrap;
}

// Plain text input for emails and API keys.
function makeTextControl(path, value, placeholder) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "setting-text";
  input.dataset.path = path;
  input.value = value || "";
  if (placeholder) input.placeholder = placeholder;
  return input;
}

function buildSettingsPanel() {
  const s = currentSettings;

  // ── Basic settings ──────────────────────────────────────────────────────────
  const basic = document.getElementById("basic-settings");
  basic.innerHTML = "";
  basic.appendChild(makeSettingRow("Max queries per run",
    makeNumControl("search.max_queries_per_run",    s.search.max_queries_per_run,    1, 100, 1)));
  basic.appendChild(makeSettingRow("Results per query",
    makeNumControl("search.max_results_per_query",  s.search.max_results_per_query,  1, 100, 1)));
  basic.appendChild(makeSettingRow("Selected papers",
    makeNumControl("selection.top_n",               s.selection.top_n,               1, 100, 1)));

  // ── Advanced settings ───────────────────────────────────────────────────────
  const adv = document.getElementById("advanced-settings");
  adv.innerHTML = "";

  adv.appendChild(makeSettingRow("Contact email",
    makeTextControl("contact_email", s.contact_email, "user@example.com")));
  adv.appendChild(makeSettingRow("OpenAlex API key",
    makeTextControl("api_keys.openalex",          s.api_keys?.openalex)));
  adv.appendChild(makeSettingRow("Semantic Scholar key",
    makeTextControl("api_keys.semantic_scholar",  s.api_keys?.semantic_scholar)));
  adv.appendChild(makeSettingRow("NCBI API key",
    makeTextControl("api_keys.ncbi",              s.api_keys?.ncbi)));
  adv.appendChild(makeSettingRow("Concurrent workers",
    makeNumControl("search.concurrent_workers",   s.search.concurrent_workers,   1, 24,  1)));
  adv.appendChild(makeSettingRow("Timeout (seconds)",
    makeNumControl("search.timeout_seconds",      s.search.timeout_seconds,      10, 100, 10)));

  // Sources toggles
  const sourcesCtrl = document.createElement("div");
  sourcesCtrl.className = "sources-wrap";
  const enabled = s.search.enabled_sources || ALL_SOURCES;
  for (const src of ALL_SOURCES) {
    const lbl = document.createElement("label");
    lbl.className = "checkbox";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.source = src;
    cb.checked = enabled.includes(src);
    lbl.append(cb, " " + src);
    sourcesCtrl.appendChild(lbl);
  }
  adv.appendChild(makeSettingRow("Sources", sourcesCtrl));
}

// Gather current UI values into an overrides dict for /api/run.
function collectSettings() {
  const out = { search: {}, selection: {}, api_keys: {} };

  document.querySelectorAll("#settings-details .num-ctl[data-path]").forEach(ctl => {
    const valEl = ctl.querySelector(".num-val");
    const inputEl = ctl.querySelector(".num-inline");
    if (valEl) {
      setNestedPath(out, ctl.dataset.path, parseInt(valEl.textContent, 10));
      return;
    }
    if (inputEl) setNestedPath(out, ctl.dataset.path, parseInt(inputEl.value, 10));
  });

  document.querySelectorAll("#settings-details .setting-text[data-path]").forEach(el => {
    setNestedPath(out, el.dataset.path, el.value);
  });

  const checked = [];
  document.querySelectorAll("#advanced-settings input[data-source]").forEach(cb => {
    if (cb.checked) checked.push(cb.dataset.source);
  });
  if (checked.length) out.search.enabled_sources = checked;

  return out;
}

// ── Reset-to-default helpers ─────────────────────────────────────────────────────
function setNumCtlValue(path, value) {
  const ctl = document.querySelector(`#settings-details .num-ctl[data-path="${path}"]`);
  if (ctl) {
    const valEl = ctl.querySelector(".num-val");
    if (valEl) {
      valEl.textContent = value;
      valEl.setAttribute("aria-valuenow", String(value));
    }
  }
}
function setTextCtlValue(path, value) {
  const el = document.querySelector(`#settings-details .setting-text[data-path="${path}"]`);
  if (el) el.value = value ?? "";
}

function resetBasicSettings() {
  if (!serverDefaults) return;
  const s = serverDefaults;
  setNumCtlValue("search.max_queries_per_run",   s.search.max_queries_per_run);
  setNumCtlValue("search.max_results_per_query", s.search.max_results_per_query);
  setNumCtlValue("selection.top_n",              s.selection.top_n);
  saveSettingsState();
}

function resetAdvancedSettings() {
  if (!serverDefaults) return;
  const s = serverDefaults;

  setNumCtlValue("search.concurrent_workers",  s.search.concurrent_workers);
  setNumCtlValue("search.timeout_seconds",     s.search.timeout_seconds);
  setTextCtlValue("contact_email",             s.contact_email);
  setTextCtlValue("api_keys.openalex",         s.api_keys?.openalex);
  setTextCtlValue("api_keys.semantic_scholar", s.api_keys?.semantic_scholar);
  setTextCtlValue("api_keys.ncbi",             s.api_keys?.ncbi);
  const enabled = s.search.enabled_sources ?? ALL_SOURCES;
  document.querySelectorAll("#advanced-settings input[data-source]").forEach(cb => {
    cb.checked = enabled.includes(cb.dataset.source);
  });
  saveSettingsState();
}

// ── Init ──────────────────────────────────────────────────────────────────────────────
resetBasicBtn.addEventListener("click",    resetBasicSettings);
resetAdvancedBtn.addEventListener("click", resetAdvancedSettings);
for (const button of [resetBasicBtn, resetAdvancedBtn]) {
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
  });
}

// Persist settings whenever any control in the settings panel changes.
settingsDetails.addEventListener("change", saveSettingsState);
settingsDetails.addEventListener("input",  saveSettingsState);

// Persist the query form state as the user edits.
document.getElementById("question").addEventListener("input",  saveQueryState);
document.getElementById("offline").addEventListener("change",  saveQueryState);
profileSelect.addEventListener("change", () => {
  saveQueryState();
  updateProfileActionState();
});

profileCreateBtn.addEventListener("click", openCreateProfileModal);
profileEditBtn.addEventListener("click", openEditProfileModal);
profileDeleteBtn.addEventListener("click", deleteSelectedProfile);
profileForm.addEventListener("submit", saveProfileFromModal);
profileModalClose.addEventListener("click", closeProfileModal);
profileModal.addEventListener("cancel", () => setInlineStatus(profileFormStatus, "", false));
profileModal.addEventListener("close", () => hideHoverTip());

buildColPicker();
initProfileTooltips();
loadSettings();
restoreQueryState();
loadProfiles().catch((err) => setStatus(`Error: ${err.message}`, true, false));
