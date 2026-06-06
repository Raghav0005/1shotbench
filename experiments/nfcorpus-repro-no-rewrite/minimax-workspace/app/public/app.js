// Frontend controller. Fetches /api/status periodically, drives the search
// and evaluation panels, and renders command/artifact lists. The page never
// hard-codes search results or metrics; everything is read from the backend.

const state = {
  evalLoaded: false,
  lastEval: null,
};

const STATUS_TILE_KEYS = ['app', 'anserini', 'nfcorpus', 'search', 'evaluation'];

function $(id) { return document.getElementById(id); }

function fmtNumber(n, digits = 4) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toFixed(digits);
}

function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(1)} ${u[i]}`;
}

function setStatus(key, label, stateName) {
  const el = $(`status-${key}`);
  if (!el) return;
  el.textContent = label;
  const tile = el.closest('.status-tile');
  if (tile) tile.setAttribute('data-state', stateName);
}

function renderStatus(snapshot) {
  const flags = snapshot.phase === 'ready' || snapshot.phase === 'live' ? 'ok' : 'starting';
  setStatus('app', flags, flags);

  const anserini = snapshot.fatjar && snapshot.fatjar.exists && snapshot.java && snapshot.java.ok ? 'ok' : 'unavailable';
  setStatus('anserini', anserini, anserini);

  const nf = snapshot.reproduction && snapshot.reproduction.beirCoreCondition ? 'configured' : 'unconfigured';
  setStatus('nfcorpus', nf, nf);

  const srch = snapshot.restServer && snapshot.restServer.running ? 'available' : 'unavailable';
  setStatus('search', srch, srch);

  const ev = snapshot.eval && (snapshot.eval.status === 'completed' || snapshot.eval.status === 'cached') ? 'available' : (snapshot.eval ? snapshot.eval.status : 'pending');
  setStatus('evaluation', ev, ev);

  // Detail
  const detail = $('readiness-detail');
  detail.innerHTML = '';
  const items = [
    ['Java', snapshot.java ? `${snapshot.java.major || '?'} (${snapshot.java.ok ? 'ok' : 'no'})` : 'unknown'],
    ['Anserini fatjar', snapshot.fatjar && snapshot.fatjar.path ? `${snapshot.fatjar.path} (${fmtBytes(snapshot.fatjar.sizeBytes)})` : 'missing'],
    ['Prebuilt index', snapshot.prebuiltIndex && snapshot.prebuiltIndex.name ? snapshot.prebuiltIndex.name : '—'],
    ['Repro config', snapshot.reproduction && snapshot.reproduction.beirCoreCondition ? `beir.core / ${snapshot.reproduction.beirCoreCondition.condition}` : '—'],
    ['Eval key', snapshot.reproduction && snapshot.reproduction.beirCoreCondition ? snapshot.reproduction.beirCoreCondition.evalKey : '—'],
    ['REST port', snapshot.restServer && snapshot.restServer.port ? String(snapshot.restServer.port) : '—'],
    ['Eval status', snapshot.eval ? snapshot.eval.status : 'pending'],
  ];
  for (const [k, v] of items) {
    const el = document.createElement('div');
    el.innerHTML = `<strong>${k}:</strong> <code>${escapeHtml(String(v))}</code>`;
    detail.appendChild(el);
  }

  // Environment summary
  const env = snapshot.app && snapshot.app.env ? snapshot.app.env : {};
  $('env-summary').innerHTML = `<code>PORT=${env.PORT || '?'}</code> · <code>HOST=${env.HOST || '?'}</code> · cache <code>${env.CACHE_DIR || '?'}</code> · data <code>${env.APP_DATA_DIR || '?'}</code>`;
}

function renderSamples(samples) {
  const wrap = $('samples');
  wrap.innerHTML = '';
  for (const s of samples) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = s.title;
    b.title = `${s.id}: ${s.title}`;
    b.addEventListener('click', () => {
      $('search-input').value = s.title;
      doSearch();
    });
    wrap.appendChild(b);
  }
}

function renderResults(payload) {
  const ol = $('results');
  ol.innerHTML = '';
  const meta = $('search-meta');
  if (!payload) {
    meta.textContent = '';
    return;
  }
  meta.textContent = `${payload.hits} result${payload.hits === 1 ? '' : 's'} in ${payload.durationMs} ms · index=${payload.index} · command: curl "http://127.0.0.1:<port>/v1/${payload.index}/search?query=${encodeURIComponent(payload.query)}&hits=${payload.hitsRequested}"`;
  for (const r of payload.results) {
    const li = document.createElement('li');
    li.innerHTML = `
      <div>
        <span class="rank">${r.rank}</span>
        <span class="docid">${escapeHtml(r.docid)}</span>
        <span class="score">score=${fmtNumber(r.score, 4)}</span>
      </div>
      <h4>${escapeHtml(r.title || '(untitled)')}</h4>
      <p>${escapeHtml(r.snippet || r.text || '')}</p>
      ${r.url ? `<a class="url" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.url)}</a>` : ''}
    `;
    ol.appendChild(li);
  }
}

async function doSearch() {
  const q = $('search-input').value.trim();
  const hits = Math.max(1, Math.min(50, Number($('hits-input').value || 10)));
  if (!q) return;
  $('search-button').disabled = true;
  $('search-button').textContent = 'Searching…';
  $('search-meta').textContent = `Querying Anserini RestServer for "${q}"…`;
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&hits=${hits}`);
    const body = await r.json();
    if (!r.ok) {
      renderResults(null);
      $('search-meta').innerHTML = `<span style="color: var(--bad)">Search failed: ${escapeHtml(body.error || r.statusText)}</span>`;
      return;
    }
    renderResults(body);
  } catch (err) {
    $('search-meta').innerHTML = `<span style="color: var(--bad)">Search error: ${escapeHtml(err.message)}</span>`;
  } finally {
    $('search-button').disabled = false;
    $('search-button').textContent = 'Search';
  }
}

function renderEval(evalInfo, comparison) {
  const tbody = $('eval-table').querySelector('tbody');
  tbody.innerHTML = '';
  const rows = comparison || (evalInfo.observed || []).map((o) => ({ metric: o.metric, observed: o.score, expected: null, delta: null, status: 'no-expected' }));
  if (rows.length === 0) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td colspan="5" style="color: var(--muted)">No metrics yet. Click <em>Verify / Rerun</em> to execute the reproduction.</td>`;
    tbody.appendChild(tr);
  } else {
    for (const row of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(row.metric)}</td>
        <td class="numeric">${fmtNumber(row.observed, 4)}</td>
        <td class="numeric">${row.expected == null ? '—' : fmtNumber(row.expected, 4)}</td>
        <td class="numeric">${row.delta == null ? '—' : (row.delta >= 0 ? '+' : '') + fmtNumber(row.delta, 4)}</td>
        <td class="status-${row.status}">${row.status}</td>
      `;
      tbody.appendChild(tr);
    }
  }
  // Detail block
  const detail = $('eval-detail');
  detail.innerHTML = '';
  const items = [];
  items.push(['Status', evalInfo.status || 'pending']);
  if (evalInfo.cached) items.push(['Source', 'cached artifacts from a prior run']);
  if (evalInfo.lastRunAt) items.push(['Last run at', evalInfo.lastRunAt]);
  if (evalInfo.lastDurationMs != null) items.push(['Eval duration', `${evalInfo.lastDurationMs} ms`]);
  if (evalInfo.runFile && evalInfo.runFile.path) items.push(['Run file', evalInfo.runFile.path]);
  if (evalInfo.evalFile && evalInfo.evalFile.path) items.push(['Eval output', evalInfo.evalFile.path]);
  if (evalInfo.metricDefinitions) items.push(['Metric definitions', JSON.stringify(evalInfo.metricDefinitions)]);
  for (const [k, v] of items) {
    const el = document.createElement('div');
    el.innerHTML = `<strong>${k}:</strong> <code>${escapeHtml(String(v))}</code>`;
    detail.appendChild(el);
  }
  if (evalInfo.messages && evalInfo.messages.length) {
    const list = document.createElement('div');
    list.style.gridColumn = '1 / -1';
    list.innerHTML = '<strong>Recent messages:</strong><ul style="margin:4px 0 0;padding-left:18px;">' +
      evalInfo.messages.slice(-6).map((m) => `<li><code>${escapeHtml(m.at)}</code> · ${escapeHtml(m.text)}</li>`).join('') +
      '</ul>';
    detail.appendChild(list);
  }
  $('eval-state').textContent = evalInfo.cached ? 'showing cached artifacts' : (evalInfo.status || 'pending');
  state.lastEval = evalInfo;
  state.evalLoaded = true;
}

function renderCommands(commands) {
  const wrap = $('command-list');
  wrap.innerHTML = '';
  if (!commands || !commands.length) {
    wrap.innerHTML = '<p style="color: var(--muted); font-size: 12.5px">No commands yet.</p>';
    return;
  }
  for (const c of commands) {
    const el = document.createElement('div');
    el.className = 'command';
    const logHref = c.logFile ? `<a href="/logs/${encodeURIComponent(c.logFile.split('/').pop())}" target="_blank">log</a>` : '';
    el.innerHTML = `
      <div class="cmd-line">${escapeHtml(c.command)}</div>
      <div class="meta">
        <span>exit=${c.exitCode}</span>
        <span>${c.durationMs} ms</span>
        <span>${c.startedAt}</span>
        ${logHref}
      </div>
    `;
    wrap.appendChild(el);
  }
}

function renderArtifacts(artifacts) {
  const ul = $('artifact-list');
  ul.innerHTML = '';
  for (const a of artifacts) {
    const li = document.createElement('li');
    const href = `/artifacts/${encodeURIComponent(a.path.split('/').slice(-1)[0])}`;
    li.innerHTML = `<strong>${a.kind}:</strong> <a href="${href}" target="_blank"><code>${escapeHtml(a.path)}</code></a>`;
    ul.appendChild(li);
  }
}

function renderErrors(snapshot) {
  // Strip previous errors banner if any
  const existing = document.querySelector('.errors');
  if (existing) existing.remove();
  if (!snapshot.errors || !snapshot.errors.length) return;
  const card = $('readiness-card');
  const div = document.createElement('div');
  div.className = 'errors';
  div.innerHTML = `<strong>Errors:</strong><ul>${snapshot.errors.map((e) => `<li>${escapeHtml(e.message)}</li>`).join('')}</ul>`;
  card.appendChild(div);
}

async function refreshAll() {
  try {
    const r = await fetch('/api/status');
    const snap = await r.json();
    renderStatus(snap);
    renderSamples(snap.topics && snap.topics.samples ? snap.topics.samples : []);
    renderCommands(snap.commands);
    renderArtifacts(collectArtifacts(snap));
    renderErrors(snap);
    if (!state.evalLoaded) {
      // Force-load evaluation metrics once
      try {
        const er = await fetch('/api/eval');
        const ej = await er.json();
        renderEval(ej, ej.comparison);
      } catch (_) { /* ignore */ }
    }
  } catch (err) {
    console.error('refreshAll failed', err);
  }
}

async function refreshEval() {
  const r = await fetch('/api/eval');
  const body = await r.json();
  renderEval(body.eval || body, body.comparison);
}

async function rerunEval() {
  $('eval-state').textContent = 're-running…';
  $('eval-rerun').disabled = true;
  try {
    const r = await fetch('/api/eval/rerun');
    const body = await r.json();
    if (!r.ok || !body.ok) {
      $('eval-state').textContent = 'rerun failed';
      console.error(body);
    } else {
      renderEval(body.eval, body.comparison);
      refreshAll();
    }
  } catch (err) {
    $('eval-state').textContent = 'rerun error';
  } finally {
    $('eval-rerun').disabled = false;
  }
}

function collectArtifacts(snapshot) {
  const list = [];
  for (const c of snapshot.commands || []) {
    if (c.logFile) list.push({ kind: 'log', path: c.logFile });
  }
  if (snapshot.eval && snapshot.eval.runFile && snapshot.eval.runFile.path) list.push({ kind: 'run', path: snapshot.eval.runFile.path });
  if (snapshot.eval && snapshot.eval.evalFile && snapshot.eval.evalFile.path) list.push({ kind: 'eval', path: snapshot.eval.evalFile.path });
  if (snapshot.reproduction && snapshot.reproduction.rawShowPath) list.push({ kind: 'repro-yaml', path: snapshot.reproduction.rawShowPath });
  return list;
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

document.addEventListener('DOMContentLoaded', () => {
  $('search-form').addEventListener('submit', (e) => { e.preventDefault(); doSearch(); });
  $('eval-refresh').addEventListener('click', refreshEval);
  $('eval-rerun').addEventListener('click', rerunEval);
  refreshAll();
  setInterval(refreshAll, 5000);
});
