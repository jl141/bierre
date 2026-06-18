"use strict";

// Minimal vanilla front-end. It calls the JSON API and renders the result;
// it holds no server state. (A React SPA is the Phase 1 step — this stays
// dependency-free and build-free for Phase 0.)

const form = document.getElementById("search-form");
const runBtn = document.getElementById("run-btn");
const statusEl = document.getElementById("status");
const resultsPanel = document.getElementById("results-panel");
const summaryEl = document.getElementById("summary");
const tableBody = document.getElementById("results-body");
const selectedOnly = document.getElementById("selected-only");
const profileSelect = document.getElementById("profile");

let lastResult = null;

// Populate the profile dropdown from the server.
fetch("/api/profiles")
  .then((r) => r.json())
  .then((data) => {
    for (const name of data.profiles || []) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === data.default) opt.selected = true;
      profileSelect.appendChild(opt);
    }
  })
  .catch(() => {});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const offline = document.getElementById("offline").checked;
  runBtn.disabled = true;
  setStatus(
    offline
      ? "Running offline test…"
      : "Searching free scholarly sources — this can take 1–3 minutes.",
    false,
    true
  );

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: document.getElementById("question").value,
        profile: profileSelect.value,
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

function setStatus(text, isError, working) {
  statusEl.hidden = false;
  statusEl.className = "status" + (isError ? " error" : "");
  statusEl.innerHTML = escapeHtml(text) + (working ? '<span class="bar"></span>' : "");
}

function render(data) {
  resultsPanel.hidden = false;
  summaryEl.textContent =
    `Profile "${data.profile}" · ${data.mode} · found ${data.counts.found} papers, ` +
    `selected ${data.counts.selected}. Sources: ${(data.apis_used || []).join(", ") || "none"}.`;

  // The table lists every paper found, including those NOT selected and the
  // reason — the transparency the "view what was removed and why" feature wants.
  const papers = selectedOnly.checked
    ? data.papers.filter((p) => p.selected)
    : data.papers;

  tableBody.innerHTML = "";
  for (const p of papers) {
    const tr = document.createElement("tr");
    if (p.selected) tr.className = "selected";
    const link = p.url
      ? `<a href="${escapeAttr(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
      : escapeHtml(p.title);
    const meta = [p.year, p.journal, (p.sources || []).join(", ")]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" · ");
    tr.innerHTML = `
      <td class="num">${p.rank}</td>
      <td class="num">${p.relevance_percent}%</td>
      <td><span class="badge">${escapeHtml(p.bucket)}</span></td>
      <td><span class="badge ${p.selected ? "on" : ""}">${escapeHtml(p.status)}</span></td>
      <td>
        <div class="title">${link}</div>
        <div class="meta">${meta}</div>
        <div class="reason">${escapeHtml(p.reason)}</div>
      </td>`;
    tableBody.appendChild(tr);
  }
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
function escapeAttr(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}
