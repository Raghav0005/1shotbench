const state = {
  catalog: null,
  selected: null,
  filter: ''
};

const $ = (id) => document.getElementById(id);
const els = {
  environment: $('environment'),
  errorPanel: $('errorPanel'),
  catalogSummary: $('catalogSummary'),
  catalogRows: $('catalogRows'),
  filterInput: $('filterInput'),
  refreshCatalog: $('refreshCatalog'),
  selectedIndex: $('selectedIndex'),
  metricSelect: $('metricSelect'),
  runButton: $('runButton'),
  status: $('status'),
  resultPanel: $('resultPanel'),
  scoreValue: $('scoreValue'),
  scoreMetric: $('scoreMetric'),
  metaIndex: $('metaIndex'),
  metaTopics: $('metaTopics'),
  metaQrels: $('metaQrels'),
  metaMetric: $('metaMetric'),
  metaStatus: $('metaStatus'),
  metaElapsed: $('metaElapsed'),
  metaRunFile: $('metaRunFile'),
  metaEvalFile: $('metaEvalFile'),
  evalPreview: $('evalPreview')
};

function showError(message) {
  els.errorPanel.textContent = message || '';
  els.errorPanel.classList.toggle('hidden', !message);
}

function formatInt(value) {
  return typeof value === 'number' ? new Intl.NumberFormat().format(value) : '—';
}

function formatBytes(value) {
  if (typeof value !== 'number') return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let n = value;
  let u = 0;
  while (n >= 1024 && u < units.length - 1) { n /= 1024; u += 1; }
  return `${n.toFixed(n >= 10 || u === 0 ? 0 : 1)} ${units[u]}`;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = data.stderr || data.details || data.stdout || '';
    throw new Error(`${data.error || response.statusText}${details ? `\n${details}` : ''}`);
  }
  return data;
}

async function loadEnvironment() {
  try {
    const env = await fetchJson('/api/environment');
    if (!env.ok) throw new Error('Anserini fatjar not found.');
    const javaLine = (env.java || '').split(/\r?\n/)[0];
    els.environment.innerHTML = `<strong>Ready</strong><br>Fatjar: <code>${env.jar}</code><br>${javaLine}`;
  } catch (err) {
    els.environment.innerHTML = `<strong>Environment issue</strong><br>${err.message}<br>Run <code>npm run setup:anserini</code>.`;
  }
}

async function loadCatalog(force = false) {
  els.catalogSummary.textContent = 'Loading registry from Anserini CLI…';
  els.status.textContent = 'Loading catalog.';
  els.refreshCatalog.disabled = true;
  showError('');
  try {
    state.catalog = await fetchJson(`/api/catalog${force ? '?refresh=1' : ''}`);
    const ready = state.catalog.indexes.filter(i => i.evaluable).length;
    els.catalogSummary.textContent = `${state.catalog.indexes.length} registry-derived inverted indexes; ${state.catalog.topics.length} topic sets discovered; ${ready} ready for browser evaluation. Generated ${new Date(state.catalog.generatedAt).toLocaleString()}.`;
    state.selected = state.catalog.indexes.find(i => i.name === 'cacm' && i.evaluable) || state.catalog.indexes.find(i => i.evaluable) || state.catalog.indexes[0] || null;
    renderCatalog();
    renderSelection();
  } catch (err) {
    showError(err.message);
    els.catalogSummary.textContent = 'Could not load Anserini registry.';
    els.status.textContent = 'Catalog failed to load.';
  } finally {
    els.refreshCatalog.disabled = false;
  }
}

function renderCatalog() {
  if (!state.catalog) return;
  const filter = state.filter.trim().toLowerCase();
  const rows = state.catalog.indexes.filter(index => {
    if (!filter) return true;
    return [index.name, index.type, index.description, index.status].some(v => String(v || '').toLowerCase().includes(filter));
  });

  els.catalogRows.innerHTML = '';
  for (const index of rows) {
    const tr = document.createElement('tr');
    tr.dataset.indexName = index.name;
    tr.className = state.selected && state.selected.name === index.name ? 'selected' : '';
    tr.innerHTML = `
      <td class="name-cell">${index.name}</td>
      <td>${index.type || '—'}</td>
      <td><span class="badge ${index.evaluable ? 'ready' : 'catalog'}">${index.evaluable ? 'Ready' : 'Catalog-only'}</span></td>
      <td title="Size: ${formatBytes(index.size)}">${formatInt(index.documents)}</td>
      <td class="desc-cell">${index.description || 'No description available.'}</td>`;
    tr.addEventListener('click', () => {
      state.selected = index;
      renderCatalog();
      renderSelection();
    });
    els.catalogRows.appendChild(tr);
  }
}

function renderSelection() {
  const index = state.selected;
  els.metricSelect.innerHTML = '';
  els.resultPanel.classList.add('hidden');
  if (!index) {
    els.selectedIndex.textContent = 'No index selected.';
    els.runButton.disabled = true;
    els.status.textContent = 'No index selected.';
    return;
  }

  if (!index.evaluable || !index.pairing) {
    els.selectedIndex.innerHTML = `
      <h3>${index.name}</h3>
      <p><span class="badge catalog">Catalog-only</span></p>
      <p>${index.description || ''}</p>
      <p><strong>Why disabled:</strong> ${index.catalogOnlyReason}</p>`;
    els.runButton.disabled = true;
    els.status.textContent = 'Selected index is visible in the registry but not automatically evaluable.';
    return;
  }

  els.selectedIndex.innerHTML = `
    <h3>${index.name}</h3>
    <p><span class="badge ready">Ready for evaluation</span></p>
    <p>${index.description || ''}</p>
    <p><strong>Topics:</strong> <code>${index.pairing.topics}</code></p>
    <p><strong>Qrels/eval source:</strong> <code>${index.pairing.qrels}</code> — ${index.pairing.qrelsSource}</p>
    <p><strong>Inferred from:</strong> ${index.readyReason}</p>`;
  for (const metric of index.pairing.metrics) {
    const option = document.createElement('option');
    option.value = metric.id;
    option.textContent = `${metric.label} (${metric.id})`;
    els.metricSelect.appendChild(option);
  }
  els.runButton.disabled = false;
  els.status.textContent = 'Ready to run retrieval and TrecEval.';
}

async function runEvaluation() {
  if (!state.selected || !state.selected.evaluable) return;
  const metricId = els.metricSelect.value;
  els.runButton.disabled = true;
  els.status.textContent = 'Running Anserini SearchCollection and TrecEval…';
  els.resultPanel.classList.add('hidden');
  showError('');
  try {
    const result = await fetchJson('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ indexName: state.selected.name, metricId })
    });
    els.scoreValue.textContent = Number(result.score).toFixed(4);
    els.scoreMetric.textContent = `${result.metric.label} / ${result.metric.id}`;
    els.metaIndex.textContent = result.selectedIndex;
    els.metaTopics.textContent = result.topics;
    els.metaQrels.textContent = `${result.qrels} (${result.qrelsSource})`;
    els.metaMetric.textContent = `${result.metric.label} (${result.metric.id})`;
    els.metaStatus.textContent = result.status;
    els.metaElapsed.textContent = `${(result.elapsedMs / 1000).toFixed(2)} s`;
    els.metaRunFile.textContent = result.runFile;
    els.metaEvalFile.textContent = result.evaluationOutputFile;
    els.evalPreview.textContent = result.evaluationPreview || result.scoreLine || '';
    els.resultPanel.classList.remove('hidden');
    els.status.textContent = 'Evaluation completed.';
  } catch (err) {
    showError(err.message);
    els.status.textContent = 'Evaluation failed.';
  } finally {
    els.runButton.disabled = !state.selected || !state.selected.evaluable;
  }
}

els.filterInput.addEventListener('input', event => {
  state.filter = event.target.value;
  renderCatalog();
});
els.refreshCatalog.addEventListener('click', () => loadCatalog(true));
els.runButton.addEventListener('click', runEvaluation);

loadEnvironment();
loadCatalog();
