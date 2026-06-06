// NFCorpus Diagnostics Workbench front-end.
// Fetches /api/* endpoints and renders the dashboard.

const els = {
  statusPill: document.getElementById("status-pill"),
  datasetBadge: document.getElementById("dataset-badge"),
  readiness: {
    java: document.getElementById("readiness-java"),
    fatjar: document.getElementById("readiness-fatjar"),
    index: document.getElementById("readiness-index"),
    reproduction: document.getElementById("readiness-reproduction"),
    search: document.getElementById("readiness-search"),
    evaluation: document.getElementById("readiness-evaluation"),
  },
  readinessSummary: document.getElementById("readiness-summary"),
  searchForm: document.getElementById("search-form"),
  searchInput: document.getElementById("search-input"),
  searchHits: document.getElementById("search-hits"),
  searchStatus: document.getElementById("search-status"),
  searchResults: document.getElementById("search-results"),
  sampleQueries: document.getElementById("sample-queries"),
  btnEvaluate: document.getElementById("btn-evaluate"),
  btnVerify: document.getElementById("btn-verify"),
  evalStatus: document.getElementById("eval-status"),
  metricTableBody: document.querySelector("#metric-table tbody"),
  evalElapsed: document.getElementById("eval-elapsed"),
  evalCached: document.getElementById("eval-cached"),
  evalVerdict: document.getElementById("eval-verdict"),
  commandList: document.getElementById("command-list"),
  artifactList: document.getElementById("artifact-list"),
  logPreview: document.getElementById("log-preview"),
  logPreviewBody: document.getElementById("log-preview-body"),
  btnRefreshStatus: document.getElementById("btn-refresh-status"),
  btnToggleDrawer: document.getElementById("btn-toggle-drawer"),
  expectedConfigName: document.getElementById("expected-config-name"),
  footerAnserini: document.getElementById("footer-anserini-version"),
  footerJava: document.getElementById("footer-java-version"),
  footerPort: document.getElementById("footer-port"),
  dataDirLabel: document.getElementById("data-dir-label"),
};

const state = {
  sampleQueries: [],
  lastCommands: [],
  lastArtifacts: [],
  lastEval: null,
};

// ------------------------------------------------------------ utilities

function setDot(item, status) {
  const dot = item.parentElement.querySelector(".dot");
  dot.classList.remove("dot-ok", "dot-warn", "dot-fail", "dot-unknown");
  dot.classList.add(`dot-${status}`);
}

function fmtBytes(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function fmtPct(n) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function fmtNumber(n, digits = 4) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function setStatusLine(el, msg, kind) {
  el.textContent = msg || "";
  el.classList.remove("ok", "error");
  if (kind) el.classList.add(kind);
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// -------------------------------------------------------- readiness

async function loadStatus() {
  setStatusLine(els.readinessSummary, "Loading runtime status…");
  let data;
  try {
    const resp = await fetch("/api/status");
    data = await resp.json();
  } catch (err) {
    setStatusLine(els.readinessSummary, `Failed to load /api/status: ${err}`, "error");
    return;
  }

  const rt = data.runtime || {};
  const java = rt.java || {};
  const fatjar = rt.fatjar || {};
  const index = rt.index || {};
  const dataset = data.dataset || {};

  els.readiness.java.textContent = java.version_string
    ? `${java.version_string}${java.supported ? " (supported)" : " (unsupported)"}`
    : "not found";
  setDot(els.readiness.java.parentElement, java.supported ? "ok" : (java.available ? "warn" : "fail"));

  els.readiness.fatjar.textContent = fatjar.available
    ? `${fatjar.version || "—"} · ${fmtBytes(fatjar.size_bytes)}`
    : "missing — click Refresh to download";
  setDot(els.readiness.fatjar.parentElement, fatjar.available ? "ok" : "warn");

  els.readiness.index.textContent = index.available
    ? `cached (${index.entries.length} entr${index.entries.length === 1 ? "y" : "ies"})`
    : `${index.expected_index} (will download on first use)`;
  setDot(els.readiness.index.parentElement, index.available ? "ok" : "warn");

  els.readiness.reproduction.textContent = `${dataset.reproduction_config} · ${dataset.condition}`;
  setDot(els.readiness.reproduction.parentElement, "ok");

  els.readiness.search.textContent = data.ready_for_live_search ? "ready" : "pending — complete readiness first";
  setDot(els.readiness.search.parentElement, data.ready_for_live_search ? "ok" : "unknown");

  els.readiness.evaluation.textContent = data.ready_for_evaluation ? "ready" : "pending — complete readiness first";
  setDot(els.readiness.evaluation.parentElement, data.ready_for_evaluation ? "ok" : "unknown");

  els.expectedConfigName.textContent = `${dataset.reproduction_config} · ${dataset.condition}`;

  const ready = data.ready_for_live_search;
  els.statusPill.classList.remove("status-ok", "status-warn", "status-fail", "status-unknown");
  if (ready) {
    els.statusPill.classList.add("status-ok");
    els.statusPill.textContent = "readiness: ok";
  } else if (java.available && fatjar.available) {
    els.statusPill.classList.add("status-warn");
    els.statusPill.textContent = "readiness: warming up";
  } else {
    els.statusPill.classList.add("status-fail");
    els.statusPill.textContent = "readiness: degraded";
  }

  els.footerAnserini.textContent = fatjar.version || "—";
  els.footerJava.textContent = java.major || "—";

  setStatusLine(
    els.readinessSummary,
    ready
      ? "Application is ready for live search and BM25 evaluation."
      : "Some prerequisites are missing. Click Refresh to attempt fatjar download and index discovery."
  );

  // Auto-bootstrap: if the fatjar is missing, try to download it.
  if (!fatjar.available) {
    bootstrapFatjar();
  } else {
    await loadArtifacts();
  }
}

async function bootstrapFatjar() {
  setStatusLine(els.readinessSummary, "Anserini fatjar not present — downloading from Maven Central…");
  try {
    const resp = await fetch("/api/setup/fatjar", { method: "POST" });
    const data = await resp.json();
    if (data.ok) {
      setStatusLine(els.readinessSummary, "Fatjar downloaded and verified. Reloading status…");
      await loadStatus();
      await loadArtifacts();
    } else {
      const stage = data.stage || "unknown";
      const err = (data.command && data.command.stderr_excerpt) || "unknown error";
      setStatusLine(els.readinessSummary, `Fatjar setup failed at ${stage}: ${err}`, "error");
    }
  } catch (err) {
    setStatusLine(els.readinessSummary, `Fatjar download failed: ${err}`, "error");
  }
}

async function loadArtifacts() {
  try {
    const resp = await fetch("/api/artifacts");
    const data = await resp.json();
    state.lastArtifacts = data.paths || [];
    if (data.data_dir) els.dataDirLabel.textContent = data.data_dir;
    renderArtifacts();
  } catch (err) {
    // Non-fatal: artifact list is supplementary.
    console.warn("Failed to load artifacts", err);
  }
}

function renderArtifacts() {
  els.artifactList.innerHTML = "";
  if (!state.lastArtifacts.length) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="hint">No artifacts yet. Run a search or evaluation to generate run files and evaluator output.</span>`;
    els.artifactList.appendChild(li);
    return;
  }
  for (const art of state.lastArtifacts) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div><code>${escapeHtml(art.path)}</code>
        <span class="size">${fmtBytes(art.size_bytes)} · ${escapeHtml(art.kind)}</span>
      </div>
    `;
    els.artifactList.appendChild(li);
  }
}

function pushCommand(label, command) {
  state.lastCommands.unshift({ label, command });
  state.lastCommands = state.lastCommands.slice(0, 20);
  renderCommands();
}

function renderCommands() {
  els.commandList.innerHTML = "";
  if (!state.lastCommands.length) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="hint">No commands recorded yet.</span>`;
    els.commandList.appendChild(li);
    return;
  }
  for (const c of state.lastCommands) {
    const li = document.createElement("li");
    li.innerHTML = `<div class="label">${escapeHtml(c.label)}</div><code>${escapeHtml(c.command)}</code>`;
    els.commandList.appendChild(li);
  }
}

// ---------------------------------------------------------- search

function renderSampleQueries(queries) {
  els.sampleQueries.innerHTML = "";
  for (const q of queries) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = q;
    btn.addEventListener("click", () => {
      els.searchInput.value = q;
      runSearch();
    });
    els.sampleQueries.appendChild(btn);
  }
}

async function runSearch() {
  const q = (els.searchInput.value || "").trim();
  if (!q) {
    setStatusLine(els.searchStatus, "Type a query or pick a sample NFCorpus query.", "error");
    return;
  }
  const hits = Math.max(1, Math.min(50, parseInt(els.searchHits.value, 10) || 10));
  setStatusLine(els.searchStatus, `Searching NFCorpus for "${q}" (hits=${hits})…`);
  els.searchResults.innerHTML = "";
  try {
    const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&hits=${hits}`);
    const data = await resp.json();
    if (!data.ok) {
      setStatusLine(els.searchStatus, data.error || "search failed", "error");
      if (data.command) pushCommand("search (failed)", data.command.command);
      return;
    }
    const cmd = data.command || {};
    pushCommand(`live search · hits=${hits}`, cmd.command || "search command unavailable");
    if (cmd.output_paths) cmd.output_paths.forEach((p) => state.lastArtifacts.push({ path: p, size_bytes: null, kind: "logs" }));
    renderResults(data.results || []);
    setStatusLine(
      els.searchStatus,
      `Returned ${data.results.length} result${data.results.length === 1 ? "" : "s"} in ${cmd.elapsed_seconds || "?"}s — command recorded.`,
      "ok"
    );
  } catch (err) {
    setStatusLine(els.searchStatus, `Search request failed: ${err}`, "error");
  }
}

function renderResults(results) {
  els.searchResults.innerHTML = "";
  if (!results.length) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="hint">No results returned by Anserini.</span>`;
    els.searchResults.appendChild(li);
    return;
  }
  for (const r of results) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="meta">
        <span class="rank">#${r.rank}</span>
        <span class="docid">${escapeHtml(r.docid)}</span>
        <span class="score">score ${fmtNumber(r.score)}</span>
        ${r.url ? `<span>· <a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">source</a></span>` : ""}
      </div>
      <div class="title">${escapeHtml(r.title || "(no title)")}</div>
      <div class="snippet">${escapeHtml(r.snippet || "")}</div>
    `;
    els.searchResults.appendChild(li);
  }
}

// ----------------------------------------------------- evaluation

async function runEvaluation(force) {
  const url = force ? "/api/verify" : "/api/evaluate";
  setStatusLine(els.evalStatus, `${force ? "Verifying" : "Running"} BM25 evaluation…`);
  els.btnEvaluate.disabled = true;
  els.btnVerify.disabled = true;
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    const data = await resp.json();
    state.lastEval = data;
    renderEvaluation(data);
    await loadArtifacts();
  } catch (err) {
    setStatusLine(els.evalStatus, `Evaluation request failed: ${err}`, "error");
  } finally {
    els.btnEvaluate.disabled = false;
    els.btnVerify.disabled = false;
  }
}

function renderEvaluation(data) {
  if (!data) return;
  if (data.evaluate && data.evaluate.command) {
    pushCommand("TrecEval", data.evaluate.command);
  }
  if (!data.ok) {
    setStatusLine(els.evalStatus, `Evaluation failed at stage=${data.stage}: ${data.error || "see logs"}`, "error");
    return;
  }
  setStatusLine(
    els.evalStatus,
    data.cached
      ? "Returned cached run + eval output. Click Verify/Rerun for a fresh run."
      : "Fresh batch retrieval + evaluation completed.",
    "ok"
  );

  const tbody = els.metricTableBody;
  tbody.innerHTML = "";
  const comparison = data.comparison || {};
  for (const [metric, info] of Object.entries(comparison)) {
    const tr = document.createElement("tr");
    const delta = info.delta;
    const deltaClass = delta == null ? "" : (delta < 0 ? "delta-negative" : "delta-positive");
    tr.innerHTML = `
      <td class="metric">${escapeHtml(metric)}</td>
      <td>${fmtNumber(info.expected)}</td>
      <td>${fmtNumber(info.observed)}</td>
      <td class="${deltaClass}">${delta == null ? "—" : (delta >= 0 ? "+" : "") + fmtNumber(delta)}</td>
      <td class="verdict-cell"><span class="badge verdict-${info.verdict}">${escapeHtml(info.verdict)}</span></td>
    `;
    tbody.appendChild(tr);
  }

  els.evalElapsed.textContent = data.elapsed_seconds != null
    ? `elapsed: ${data.elapsed_seconds.toFixed(2)}s`
    : "";
  els.evalCached.textContent = data.cached ? "cache: hit" : "cache: miss (fresh run)";
  els.evalVerdict.className = `badge verdict-${data.overall_verdict || "unknown"}`;
  els.evalVerdict.textContent = `overall: ${data.overall_verdict || "unknown"}`;

  // Pull a short preview from the most recent evaluation log.
  if (data.evaluate && data.evaluate.stdout_excerpt) {
    els.logPreviewBody.textContent = data.evaluate.stdout_excerpt;
  }
}

// ----------------------------------------------------- boot

async function boot() {
  renderCommands();
  renderArtifacts();
  els.btnRefreshStatus.addEventListener("click", () => loadStatus());
  els.searchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    runSearch();
  });
  els.btnEvaluate.addEventListener("click", () => runEvaluation(false));
  els.btnVerify.addEventListener("click", () => runEvaluation(true));
  els.btnToggleDrawer.addEventListener("click", () => {
    const open = !els.logPreview.open;
    // (the drawer card is the body; just toggle the log preview by class for now)
    els.logPreview.open = !els.logPreview.open;
    els.btnToggleDrawer.textContent = els.logPreview.open ? "Hide" : "Show";
  });

  // Probe health to learn the port.
  try {
    const resp = await fetch("/health");
    const data = await resp.json();
    if (data.port) els.footerPort.textContent = data.port;
  } catch (err) {
    console.warn("health probe failed", err);
  }

  await loadStatus();

  // Pull a few sample queries from /api/setup/reproduction or fall back to defaults.
  try {
    const resp = await fetch("/api/setup/reproduction");
    const data = await resp.json();
    // TopicsRegistry output isn't directly exposed; ship defaults that match the BEIR test split.
    state.sampleQueries = [
      "Preventing the Common Cold with Probiotics?",
      "Heart Disease Starts in Childhood",
      "Aspartame and the Brain",
      "Dairy and Prostate Cancer Risk",
      "Alkylphenol Endocrine Disruptors and Allergies",
      "Is Milk Good for Our Bones?",
      "Caloric Restriction vs. Plant-Based Diets",
      "Treating Asthma With Plants vs. Supplements?",
      "Food Dyes and ADHD",
      "Diabetes as a Disease of Fat Toxicity",
    ];
    renderSampleQueries(state.sampleQueries);
  } catch (err) {
    console.warn("reproduction probe failed", err);
  }
}

document.addEventListener("DOMContentLoaded", boot);
