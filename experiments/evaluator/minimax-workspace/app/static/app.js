/* Anserini Prebuilt Index Evaluator — UI logic. */

const state = {
  health: null,
  catalog: [],
  evaluableCount: 0,
  selectedIndex: null,
  metrics: [],
  topicKey: null,
  topicSelections: [], // [{topic_key, eval_key, metrics}]
  defaultIndex: 'cacm',
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function setStatus(text, isError = false) {
  const el = $('#meta-status');
  el.textContent = text;
  el.classList.toggle('error', isError);
}

function fmtNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  if (typeof n !== 'number') return String(n);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  return n.toFixed(4);
}

function fmtBytes(b) {
  if (!b) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = b;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 ? 0 : 1)} ${units[i]}`;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

async function api(path, init) {
  const res = await fetch(path, init);
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try { detail = JSON.parse(text).error || text; } catch (_) { /* not JSON */ }
    throw new Error(`API ${path} failed (${res.status}): ${detail}`);
  }
  return res.json();
}

async function loadHealth() {
  const h = await api('/api/health');
  state.health = h;
  $('#meta-version').textContent = `jar: ${h.anserini_version}`;
  $('#meta-indexes').textContent = `indexes: ${h.indexes_loaded}`;
  $('#meta-topics').textContent = `topics: ${h.topics_loaded}`;
  $('#meta-pairings').textContent = `pairings: ${h.pairings_loaded}`;
  if (h.error) {
    setStatus(`degraded: ${h.error}`, true);
  } else if (h.indexes_loaded === 0) {
    setStatus('no indexes', true);
  } else {
    setStatus('ready');
  }
}

async function loadCatalog() {
  const data = await api('/api/catalog');
  state.catalog = data.indexes;
  state.evaluableCount = state.catalog.filter((e) => e.evaluable).length;
  $('#catalog-summary').textContent =
    `${state.catalog.length} prebuilt Lucene inverted indexes ` +
    `(${state.evaluableCount} evaluable, ` +
    `${state.catalog.length - state.evaluableCount} catalog-only) — ` +
    `derived from the live Anserini prebuilt-index registry.`;
  renderCatalog();
  // Default to CACM as required by the PRD.
  const def = state.catalog.find((e) => e.name === state.defaultIndex);
  if (def) {
    selectIndex(def);
  } else {
    const firstEval = state.catalog.find((e) => e.evaluable);
    if (firstEval) selectIndex(firstEval);
  }
}

function renderCatalog() {
  const filter = ($('#catalog-filter').value || '').toLowerCase().trim();
  const list = $('#catalog-list');
  list.innerHTML = '';
  const filtered = state.catalog.filter((e) => {
    if (!filter) return true;
    return (
      e.name.toLowerCase().includes(filter) ||
      (e.type || '').toLowerCase().includes(filter) ||
      (e.description || '').toLowerCase().includes(filter) ||
      (e.corpus_index || '').toLowerCase().includes(filter)
    );
  });
  // Sort evaluable first, then by name.
  filtered.sort((a, b) => {
    if (a.evaluable !== b.evaluable) return a.evaluable ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const entry of filtered) {
    const li = document.createElement('li');
    li.dataset.name = entry.name;
    if (state.selectedIndex && state.selectedIndex.name === entry.name) {
      li.classList.add('selected');
    }
    if (!entry.evaluable) {
      li.classList.add('disabled');
      li.title = 'No evaluable topics/qrels pairing was discovered for this index in the bundled Anserini reproduction configs.';
    }
    const docs = entry.documents != null
      ? `${entry.documents.toLocaleString()} docs`
      : '';
    const terms = entry.total_terms != null
      ? `${entry.total_terms.toLocaleString()} terms`
      : '';
    li.innerHTML = `
      <div>
        <div class="idx-name">${escapeHtml(entry.name)}</div>
        <div class="idx-meta">
          <span class="badge type">${escapeHtml(entry.type)}</span>
          <span>${escapeHtml(docs)}</span>
          <span>${escapeHtml(terms)}</span>
          <span>${escapeHtml(fmtBytes(entry.size_bytes))}</span>
        </div>
        <div class="idx-desc">${escapeHtml(entry.description)}</div>
      </div>
      <div>
        <span class="badge ${entry.evaluable ? 'evaluable' : 'catalog-only'}">
          ${entry.evaluable ? 'Evaluable' : 'Catalog only'}
        </span>
      </div>
    `;
    li.addEventListener('click', () => {
      if (!entry.evaluable) return;
      selectIndex(entry);
    });
    list.appendChild(li);
  }
  if (filtered.length === 0) {
    const li = document.createElement('li');
    li.classList.add('disabled');
    li.innerHTML = '<div><div class="idx-name">No matches</div></div><div></div>';
    list.appendChild(li);
  }
}

async function selectIndex(entry) {
  state.selectedIndex = entry;
  state.topicSelections = entry.pairings || [];
  if (!entry.evaluable) {
    $('#eval-section').hidden = true;
    renderCatalog();
    return;
  }
  $('#eval-section').hidden = false;
  const desc = entry.description
    ? ` — <em>${escapeHtml(entry.description)}</em>` : '';
  $('#eval-selected').innerHTML =
    `<strong>${escapeHtml(entry.name)}</strong>${desc} &middot; ` +
    `<span>${entry.pairings.length} topic/qrels pairing(s) found</span>`;
  // Build the topic dropdown.
  const sel = $('#topic-select');
  sel.innerHTML = '';
  for (const p of entry.pairings) {
    const opt = document.createElement('option');
    opt.value = p.topic_key;
    opt.textContent = `${p.topic_key}  (qrels: ${p.eval_key})`;
    sel.appendChild(opt);
  }
  // Auto-prefer a "preferred" metric order that satisfies the PRD.
  await onTopicChange();
  renderCatalog();
}

async function onTopicChange() {
  const topicKey = $('#topic-select').value;
  state.topicKey = topicKey;
  const pairing = state.topicSelections.find((p) => p.topic_key === topicKey);
  if (!pairing) return;
  $('#qrels-input').value = pairing.eval_key;
  // Load the metric options from the server, which knows about the
  // YAML-declared metrics and the standard modern metrics.
  try {
    const data = await api(
      `/api/metrics?index=${encodeURIComponent(state.selectedIndex.name)}` +
      `&topic_key=${encodeURIComponent(topicKey)}`
    );
    state.metrics = data.metrics;
    const sel = $('#metric-select');
    sel.innerHTML = '';
    for (const m of data.metrics) {
      const opt = document.createElement('option');
      opt.value = m.label;
      const expected = m.expected != null
        ? ` (expected ${m.expected})` : '';
      opt.textContent = `${m.label}${expected}`;
      sel.appendChild(opt);
    }
    // Pick a sensible default: prefer nDCG@10, then Recall@1000, then
    // the first option in the list. This matches the PRD's required
    // metric-selector emphasis.
    const preferred = ['nDCG@10', 'Recall@1000'];
    let chosen = null;
    for (const p of preferred) {
      chosen = data.metrics.find((m) => m.label === p);
      if (chosen) break;
    }
    if (!chosen && data.metrics.length > 0) chosen = data.metrics[0];
    if (chosen) sel.value = chosen.label;
  } catch (err) {
    setStatus(`metric lookup failed: ${err.message}`, true);
  }
}

async function runEvaluation(event) {
  event.preventDefault();
  if (!state.selectedIndex) return;
  const topicKey = $('#topic-select').value;
  const metric = $('#metric-select').value;
  const btn = $('#run-btn');
  const status = $('#run-status');
  const result = $('#eval-result');
  btn.disabled = true;
  status.hidden = false;
  status.classList.remove('error');
  status.innerHTML = '<span class="spinner"></span> Running retrieval + evaluation&hellip;';
  result.hidden = true;
  result.innerHTML = '';
  try {
    const data = await api('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        index: state.selectedIndex.name,
        topic_key: topicKey,
        metric,
      }),
    });
    renderResult(data);
  } catch (err) {
    status.classList.add('error');
    status.textContent = err.message;
    result.hidden = false;
    result.innerHTML = `<div class="error-card"><strong>Evaluation failed</strong><pre>${escapeHtml(err.message)}</pre></div>`;
  } finally {
    btn.disabled = false;
  }
}

function renderResult(data) {
  const status = $('#run-status');
  status.classList.remove('error');
  status.innerHTML =
    `<span>Done in ${data.elapsed_seconds}s</span>`;
  const result = $('#eval-result');
  result.hidden = false;
  const scoreLabel = data.metric;
  const score = data.score;
  const expectedStr = data.expected != null
    ? `expected ${data.expected}` : 'expected n/a';
  const evalPath = data.eval_file
    ? `<a href="/api/artifact?path=${encodeURIComponent(data.eval_file)}" target="_blank">${escapeHtml(data.eval_file)}</a>`
    : '—';
  const runPath = data.run_file
    ? `<a href="/api/artifact?path=${encodeURIComponent(data.run_file)}" target="_blank">${escapeHtml(data.run_file)}</a>`
    : '—';
  const metricRows = Object.entries(data.metrics || {})
    .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v.subset)} = ${fmtNumber(v.value)}</dd>`)
    .join('');
  const searchCmd = (data.command && data.command.search || []).join(' ');
  const evalCmd = (data.command && data.command.eval || []).join(' ');
  result.innerHTML = `
    <div class="score-card">
      <div>
        <div class="score-label">${escapeHtml(scoreLabel)}</div>
        <div class="score-value" data-testid="score-value">${fmtNumber(score)}</div>
      </div>
      <div class="score-meta">
        <div>${escapeHtml(expectedStr)}</div>
        <div>elapsed ${data.elapsed_seconds}s</div>
      </div>
    </div>
    <dl class="run-meta">
      <dt>Index</dt><dd data-testid="meta-index">${escapeHtml(data.index)}</dd>
      <dt>Topics</dt><dd data-testid="meta-topics">${escapeHtml(data.topic_key)}</dd>
      <dt>Qrels</dt><dd data-testid="meta-qrels">${escapeHtml(data.eval_key)}</dd>
      <dt>Metric</dt><dd data-testid="meta-metric">${escapeHtml(data.metric)} (args: ${escapeHtml(data.metric_args)})</dd>
      <dt>Status</dt><dd data-testid="meta-status">ok</dd>
      <dt>Run file</dt><dd data-testid="meta-run-file">${runPath} (${data.run_file_size.toLocaleString()} bytes)</dd>
      <dt>Eval file</dt><dd data-testid="meta-eval-file">${evalPath}</dd>
      <dt>Search cmd</dt><dd>${escapeHtml(searchCmd)}</dd>
      <dt>Eval cmd</dt><dd>${escapeHtml(evalCmd)}</dd>
    </dl>
    ${metricRows ? `<dl class="run-meta"><dt>All metrics</dt>${metricRows}</dl>` : ''}
    <div class="artifact-preview">
      <h4>Run file preview (${escapeHtml(data.run_file)})</h4>
      <pre>${escapeHtml(data.run_file_preview || '(empty)')}</pre>
    </div>
    <div class="artifact-preview">
      <h4>Eval output preview (${escapeHtml(data.eval_file)})</h4>
      <pre>${escapeHtml(data.eval_output_preview || '(empty)')}</pre>
    </div>
  `;
}

function init() {
  $('#catalog-filter').addEventListener('input', renderCatalog);
  $('#topic-select').addEventListener('change', onTopicChange);
  $('#eval-form').addEventListener('submit', runEvaluation);
  Promise.all([loadHealth(), loadCatalog()])
    .catch((err) => {
      setStatus(`failed to load: ${err.message}`, true);
    });
}

document.addEventListener('DOMContentLoaded', init);
