const $ = (id) => document.getElementById(id);
let lastStatus = null;

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function cls(value) {
  if (value === true || value === 'ready' || value === 'ok' || value === 'pass') return 'ok';
  if (value === 'degraded' || value === 'close' || value === 'running' || value === 'initializing') return 'warn';
  return 'bad';
}

async function fetchStatus() {
  const res = await fetch('/api/status');
  lastStatus = await res.json();
  render(lastStatus);
  return lastStatus;
}

function renderReadiness(s) {
  const rows = [
    ['App status', s.app.status],
    ['Active dataset', s.dataset.id],
    ['Java', s.java.available ? s.java.version : 'missing'],
    ['Anserini setup', s.anserini.verified ? `verified ${s.anserini.version || ''}` : 'not verified'],
    ['Fatjar', s.anserini.jar || 'not located'],
    ['NFCorpus index', s.nfcorpus.ready ? 'ready' : 'initializing'],
    ['Reproduction discovery', s.reproduction.discovered ? 'beir.core / flat / nfcorpus discovered' : 'pending'],
    ['Live search', s.search.available ? 'available' : 'pending'],
    ['Evaluation', s.evaluation.available ? 'available' : (s.evaluation.running ? 'running' : 'pending')]
  ];
  if (s.app.error) rows.push(['Startup error', s.app.error.split('\n')[0]]);
  $('readiness').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd class="${cls(v === 'missing' || v === 'not verified' ? false : v)}">${esc(v)}</dd>`).join('');
  $('dataset').textContent = s.dataset.id;
  $('dataset-note').textContent = s.dataset.note;
  $('search-status').textContent = s.search.available ? 'available' : s.app.status;
  $('search-status').className = `status ${cls(s.search.available ? 'ok' : s.app.status)}`;
}

function renderSamples(s) {
  $('samples').innerHTML = s.samples.map(q => `<button type="button" data-query="${esc(q)}">${esc(q)}</button>`).join('');
  $('samples').querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => {
    $('query').value = btn.dataset.query;
    runSearch(btn.dataset.query);
  }));
}

function renderEvaluation(s) {
  const e = s.evaluation;
  $('eval-summary').textContent = e.available
    ? `${e.cached ? 'Cached startup verification' : 'Fresh rerun'} at ${e.lastRunAt}; elapsed ${e.elapsedMs} ms.`
    : (e.running ? 'Evaluation is running SearchCollection and TrecEval…' : 'Evaluation pending.');
  $('eval-error').textContent = e.error || '';

  const observedRows = Object.entries(e.comparisons || {}).map(([metric, c]) => ({ metric, observed: c.observed, expected: c.expected, delta: c.delta, status: c.status }));
  if (!observedRows.length) {
    for (const [metric, observed] of Object.entries(e.metrics || {})) observedRows.push({ metric, observed, expected: '', delta: '', status: 'observed' });
  }
  $('metrics').innerHTML = observedRows.map(r => `<tr>
    <td>${esc(r.metric)}</td><td>${typeof r.observed === 'number' ? r.observed.toFixed(4) : esc(r.observed)}</td>
    <td>${typeof r.expected === 'number' ? r.expected.toFixed(4) : esc(r.expected)}</td>
    <td>${typeof r.delta === 'number' ? r.delta.toFixed(6) : esc(r.delta)}</td>
    <td class="${cls(r.status)}">${esc(r.status)}</td>
  </tr>`).join('');

  const artifacts = [
    ['Run file', e.runFile],
    ['Evaluation output', e.evalFile],
    ['Reproduction show YAML', s.reproduction.showPath],
    ['Reproduction dry-run log', s.reproduction.dryRunPath]
  ].filter(([, p]) => p);
  $('artifacts').innerHTML = artifacts.map(([label, p]) => `<div class="artifact"><strong>${esc(label)}</strong><br><code>${esc(p)}</code></div>`).join('');
}

function renderCommands(s) {
  const dry = s.reproduction.dryRunSnippet ? `<div class="command"><h3>NFCorpus reproduction dry-run excerpt</h3><pre>${esc(s.reproduction.dryRunSnippet)}</pre></div>` : '';
  const cmds = s.commands.slice().reverse().map(c => `<article class="command">
    <h3>${esc(c.label)} <span class="${cls(c.status)}">${esc(c.status)}</span></h3>
    <div class="command-meta"><span>id ${esc(c.id)}</span><span>exit ${esc(c.exitCode)}</span><span>${esc(c.durationMs)} ms</span></div>
    <pre>${esc(c.command)}</pre>
    <details><summary>stdout preview and artifact path</summary><p><code>${esc(c.stdoutPath)}</code></p><pre>${esc(c.stdoutPreview)}</pre></details>
    <details><summary>stderr preview and artifact path</summary><p><code>${esc(c.stderrPath)}</code></p><pre>${esc(c.stderrPreview)}</pre></details>
  </article>`).join('');
  $('commands').innerHTML = dry + cmds;
}

function render(s) {
  renderReadiness(s);
  renderSamples(s);
  renderEvaluation(s);
  renderCommands(s);
  $('rerun').disabled = s.evaluation.running || !s.anserini.verified;
}

async function runSearch(query) {
  $('search-error').textContent = '';
  $('results').innerHTML = '<li class="muted">Running Anserini CLI search…</li>';
  try {
    const res = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, hits: 10 }) });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || 'search failed');
    $('results').innerHTML = payload.results.map(r => `<li class="result">
      <div class="result-head"><span class="rank">#${r.rank}</span><span class="docid">${esc(r.docid)}</span><span class="score">score ${Number(r.score).toFixed(4)}</span></div>
      <h3>${esc(r.title || '(untitled)')}</h3>
      <p>${esc(r.snippet)}</p>
    </li>`).join('');
    await fetchStatus();
  } catch (err) {
    $('search-error').textContent = err.message;
    $('results').innerHTML = '';
  }
}

$('search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  runSearch($('query').value.trim());
});

$('rerun').addEventListener('click', async () => {
  $('eval-error').textContent = '';
  $('rerun').disabled = true;
  try {
    const res = await fetch('/api/evaluation/rerun', { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || 'evaluation failed');
    await fetchStatus();
  } catch (err) {
    $('eval-error').textContent = err.message;
  } finally {
    $('rerun').disabled = false;
  }
});

fetchStatus();
setInterval(fetchStatus, 2500);
