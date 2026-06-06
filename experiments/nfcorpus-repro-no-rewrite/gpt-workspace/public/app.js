const $ = (id) => document.getElementById(id);
let latestStatus = null;

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

async function jsonFetch(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function statusClass(s) {
  if (/ok|ready|pass|available/i.test(String(s))) return 'status-ok';
  if (/error|fail/i.test(String(s))) return 'status-error';
  return 'status-running';
}

function renderStatus(data) {
  latestStatus = data;
  $('app-status').textContent = data.app.status;
  $('app-status').className = `badge ${statusClass(data.app.status)}`;
  $('dataset').textContent = `${data.dataset.name} (${data.dataset.index})`;
  $('anserini-status').textContent = `${data.anserini.status}${data.anserini.version ? ' v' + data.anserini.version : ''}`;
  $('nfcorpus-status').textContent = `${data.nfcorpus.status}; ${data.nfcorpus.indexStatus}`;
  $('search-status').textContent = data.nfcorpus.searchAvailable ? 'available' : 'not ready';
  $('eval-status').textContent = data.evaluation.status;
  $('java-line').textContent = data.anserini.java ? `Java/fatjar: ${data.anserini.java}; jar ${data.anserini.jar}` : 'Java/fatjar checks are running.';
  renderEvaluation(data.evaluation);
  renderReproduction(data.reproduction);
  renderCommands(data.commands || []);
}

function renderEvaluation(ev) {
  $('run-file').textContent = ev.runFile || 'pending';
  $('eval-file').textContent = ev.evalFile || 'pending';
  $('elapsed').textContent = ev.elapsedMs ? `${ev.elapsedMs} ms (${ev.fresh ? 'fresh run' : 'cached'})` : ev.status;
  $('eval-preview').textContent = ev.outputPreview || ev.error || '';
  if (!ev.comparisons || !ev.comparisons.length) {
    $('metrics').innerHTML = `<div class="metric"><span>Status</span><b>${esc(ev.status)}</b><p>${esc(ev.error || 'Waiting for numeric observed metric from Anserini TrecEval.')}</p></div>`;
    return;
  }
  $('metrics').innerHTML = ev.comparisons.map((m) => `
    <div class="metric ${esc(m.status)}">
      <span>${esc(m.metric)} observed</span>
      <b>${esc(m.observed)}</b>
      <p>Expected: <strong>${m.expected == null ? 'unavailable' : esc(m.expected)}</strong></p>
      <p>Delta: <strong>${m.delta == null ? 'n/a' : esc(m.delta)}</strong></p>
      <p>Status: <strong>${esc(m.status)}</strong></p>
    </div>`).join('');
}

function renderReproduction(rep) {
  $('expected-source').textContent = Object.keys(rep.expected || {}).length ? `ReproduceFromPrebuiltIndexes --config beir.core --show (${JSON.stringify(rep.expected)})` : 'not exposed yet';
  $('template').textContent = rep.commandTemplate || 'pending';
  $('show-preview').textContent = rep.showPreview || rep.error || '';
  $('dry-preview').textContent = rep.dryRunPreview || '';
}

function renderCommands(commands) {
  $('commands').innerHTML = commands.map((c) => `
    <details class="cmd">
      <summary>${esc(c.name)} — ${esc(c.status)} — ${esc(c.elapsedMs ?? '')} ms</summary>
      <div class="inner">
        <p><span>Exact command</span><code>${esc(c.command)}</code></p>
        <p><span>Working directory</span><code>${esc(c.cwd)}</code></p>
        <p><span>Artifacts</span>${(c.artifacts || []).map((a) => `<code>${esc(a)}</code>`).join('<br>') || 'none'}</p>
        <pre class="preview">${esc(c.stdoutPreview || c.stderrPreview || '')}</pre>
      </div>
    </details>`).join('');
}

async function refresh() {
  try { renderStatus(await jsonFetch('/api/status')); } catch (e) { console.error(e); }
}

async function runSearch(q) {
  $('results').innerHTML = '<p class="muted">Running real Anserini CLI search…</p>';
  $('search-command').textContent = '';
  const data = await jsonFetch(`/api/search?q=${encodeURIComponent(q)}&hits=5`);
  $('search-command').textContent = data.command;
  $('results').innerHTML = data.results.map((r) => `
    <article class="result">
      <h3>#${r.rank} ${esc(r.title || r.docid)}</h3>
      <div class="meta">docid=${esc(r.docid)} · rank=${r.rank} · score=${esc(r.score)}</div>
      <p>${esc(r.snippet)}</p>
      ${r.url ? `<p><a href="${esc(r.url)}" target="_blank" rel="noreferrer">${esc(r.url)}</a></p>` : ''}
    </article>`).join('') || '<p>No results.</p>';
  await refresh();
}

$('search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = $('query').value.trim();
  if (!q) return;
  try { await runSearch(q); } catch (err) { $('results').innerHTML = `<p class="status-error">${esc(err.message)}</p>`; }
});

document.querySelectorAll('[data-query]').forEach((btn) => btn.addEventListener('click', async () => {
  $('query').value = btn.dataset.query;
  try { await runSearch(btn.dataset.query); } catch (err) { $('results').innerHTML = `<p class="status-error">${esc(err.message)}</p>`; }
}));

$('rerun-eval').addEventListener('click', async () => {
  $('rerun-eval').disabled = true;
  $('rerun-eval').textContent = 'Running…';
  try { await jsonFetch('/api/evaluate', { method: 'POST' }); await refresh(); }
  catch (err) { $('eval-preview').textContent = err.message; }
  finally { $('rerun-eval').disabled = false; $('rerun-eval').textContent = 'Verify/Rerun'; }
});

refresh();
setInterval(refresh, 2500);
