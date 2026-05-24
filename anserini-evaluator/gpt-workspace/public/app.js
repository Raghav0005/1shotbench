const state = {
  catalog: [],
  selected: null
};

const els = {
  health: document.getElementById('health'),
  error: document.getElementById('error'),
  catalogSummary: document.getElementById('catalogSummary'),
  catalogSource: document.getElementById('catalogSource'),
  filter: document.getElementById('filter'),
  list: document.getElementById('indexList'),
  refresh: document.getElementById('refreshCatalog'),
  selection: document.getElementById('selection'),
  form: document.getElementById('evalForm'),
  metric: document.getElementById('metric'),
  runButton: document.getElementById('runButton'),
  runStatus: document.getElementById('runStatus'),
  result: document.getElementById('result'),
  score: document.getElementById('score'),
  metaIndex: document.getElementById('metaIndex'),
  metaTopics: document.getElementById('metaTopics'),
  metaQrels: document.getElementById('metaQrels'),
  metaMetric: document.getElementById('metaMetric'),
  metaElapsed: document.getElementById('metaElapsed'),
  metaRunFile: document.getElementById('metaRunFile'),
  metaEvalFile: document.getElementById('metaEvalFile'),
  evalPreview: document.getElementById('evalPreview'),
  runPreview: document.getElementById('runPreview')
};

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = '';
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return 'unknown size';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  return data;
}

async function checkHealth() {
  try {
    const health = await fetchJson('/api/health');
    els.health.className = 'status-pill ok';
    els.health.textContent = `Ready: Java + Anserini fatjar\n${health.jar}`;
  } catch (err) {
    els.health.className = 'status-pill bad';
    els.health.textContent = 'Setup problem';
    showError(err.message);
  }
}

function renderCatalog() {
  const query = els.filter.value.trim().toLowerCase();
  const filtered = state.catalog.filter((idx) => {
    const haystack = `${idx.name} ${idx.description || ''} ${idx.type || ''}`.toLowerCase();
    return haystack.includes(query);
  });
  els.list.innerHTML = '';
  for (const idx of filtered.slice(0, 80)) {
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `index-card ${state.selected?.name === idx.name ? 'selected' : ''}`;
    button.dataset.indexName = idx.name;
    button.innerHTML = `
      <h3>${escapeHtml(idx.name)}</h3>
      <p>${escapeHtml(idx.description || 'No description available')}</p>
      <p>${escapeHtml(idx.type || 'unknown')} · ${formatBytes(idx.size)}${idx.documents ? ` · ${idx.documents.toLocaleString()} docs` : ''}</p>
      <div class="badges">
        <span class="badge ${idx.evaluable ? 'ok' : 'warn'}">${idx.evaluable ? 'Ready for evaluation' : 'Catalog-only'}</span>
        ${idx.evaluation ? `<span class="badge">topics: ${escapeHtml(idx.evaluation.topics)}</span>` : ''}
      </div>
    `;
    button.addEventListener('click', () => {
      state.selected = idx;
      renderCatalog();
      renderSelection();
    });
    li.appendChild(button);
    els.list.appendChild(li);
  }
  if (filtered.length === 0) {
    const li = document.createElement('li');
    li.textContent = 'No registry indexes match the filter.';
    els.list.appendChild(li);
  }
}

function renderSelection() {
  const idx = state.selected;
  els.result.hidden = true;
  if (!idx) {
    els.selection.innerHTML = '<p>No index selected.</p>';
    els.runButton.disabled = true;
    return;
  }

  if (!idx.evaluable) {
    els.selection.innerHTML = `
      <h3>${escapeHtml(idx.name)}</h3>
      <p><strong>Catalog-only.</strong> ${escapeHtml(idx.catalogOnlyReason || 'No automatic pairing is available.')}</p>
      <p>This keeps the registry visible without launching unknown or large downloads.</p>
    `;
    els.metric.innerHTML = '';
    els.runButton.disabled = true;
    return;
  }

  const evaluation = idx.evaluation;
  els.selection.innerHTML = `
    <h3>${escapeHtml(idx.name)} is ready for evaluation</h3>
    <p><strong>Topics:</strong> ${escapeHtml(evaluation.topics)}</p>
    <p><strong>Qrels/eval source:</strong> ${escapeHtml(evaluation.qrelsLabel)}</p>
    <p><strong>Retrieval:</strong> ${escapeHtml(evaluation.searchModel)}</p>
    <p>${escapeHtml(evaluation.reason)}</p>
  `;
  els.metric.innerHTML = evaluation.metrics.map((m) => `<option value="${escapeHtml(m.value)}">${escapeHtml(m.label)} (${escapeHtml(m.value)})</option>`).join('');
  els.metric.value = evaluation.defaultMetric;
  els.runButton.disabled = false;
}

async function loadCatalog(force = false) {
  clearError();
  els.catalogSummary.textContent = 'Loading PrebuiltIndexRegistry and TopicsRegistry…';
  els.refresh.disabled = true;
  try {
    const catalog = await fetchJson(`/api/catalog${force ? '?refresh=1' : ''}`);
    state.catalog = catalog.indexes;
    state.selected = state.catalog.find((idx) => idx.name === 'cacm') || state.catalog.find((idx) => idx.evaluable) || state.catalog[0];
    els.catalogSummary.textContent = `${state.catalog.length} Lucene inverted indexes from registry · ${catalog.topicsCount} topic sets discovered`;
    els.catalogSource.textContent = `${catalog.source}. Jar: ${catalog.jar}`;
    renderCatalog();
    renderSelection();
  } catch (err) {
    showError(`Catalog discovery failed. ${err.message}`);
    els.catalogSummary.textContent = 'Catalog discovery failed';
  } finally {
    els.refresh.disabled = false;
  }
}

async function runEvaluation(event) {
  event.preventDefault();
  if (!state.selected?.evaluable) return;
  clearError();
  els.result.hidden = true;
  els.runButton.disabled = true;
  els.runStatus.className = 'run-status running';
  els.runStatus.textContent = 'Running Anserini SearchCollection and TrecEval…';
  try {
    const result = await fetchJson('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: state.selected.name, metric: els.metric.value })
    });
    els.runStatus.className = 'run-status done';
    els.runStatus.textContent = 'Evaluation completed with real Anserini artifacts.';
    els.score.textContent = result.score.toFixed(4);
    els.metaIndex.textContent = result.index;
    els.metaTopics.textContent = result.topics;
    els.metaQrels.textContent = result.qrelsLabel;
    els.metaMetric.textContent = `${result.selectedMetricLabel} (${result.measure})`;
    els.metaElapsed.textContent = `${(result.elapsedMs / 1000).toFixed(2)}s`;
    els.metaRunFile.textContent = result.artifacts.runFile;
    els.metaEvalFile.textContent = result.artifacts.evalFile;
    els.evalPreview.textContent = result.evaluationOutput;
    els.runPreview.textContent = result.runPreview;
    els.result.hidden = false;
  } catch (err) {
    els.runStatus.className = 'run-status failed';
    els.runStatus.textContent = `Evaluation failed: ${err.message}`;
  } finally {
    els.runButton.disabled = !state.selected?.evaluable;
  }
}

els.filter.addEventListener('input', renderCatalog);
els.refresh.addEventListener('click', () => loadCatalog(true));
els.form.addEventListener('submit', runEvaluation);

checkHealth();
loadCatalog();
