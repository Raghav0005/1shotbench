// Frontend for the Anserini Prebuilt Index Evaluator.

const els = {
  health: document.getElementById("health"),
  filter: document.getElementById("filter"),
  list: document.getElementById("catalog-list"),
  stats: document.getElementById("catalog-stats"),
  detail: document.getElementById("detail"),
};

let CATALOG = null;
let METRICS = null;
let DEFAULT_INDEX = "cacm";
let selectedName = null;

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
  if (!res.ok) {
    const msg = (body && body.error) || `${res.status} ${res.statusText}`;
    const err = new Error(msg);
    err.body = body;
    err.status = res.status;
    throw err;
  }
  return body;
}

async function bootstrap() {
  // Health check
  try {
    const h = await fetchJson("/api/health");
    if (h.catalogError) {
      els.health.className = "health bad";
      els.health.textContent = `Setup issue: ${h.catalogError}`;
    } else if (h.catalogLoaded) {
      els.health.className = "health ok";
      els.health.textContent =
        `Java OK · fatjar: ${h.fatjar} · ${h.catalogSize} prebuilt inverted indexes ` +
        `· ${h.evaluableCount} evaluable · ${h.topicsCount} topic symbols`;
    } else {
      els.health.textContent = "Loading registries...";
    }
  } catch (e) {
    els.health.className = "health bad";
    els.health.textContent = `Health check failed: ${e.message}`;
  }

  // Catalog
  try {
    const data = await fetchJson("/api/catalog");
    CATALOG = data.indexes;
    METRICS = data.metrics;
    DEFAULT_INDEX = data.defaultIndex;
    renderCatalog();
    selectIndex(DEFAULT_INDEX);
  } catch (e) {
    els.list.innerHTML = "";
    els.detail.innerHTML = `<div class="error">${escapeHtml(e.message)}</div>`;
  }

  els.filter.addEventListener("input", renderCatalog);
}

function renderCatalog() {
  if (!CATALOG) return;
  const q = els.filter.value.trim().toLowerCase();
  const filtered = q
    ? CATALOG.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          (e.description || "").toLowerCase().includes(q)
      )
    : CATALOG;
  const evaluable = filtered.filter((e) => e.evaluable).length;
  els.stats.textContent =
    `${filtered.length} of ${CATALOG.length} indexes shown · ${evaluable} evaluable`;

  els.list.innerHTML = "";
  for (const entry of filtered) {
    const li = document.createElement("li");
    li.dataset.name = entry.name;
    li.setAttribute("role", "option");
    li.setAttribute("data-evaluable", entry.evaluable ? "true" : "false");
    if (!entry.evaluable) li.setAttribute("aria-disabled", "true");
    if (entry.name === selectedName) li.classList.add("selected");

    const row = document.createElement("div");
    row.className = "row";

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.name;
    row.appendChild(name);

    if (entry.name === DEFAULT_INDEX) {
      const b = document.createElement("span");
      b.className = "badge default";
      b.textContent = "default";
      row.appendChild(b);
    }
    const b2 = document.createElement("span");
    if (entry.evaluable) {
      b2.className = "badge evaluable";
      b2.textContent = "Evaluable";
    } else {
      b2.className = "badge catalog-only";
      b2.textContent = "Catalog only";
    }
    row.appendChild(b2);

    li.appendChild(row);

    if (entry.description) {
      const d = document.createElement("div");
      d.className = "desc";
      d.textContent = entry.description;
      li.appendChild(d);
    }
    if (entry.pairing) {
      const d = document.createElement("div");
      d.className = "desc";
      d.textContent = `topics: ${entry.pairing.topics} · qrels: ${entry.pairing.qrels}`;
      li.appendChild(d);
    }

    li.addEventListener("click", () => selectIndex(entry.name));
    els.list.appendChild(li);
  }
}

function selectIndex(name) {
  selectedName = name;
  for (const li of els.list.querySelectorAll("li")) {
    li.classList.toggle("selected", li.dataset.name === name);
  }
  renderDetail();
}

function renderDetail() {
  const entry = CATALOG.find((e) => e.name === selectedName);
  if (!entry) {
    els.detail.innerHTML = `<p class="muted">Select an index from the catalog to begin.</p>`;
    return;
  }

  const evaluable = entry.evaluable && entry.pairing;
  const metricOptions = METRICS.map(
    (m) => `<option value="${m.id}">${escapeHtml(m.label)} (<code>${escapeHtml(m.trecEvalArg)}</code>)</option>`
  ).join("");

  els.detail.innerHTML = `
    <div class="field-row">
      <div class="field"><label>Index</label><div class="value" data-testid="selected-index">${escapeHtml(entry.name)}</div></div>
      <div class="field"><label>Type</label><div class="value">${escapeHtml(entry.type || "inverted")}</div></div>
      ${entry.documents ? `<div class="field"><label>Documents</label><div class="value">${entry.documents.toLocaleString()}</div></div>` : ""}
    </div>
    ${entry.description ? `<div class="muted">${escapeHtml(entry.description)}</div>` : ""}
    ${evaluable
      ? `
        <div class="field-row">
          <div class="field"><label>Topics symbol</label><div class="value" data-testid="paired-topics">${escapeHtml(entry.pairing.topics)}</div></div>
          <div class="field"><label>Qrels / eval source</label><div class="value" data-testid="paired-qrels">${escapeHtml(entry.pairing.qrels)}</div></div>
        </div>
        <div class="field-row">
          <div class="field" style="min-width:14rem">
            <label for="metric-select">Metric</label>
            <select id="metric-select" data-testid="metric-select">${metricOptions}</select>
          </div>
          <div class="field" style="justify-content:flex-end">
            <label>&nbsp;</label>
            <button id="run-btn" class="primary" data-testid="run-btn">Run Evaluation</button>
          </div>
        </div>
        <div id="run-status" aria-live="polite"></div>
        <div id="run-result"></div>
      `
      : `
        <div class="error" data-testid="catalog-only-msg">
          This entry is catalog-only: no compatible topics/qrels pairing was
          automatically derived from Anserini's registries. It is shown for
          discovery but cannot be evaluated here.
        </div>
      `}
  `;

  if (evaluable) {
    document.getElementById("run-btn").addEventListener("click", runEvaluation);
    // Default metric to nDCG@10
    const sel = document.getElementById("metric-select");
    sel.value = "ndcg_cut_10";
  }
}

async function runEvaluation() {
  const entry = CATALOG.find((e) => e.name === selectedName);
  if (!entry) return;
  const metricId = document.getElementById("metric-select").value;
  const btn = document.getElementById("run-btn");
  const statusEl = document.getElementById("run-status");
  const resultEl = document.getElementById("run-result");

  btn.disabled = true;
  resultEl.innerHTML = "";
  statusEl.innerHTML = `<span class="status-pending" data-testid="run-status"><span class="spinner"></span>Running Anserini SearchCollection then TrecEval...</span>`;

  try {
    const r = await fetchJson("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: entry.name, metricId }),
    });
    statusEl.innerHTML = `<span class="status-pending" data-testid="run-status">Completed in ${(r.elapsedMs/1000).toFixed(2)}s</span>`;
    resultEl.innerHTML = `
      <div class="result" data-testid="run-result">
        <div class="score-row">
          <span class="score" data-testid="score">${r.score.toFixed(4)}</span>
          <span class="metric-label" data-testid="metric-label">${escapeHtml(r.metric.label)} (<code>${escapeHtml(r.metric.trecEvalArg)}</code>)</span>
        </div>
        <dl class="kv">
          <dt>Index</dt><dd data-testid="meta-index">${escapeHtml(r.index)}</dd>
          <dt>Topics</dt><dd data-testid="meta-topics">${escapeHtml(r.topics)}</dd>
          <dt>Qrels</dt><dd data-testid="meta-qrels">${escapeHtml(r.qrels)}</dd>
          <dt>Metric</dt><dd data-testid="meta-metric">${escapeHtml(r.metric.label)} → <code>${escapeHtml(r.metric.trecEvalArg)}</code></dd>
          <dt>Status</dt><dd>ok</dd>
          <dt>Elapsed</dt><dd>${(r.elapsedMs/1000).toFixed(2)} s</dd>
          <dt>Run file</dt><dd data-testid="meta-runpath">${escapeHtml(r.runPath)}</dd>
          <dt>Eval file</dt><dd data-testid="meta-evalpath">${escapeHtml(r.evalPath)}</dd>
          <dt>Anserini fatjar</dt><dd>${escapeHtml(r.fatjar)}</dd>
        </dl>
        <h3 style="margin:0.5rem 0 0.25rem;font-size:0.85rem;color:var(--muted)">trec_eval output preview</h3>
        <div class="preview" data-testid="eval-preview">${escapeHtml(r.evalPreview)}</div>
      </div>
    `;
  } catch (e) {
    statusEl.innerHTML = "";
    resultEl.innerHTML = `<div class="error" data-testid="run-error">${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

bootstrap();
