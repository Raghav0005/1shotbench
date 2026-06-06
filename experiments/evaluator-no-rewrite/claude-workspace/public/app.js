/* global document, window, fetch */

const state = {
  catalog: null,
  filter: '',
  evaluableOnly: false,
  selectedIndex: null,
  selectedPairing: null,
  selectedMetric: null,
};

const $ = (sel) => document.querySelector(sel);

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'dataset') for (const [dk, dv] of Object.entries(v)) node.dataset[dk] = dv;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k === 'html') node.innerHTML = v;
    else if (v === false || v == null) continue;
    else if (v === true) node.setAttribute(k, '');
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

function fmtBytes(n) {
  if (n == null) return '–';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 ? 0 : 1)} ${units[i]}`;
}

// ---------- Init ----------

async function init() {
  await renderHealth();
  await loadCatalog();
  $('#catalog-filter').addEventListener('input', (e) => {
    state.filter = e.target.value.toLowerCase();
    renderCatalogList();
  });
  $('#filter-evaluable').addEventListener('change', (e) => {
    state.evaluableOnly = e.target.checked;
    renderCatalogList();
  });
  $('#pairing-select').addEventListener('change', (e) => {
    const idx = Number(e.target.value);
    state.selectedPairing = state.selectedIndex.pairings[idx];
    renderPairing();
  });
  $('#metric-select').addEventListener('change', (e) => {
    state.selectedMetric = state.selectedPairing.metrics.find((m) => m.label === e.target.value);
  });
  $('#run-button').addEventListener('click', runEvaluation);
}

async function renderHealth() {
  const health = $('#health');
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    if (data.ok) {
      health.className = 'health ok';
      health.textContent = `✓ Java ${data.java.version}, Anserini jar: ${data.anseriniJar.jar.split('/').pop()}`;
    } else {
      health.className = 'health bad';
      const msg = data.java?.message || data.anseriniJar?.message || 'environment unavailable';
      health.textContent = `✗ ${msg}`;
    }
  } catch (err) {
    health.className = 'health bad';
    health.textContent = `✗ Health check failed: ${err.message}`;
  }
}

async function loadCatalog() {
  $('#catalog-list').innerHTML = '<li class="empty">Loading prebuilt-index registry (may take ~1 min on first load)…</li>';
  $('.catalog-stats').textContent = 'Loading…';
  try {
    const res = await fetch('/api/catalog');
    if (!res.ok) throw new Error(await res.text());
    state.catalog = await res.json();
  } catch (err) {
    $('#catalog-list').innerHTML = `<li class="empty">Failed to load catalog: ${err.message}</li>`;
    return;
  }
  const cat = state.catalog;
  const evaluable = cat.indexes.filter((i) => i.evaluable).length;
  $('.catalog-stats').textContent =
    `${cat.indexes.length} inverted indexes · ${evaluable} evaluable · ${cat.configCount} reproduce configs`;
  renderCatalogList();
  // Auto-select CACM if present.
  const cacm = cat.indexes.find((i) => i.name === 'cacm');
  if (cacm) selectIndex(cacm);
}

function renderCatalogList() {
  const ul = $('#catalog-list');
  ul.innerHTML = '';
  if (!state.catalog) return;
  const filter = state.filter;
  const list = state.catalog.indexes.filter((idx) => {
    if (state.evaluableOnly && !idx.evaluable) return false;
    if (!filter) return true;
    return idx.name.toLowerCase().includes(filter)
      || (idx.description || '').toLowerCase().includes(filter);
  });
  if (list.length === 0) {
    ul.appendChild(el('li', { class: 'empty' }, 'No indexes match this filter.'));
    return;
  }
  for (const idx of list) {
    const classes = ['catalog-item'];
    if (state.selectedIndex && idx.name === state.selectedIndex.name) classes.push('selected');
    if (!idx.evaluable) classes.push('catalog-only');
    const badge = idx.evaluable
      ? el('span', { class: 'badge evaluable', dataset: { testid: 'badge-evaluable' } }, 'evaluable')
      : el('span', { class: 'badge catalog-only', dataset: { testid: 'badge-catalog-only' } }, 'catalog-only');
    const item = el(
      'li',
      {
        class: classes.join(' '),
        dataset: { testid: 'catalog-item', indexName: idx.name, evaluable: String(idx.evaluable) },
        onclick: () => selectIndex(idx),
      },
      [
        el('div', { class: 'catalog-name' }, idx.name),
        el('div', { class: 'catalog-meta' }, [
          badge,
          el('span', {}, idx.type),
          idx.documents ? el('span', {}, `${idx.documents.toLocaleString()} docs`) : null,
          idx.size ? el('span', {}, fmtBytes(idx.size)) : null,
        ]),
      ]
    );
    ul.appendChild(item);
  }
}

function selectIndex(idx) {
  state.selectedIndex = idx;
  state.selectedPairing = idx.pairings[0] || null;
  state.selectedMetric = state.selectedPairing?.metrics?.[0] || null;
  renderCatalogList();
  renderDetail();
  renderPairing();
}

function renderDetail() {
  const detail = $('#detail');
  const idx = state.selectedIndex;
  if (!idx) {
    detail.innerHTML = '<p class="muted">Select an index from the catalog to view details.</p>';
    $('#pairing-section').hidden = true;
    return;
  }
  detail.innerHTML = '';
  const dl = el('dl', { dataset: { testid: 'index-detail' } });
  const rows = [
    ['Name', idx.name],
    ['Type', idx.type],
    ['Description', idx.description || '–'],
    ['Documents', idx.documents ? idx.documents.toLocaleString() : '–'],
    ['Unique terms', idx.uniqueTerms ? idx.uniqueTerms.toLocaleString() : '–'],
    ['Size', fmtBytes(idx.size)],
    ['Status', idx.evaluable ? 'Evaluable (paired with topics/qrels)' : 'Catalog-only (no automatic pairing)'],
  ];
  for (const [k, v] of rows) {
    dl.appendChild(el('dt', {}, k));
    dl.appendChild(el('dd', {}, v));
  }
  detail.appendChild(dl);

  if (idx.evaluable) {
    $('#pairing-section').hidden = false;
  } else {
    $('#pairing-section').hidden = true;
  }
}

function renderPairing() {
  const idx = state.selectedIndex;
  if (!idx || !idx.evaluable) return;

  // Pairing select.
  const psel = $('#pairing-select');
  psel.innerHTML = '';
  idx.pairings.forEach((p, i) => {
    const label = `${p.topics} → qrels:${p.evalKey} (${p.conditionName})`;
    psel.appendChild(el('option', { value: String(i) }, label));
  });
  const selIdx = idx.pairings.indexOf(state.selectedPairing);
  psel.value = String(selIdx >= 0 ? selIdx : 0);
  state.selectedPairing = idx.pairings[Number(psel.value)];

  // Pairing meta.
  const meta = $('.pairing-meta');
  meta.innerHTML = '';
  const p = state.selectedPairing;
  const expected = Object.entries(p.expectedScores || {})
    .map(([k, v]) => `${k}=${v}`).join(', ') || '–';
  const rows = [
    ['Topics symbol', p.topics],
    ['qrels / eval key', p.evalKey],
    ['Reproduce config', `${p.configName} :: ${p.conditionName}`],
    ['Expected reference scores', expected],
  ];
  for (const [k, v] of rows) {
    meta.appendChild(el('dt', {}, k));
    meta.appendChild(el('dd', { dataset: { testid: `pairing-${k.toLowerCase().replace(/[^a-z]+/g, '-')}` } }, v));
  }

  // Metric select.
  const msel = $('#metric-select');
  msel.innerHTML = '';
  // Prefer to show modern ranking metrics first when present.
  const preferred = ['nDCG@10', 'Recall@1000', 'R@1K'];
  const sorted = [...p.metrics].sort((a, b) => {
    const ai = preferred.indexOf(a.label);
    const bi = preferred.indexOf(b.label);
    const aw = ai === -1 ? 99 : ai;
    const bw = bi === -1 ? 99 : bi;
    return aw - bw;
  });
  for (const m of sorted) {
    msel.appendChild(el('option', { value: m.label }, `${m.label}  [${m.args.join(' ')}]`));
  }
  state.selectedMetric = sorted[0];
  msel.value = state.selectedMetric.label;
}

// ---------- Run ----------

async function runEvaluation() {
  const button = $('#run-button');
  const status = $('#run-status');
  if (!state.selectedIndex || !state.selectedPairing || !state.selectedMetric) {
    status.textContent = 'Select an index, pairing, and metric first.';
    status.className = 'run-status error';
    return;
  }
  button.disabled = true;
  status.textContent = `Running retrieval and evaluation for ${state.selectedIndex.name}…`;
  status.className = 'run-status running';
  $('#results').innerHTML = '<p class="muted">Evaluation in progress…</p>';
  const body = {
    indexName: state.selectedIndex.name,
    topics: state.selectedPairing.topics,
    evalKey: state.selectedPairing.evalKey,
    metricLabel: state.selectedMetric.label,
    metricArgs: state.selectedMetric.args,
  };
  try {
    const res = await fetch('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    status.textContent = `✓ Completed in ${(data.totalMs / 1000).toFixed(2)}s`;
    status.className = 'run-status ok';
    renderResult(data);
  } catch (err) {
    status.textContent = `✗ ${err.message}`;
    status.className = 'run-status error';
    $('#results').innerHTML = `<p class="muted">Run failed. See the status above.</p>`;
  } finally {
    button.disabled = false;
  }
}

function renderResult(data) {
  const results = $('#results');
  results.innerHTML = '';
  const score = data.score != null ? data.score.toFixed(4) : '–';

  const scoreBlock = el('div', { class: 'score-display' }, [
    el('span', { class: 'score-value', dataset: { testid: 'score-value' } }, score),
    el('span', { class: 'score-label', dataset: { testid: 'score-label' } }, data.metric.label),
  ]);
  results.appendChild(scoreBlock);

  const dl = el('dl', { dataset: { testid: 'result-meta' } });
  const rows = [
    ['Index', data.indexName],
    ['Topics', data.topics],
    ['qrels / eval key', data.evalKey],
    ['Metric', `${data.metric.label} (${data.metric.args.join(' ')})`],
    ['Status', 'ok'],
    ['Retrieval elapsed', `${(data.retrievalMs / 1000).toFixed(2)} s`],
    ['Evaluation elapsed', `${(data.evaluationMs / 1000).toFixed(2)} s`],
    ['Total elapsed', `${(data.totalMs / 1000).toFixed(2)} s`],
    ['Run file', data.runFile],
    ['Evaluation file', data.evalFile],
  ];
  if (data.expectedScores && Object.keys(data.expectedScores).length > 0) {
    rows.push(['Reference scores', Object.entries(data.expectedScores).map(([k, v]) => `${k}=${v}`).join(', ')]);
  }
  for (const [k, v] of rows) {
    dl.appendChild(el('dt', {}, k));
    dl.appendChild(el('dd', { dataset: { testid: `result-${k.toLowerCase().replace(/[^a-z]+/g, '-')}` } }, v));
  }
  results.appendChild(dl);

  results.appendChild(el('h3', {}, 'Evaluator output'));
  results.appendChild(el('pre', { dataset: { testid: 'eval-output' } }, data.evalOutput || ''));

  results.appendChild(el('h3', {}, 'Run file preview (last lines)'));
  results.appendChild(el('pre', { dataset: { testid: 'run-preview' } }, data.runPreview || ''));

  results.appendChild(el('h3', {}, 'Commands'));
  const cmds = el('pre', { dataset: { testid: 'commands' } },
    `# retrieval\n${data.retrievalCommand}\n\n# evaluation\n${data.evaluationCommand}`);
  results.appendChild(cmds);

  results.appendChild(el('p', {},
    [
      'Artifacts: ',
      el('a', { href: `/api/artifacts/${data.runArtifact}`, target: '_blank' }, 'run file'),
      ' · ',
      el('a', { href: `/api/artifacts/${data.evalArtifact}`, target: '_blank' }, 'evaluation output'),
    ]
  ));
}

window.addEventListener('DOMContentLoaded', init);
