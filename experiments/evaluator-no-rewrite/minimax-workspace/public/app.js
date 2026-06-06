// Front-end controller. Pulls the catalog from the server, lets the
// user pick an index / topics / metric, and shows the real run
// metadata that comes back from the Anserini fatjar.

const $ = (id) => document.getElementById(id);

const state = {
  catalog: null,
  selectedIndex: null,
  selectedDataset: null,
  topicsFilter: '',
  showCatalogOnly: false,
};

async function fetchCatalog() {
  const res = await fetch('/api/catalog');
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      body.error || body.detail || `Failed to load catalog (${res.status})`
    );
  }
  return res.json();
}

async function fetchDataset(index) {
  const res = await fetch(`/api/dataset/${encodeURIComponent(index)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Failed to load dataset (${res.status})`);
  }
  return res.json();
}

function setStatus(kind, message) {
  const pill = $('statusPill');
  pill.className = 'status-pill';
  if (kind === 'ok') pill.classList.add('ok');
  if (kind === 'error') pill.classList.add('error');
  pill.textContent = message;
}

function setStatusDetail(detail) {
  $('statusDetail').textContent = detail || '';
}

function escapeHTML(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));
}

function renderCatalog() {
  const list = $('catalogList');
  const filter = state.topicsFilter.trim().toLowerCase();
  const items = state.catalog.indexes.filter((idx) => {
    if (state.showCatalogOnly && idx.evaluable) return false;
    if (!filter) return true;
    return (
      idx.name.toLowerCase().includes(filter) ||
      (idx.description || '').toLowerCase().includes(filter)
    );
  });
  $('catalogCount').textContent = items.length;
  list.innerHTML = '';
  for (const idx of items) {
    const li = document.createElement('li');
    li.dataset.index = idx.name;
    if (state.selectedIndex === idx.name) li.classList.add('active');
    if (!idx.evaluable) li.classList.add('disabled');
    li.innerHTML = `
      <span class="name">${escapeHTML(idx.name)}</span>
      <span class="desc">${escapeHTML((idx.description || '').slice(0, 140))}${
        (idx.description || '').length > 140 ? '…' : ''
      }</span>
      <span class="tag ${idx.evaluable ? 'eval' : 'catalog-only'}">${
      idx.evaluable ? 'evaluable' : 'catalog only'
    }</span>
    `;
    if (idx.evaluable) {
      li.addEventListener('click', () => selectIndex(idx.name));
    }
    list.appendChild(li);
  }
}

async function selectIndex(name) {
  state.selectedIndex = name;
  $('emptyState').hidden = true;
  $('errorView').hidden = true;
  $('result').hidden = true;
  $('datasetView').hidden = false;
  renderCatalog();

  let dataset;
  try {
    dataset = await fetchDataset(name);
  } catch (err) {
    showError(err.message);
    return;
  }
  state.selectedDataset = dataset;

  $('datasetTitle').textContent = `${dataset.id} (${dataset.index})`;
  $('evaluableBadge').textContent = 'Evaluable';
  $('evaluableBadge').className = 'badge badge-eval';
  $('sourceBadge').textContent = 'Topics + qrels from Anserini';
  $('datasetDescription').textContent = dataset.description || '';
  $('datasetIndex').textContent = dataset.index;
  $('datasetTopics').textContent = dataset.topics.join(', ');
  $('datasetQrels').textContent = dataset.qrels;

  const idxMeta = state.catalog.indexes.find((i) => i.name === name);
  $('datasetCatalogDescription').textContent = idxMeta
    ? idxMeta.description || '(no description in registry)'
    : '(not in prebuilt-index registry)';

  const topicsSelect = $('topicsSelect');
  topicsSelect.innerHTML = '';
  for (const t of dataset.topics) {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t;
    if (t === dataset.defaultTopic) opt.selected = true;
    topicsSelect.appendChild(opt);
  }

  const metricSelect = $('metricSelect');
  metricSelect.innerHTML = '';
  for (const m of dataset.metrics) {
    const opt = document.createElement('option');
    opt.value = m.label;
    opt.textContent = m.label;
    if (m.label === 'nDCG@10') opt.selected = true;
    metricSelect.appendChild(opt);
  }
  updateMetricHelp();
  metricSelect.onchange = updateMetricHelp;
}

function updateMetricHelp() {
  const sel = $('metricSelect');
  const opt = sel.options[sel.selectedIndex];
  $('metricHelp').textContent = opt ? `→ trec_eval -m ${opt.dataset.flag || ''}` : '';
  if (state.selectedDataset) {
    const m = state.selectedDataset.metrics.find((x) => x.label === sel.value);
    if (m) $('metricHelp').textContent = `trec_eval -m ${m.flag} (${m.help})`;
  }
}

function showError(message, extra) {
  $('errorView').hidden = false;
  $('errorMessage').textContent = message + (extra ? `\n\n${extra}` : '');
  $('result').hidden = true;
}

async function onSubmitRun(ev) {
  ev.preventDefault();
  if (!state.selectedDataset) return;
  const topics = $('topicsSelect').value;
  const metric = $('metricSelect').value;
  const button = $('runButton');
  button.disabled = true;
  $('formStatus').textContent = 'Running Anserini retrieval + evaluation…';
  $('errorView').hidden = true;
  $('result').hidden = true;
  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        index: state.selectedDataset.index,
        topics,
        metric,
      }),
    });
    const body = await res.json();
    if (!res.ok || !body.ok) {
      const extra = [body.stdout, body.stderr].filter(Boolean).join('\n');
      showError(body.error || 'Run failed', extra);
      $('formStatus').textContent = '';
      return;
    }
    renderResult(body);
    $('formStatus').textContent = `Done in ${body.durationMs}ms`;
  } catch (err) {
    showError(err.message);
    $('formStatus').textContent = '';
  } finally {
    button.disabled = false;
  }
}

function renderResult(r) {
  $('result').hidden = false;
  $('scoreValue').textContent =
    r.score == null ? '—' : Number(r.score).toFixed(4);
  $('scoreMeasure').textContent = r.scoreMeasure
    ? `(${r.scoreMeasure}, all queries)`
    : '';
  $('metaStatus').textContent = 'completed';
  $('metaIndex').textContent = r.index;
  $('metaTopics').textContent = r.topics;
  $('metaQrels').textContent = r.qrels;
  $('metaMetric').textContent = r.metric;
  $('metaRetrievalMs').textContent = `${r.metrics.retrievalMs} ms`;
  $('metaEvaluationMs').textContent = `${r.metrics.evaluationMs} ms`;
  $('metaRunFile').textContent = `${r.runFile} (${r.runFileBytes} bytes)`;
  $('metaEvalFile').textContent = r.evalFile;
  $('metaSearchCmd').textContent = r.commands.retrieval.join(' ');
  $('metaEvalCmd').textContent = r.commands.evaluation.join(' ');
  $('runPreview').textContent = r.runPreview || '(empty run)';
  $('evalOutput').textContent = r.evalOutput;
}

async function init() {
  $('catalogFilter').addEventListener('input', (e) => {
    state.topicsFilter = e.target.value;
    renderCatalog();
  });
  $('showCatalogOnly').addEventListener('change', (e) => {
    state.showCatalogOnly = e.target.checked;
    renderCatalog();
  });
  $('runForm').addEventListener('submit', onSubmitRun);

  setStatus('warn', 'Loading Anserini catalog…');
  try {
    const catalog = await fetchCatalog();
    state.catalog = catalog;
    const evalCount = catalog.indexes.filter((i) => i.evaluable).length;
    setStatus('ok', 'Catalog ready');
    setStatusDetail(
      `${catalog.indexes.length} prebuilt inverted indexes (${evalCount} evaluable, ` +
        `${catalog.topics.length} topic sets, ${catalog.qrels.length} qrels)`
    );
    renderCatalog();
    if (catalog.defaults && catalog.defaults.index) {
      const defaultIdx = catalog.indexes.find(
        (i) => i.name === catalog.defaults.index && i.evaluable
      );
      if (defaultIdx) {
        await selectIndex(defaultIdx.name);
      }
    }
  } catch (err) {
    setStatus('error', 'Catalog load failed');
    setStatusDetail(err.message);
  }
}

window.addEventListener('DOMContentLoaded', init);
