const state = {
  catalog: null,
  selected: null,
  filter: ''
};

const $ = (id) => document.getElementById(id);

function formatBytes(value) {
  if (!Number.isFinite(value)) return 'size unknown';
  const units = ['B', 'KB', 'MB', 'GB'];
  let n = value;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function showError(message) {
  const error = $('error');
  error.hidden = false;
  error.textContent = message;
}

function clearError() {
  $('error').hidden = true;
  $('error').textContent = '';
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function renderRuntime() {
  const catalog = state.catalog;
  $('runtime').innerHTML = `
    <strong>${catalog.indexes.length}</strong> inverted indexes from registry<br />
    Fatjar: <code>${catalog.fatjar}</code><br />
    Topics discovered: ${catalog.topicsCount}
  `;
  $('topicsPreview').textContent = catalog.topicsPreview.join(', ');
}

function renderCatalog() {
  const catalogEl = $('catalog');
  const q = state.filter.trim().toLowerCase();
  const indexes = state.catalog.indexes.filter((item) => {
    const haystack = `${item.name} ${item.description} ${item.filename}`.toLowerCase();
    return !q || haystack.includes(q);
  });
  $('catalogStatus').textContent = `${indexes.length} of ${state.catalog.indexes.length} registry indexes shown. Evaluable indexes are enabled; catalog-only indexes remain visible.`;
  catalogEl.innerHTML = '';
  for (const item of indexes) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `index-card ${item.evaluable ? 'evaluable' : 'catalog-only'} ${state.selected?.name === item.name ? 'selected' : ''}`;
    button.dataset.testid = 'catalog-index';
    button.dataset.indexName = item.name;
    button.dataset.evaluable = String(item.evaluable);
    button.disabled = false;
    button.innerHTML = `
      <div class="index-top">
        <span class="index-name">${item.name}</span>
        <span class="badge ${item.evaluable ? 'ready' : ''}">${item.status}</span>
      </div>
      <p class="description">${item.description || 'No description available.'}</p>
      <div class="meta">
        <span>type: ${item.type || 'unknown'}</span>
        <span>docs: ${item.documents ?? 'unknown'}</span>
        <span>${formatBytes(item.size)}</span>
      </div>
    `;
    button.addEventListener('click', () => {
      if (item.evaluable) {
        state.selected = item;
        renderCatalog();
        renderSelection();
      } else {
        state.selected = item;
        renderCatalog();
        renderSelection();
      }
    });
    catalogEl.appendChild(button);
  }
}

function renderSelection() {
  const item = state.selected;
  const metric = $('metric');
  metric.innerHTML = '';
  $('result').hidden = true;
  clearError();

  if (!item) {
    $('selection').textContent = 'Select an evaluable index.';
    $('run').disabled = true;
    return;
  }

  if (!item.evaluable) {
    $('selection').innerHTML = `
      <strong>${item.name}</strong> is visible from the Anserini prebuilt-index registry, but is catalog-only in this app.<br />
      ${item.catalogOnlyReason}
    `;
    $('run').disabled = true;
    const option = document.createElement('option');
    option.textContent = 'No metrics available';
    metric.appendChild(option);
    return;
  }

  $('selection').innerHTML = `
    <strong>${item.name}</strong> is ready for evaluation.<br />
    Topics: <code data-testid="selected-topics">${item.pairing.topics}</code><br />
    Qrels/evaluation source: <code data-testid="selected-qrels">${item.pairing.qrels}</code><br />
    Retrieval: ${item.pairing.retrieval.model} (${item.pairing.retrieval.args.join(' ')})
  `;
  for (const m of item.pairing.metrics) {
    const option = document.createElement('option');
    option.value = m.id;
    option.textContent = `${m.label} (${m.id})`;
    option.dataset.label = m.label;
    metric.appendChild(option);
  }
  $('run').disabled = false;
}

async function loadCatalog(force = false) {
  clearError();
  $('catalogStatus').textContent = 'Loading registry catalog…';
  const catalog = await fetchJson(`/api/catalog${force ? '?refresh=1' : ''}`);
  state.catalog = catalog;
  state.selected = catalog.indexes.find((item) => item.name === catalog.defaultIndex && item.evaluable)
    || catalog.indexes.find((item) => item.evaluable)
    || catalog.indexes[0]
    || null;
  renderRuntime();
  renderCatalog();
  renderSelection();
}

function renderResult(result) {
  $('result').hidden = false;
  $('score').textContent = String(result.score);
  $('metaIndex').textContent = result.selectedIndex;
  $('metaTopics').textContent = result.topics;
  $('metaQrels').textContent = `${result.qrels} — ${result.qrelsLabel}`;
  $('metaMetric').textContent = `${result.metric.label} (${result.metric.id})`;
  $('metaStatus').textContent = result.status;
  $('metaElapsed').textContent = `${(result.elapsedMs / 1000).toFixed(2)}s`;
  $('metaRunPath').textContent = result.runPath;
  $('metaEvalPath').textContent = result.evalPath;
  $('evalPreview').textContent = result.evalPreview.join('\n');
  $('commands').textContent = `${result.commands.search}\n\n${result.commands.evaluate}`;
}

async function runEvaluation() {
  if (!state.selected?.evaluable) return;
  clearError();
  $('result').hidden = true;
  $('run').disabled = true;
  $('runStatus').textContent = 'Running SearchCollection retrieval and TrecEval evaluation…';
  try {
    const result = await fetchJson('/api/evaluate', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ indexName: state.selected.name, metricId: $('metric').value })
    });
    $('runStatus').textContent = 'Evaluation completed.';
    renderResult(result);
  } catch (error) {
    $('runStatus').textContent = 'Evaluation failed.';
    showError(error.message);
  } finally {
    $('run').disabled = !state.selected?.evaluable;
  }
}

$('filter').addEventListener('input', (event) => {
  state.filter = event.target.value;
  renderCatalog();
});
$('refresh').addEventListener('click', () => loadCatalog(true).catch((error) => showError(error.message)));
$('run').addEventListener('click', runEvaluation);

loadCatalog().catch((error) => {
  $('catalogStatus').textContent = 'Catalog failed to load.';
  showError(error.message);
});
