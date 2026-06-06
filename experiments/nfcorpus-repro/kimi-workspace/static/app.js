(function () {
  const API_PREFIX = '';

  const els = {
    appStatus: document.getElementById('app-status'),
    javaStatus: document.getElementById('java-status'),
    fatjarStatus: document.getElementById('fatjar-status'),
    corpusStatus: document.getElementById('corpus-status'),
    indexStatus: document.getElementById('index-status'),
    searchStatus: document.getElementById('search-status'),
    evalStatus: document.getElementById('eval-status'),
    setupError: document.getElementById('setup-error'),
    setupLog: document.getElementById('setup-log'),
    searchInput: document.getElementById('search-input'),
    searchBtn: document.getElementById('search-btn'),
    sampleQueries: document.getElementById('sample-queries'),
    searchResults: document.getElementById('search-results'),
    evalContent: document.getElementById('eval-content'),
    rerunBtn: document.getElementById('rerun-btn'),
    commandsContent: document.getElementById('commands-content'),
    anseriniVersion: document.getElementById('anserini-version'),
  };

  function setBadge(el, type, text) {
    el.className = 'badge badge-' + type;
    el.textContent = text;
  }

  async function fetchJson(url, opts) {
    try {
      const res = await fetch(url, opts);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (e) {
      console.error('Fetch error', url, e);
      throw e;
    }
  }

  async function updateStatus() {
    try {
      const data = await fetchJson(`${API_PREFIX}/api/status`);
      const s = data;

      // Overall app status
      if (s.setup_error) {
        setBadge(els.appStatus, 'danger', 'Error');
        els.setupError.style.display = 'block';
        els.setupError.textContent = s.setup_error;
      } else if (s.search_ready) {
        setBadge(els.appStatus, 'success', 'Ready');
        els.setupError.style.display = 'none';
      } else if (s.setup_in_progress) {
        setBadge(els.appStatus, 'info', 'Setting up...');
        els.setupError.style.display = 'none';
      } else {
        setBadge(els.appStatus, 'warning', 'Not ready');
      }

      setBadge(els.javaStatus, s.java_ok ? 'success' : 'danger', s.java_ok ? 'OK' : 'Missing');
      setBadge(els.fatjarStatus, s.fatjar_ready ? 'success' : (s.setup_in_progress ? 'info' : 'danger'), s.fatjar_ready ? 'Ready' : 'Missing');
      setBadge(els.corpusStatus, s.corpus_ready ? 'success' : (s.setup_in_progress ? 'info' : 'danger'), s.corpus_ready ? 'Ready' : 'Missing');
      setBadge(els.indexStatus, s.index_ready ? 'success' : (s.setup_in_progress ? 'info' : 'danger'), s.index_ready ? 'Ready' : 'Missing');
      setBadge(els.searchStatus, s.search_ready ? 'success' : (s.setup_in_progress ? 'info' : 'danger'), s.search_ready ? 'Available' : 'Unavailable');
      setBadge(els.evalStatus, s.evaluation_ready ? 'success' : (s.setup_in_progress ? 'info' : 'danger'), s.evaluation_ready ? 'Complete' : 'Pending');

      els.setupLog.textContent = (s.setup_log || []).join('\n');
      els.setupLog.scrollTop = els.setupLog.scrollHeight;

      if (s.search_ready) {
        els.searchInput.disabled = false;
        els.searchBtn.disabled = false;
        els.rerunBtn.disabled = false;
      }

      if (s.sample_queries && s.sample_queries.length > 0) {
        renderSamples(s.sample_queries);
      }

      if (s.evaluation_ready && s.evaluation) {
        renderEvaluation(s.evaluation, s.commands, s.artifacts);
      }

      if (s.commands && s.artifacts) {
        renderCommands(s.commands, s.artifacts);
      }

      if (s.fatjar_path) {
        const m = s.fatjar_path.match(/anserini-([\d.]+)/);
        if (m) els.anseriniVersion.textContent = m[1];
      }

      return s.search_ready;
    } catch (e) {
      setBadge(els.appStatus, 'danger', 'Unreachable');
      return false;
    }
  }

  function renderSamples(queries) {
    if (els.sampleQueries.dataset.loaded) return;
    els.sampleQueries.innerHTML = '';
    queries.slice(0, 8).forEach(q => {
      const chip = document.createElement('span');
      chip.className = 'sample-chip';
      chip.textContent = q.text;
      chip.title = q.id;
      chip.addEventListener('click', () => {
        els.searchInput.value = q.text;
        doSearch();
      });
      els.sampleQueries.appendChild(chip);
    });
    els.sampleQueries.dataset.loaded = 'true';
  }

  async function doSearch() {
    const query = els.searchInput.value.trim();
    if (!query) return;
    els.searchBtn.disabled = true;
    els.searchResults.innerHTML = '<div style="color:var(--muted);">Searching...</div>';
    try {
      const data = await fetchJson(`${API_PREFIX}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, hits: 10 }),
      });
      renderResults(data);
    } catch (e) {
      els.searchResults.innerHTML = `<div class="error-box">Search failed: ${e.message}</div>`;
    } finally {
      els.searchBtn.disabled = false;
    }
  }

  function renderResults(data) {
    if (!data.results || data.results.length === 0) {
      els.searchResults.innerHTML = '<p style="color:var(--muted);">No results found.</p>';
      return;
    }
    let html = '';
    data.results.forEach(r => {
      const title = (r.doc && r.doc.title) || r.docid;
      const text = (r.doc && r.doc.text) || '';
      html += `
        <div class="result-item">
          <div class="result-meta">Rank ${r.rank} &middot; DocID: ${r.docid} &middot; Score: ${r.score.toFixed(4)}</div>
          <div class="result-title">${escapeHtml(title)}</div>
          <div class="result-text">${escapeHtml(text)}</div>
        </div>
      `;
    });
    html += `<div style="margin-top:0.5rem;font-size:0.75rem;color:var(--muted);">Command: <code>${escapeHtml(data.command)}</code></div>`;
    els.searchResults.innerHTML = html;
  }

  function renderEvaluation(ev, commands, artifacts) {
    let html = '<table><thead><tr><th>Metric</th><th>Expected</th><th>Observed</th><th>Delta</th><th>Status</th></tr></thead><tbody>';
    const keys = Object.keys(ev.expected || {});
    keys.forEach(k => {
      const exp = ev.expected[k];
      const obs = (ev.observed || {})[k];
      const st = (ev.status || {})[k];
      const delta = obs != null ? (obs - exp).toFixed(4) : '-';
      const deltaSign = obs != null ? (obs >= exp ? '+' : '') : '';
      let statusClass = 'metric-' + (st || 'unknown');
      let statusText = st === 'pass' ? 'Pass' : st === 'close' ? 'Close' : st === 'fail' ? 'Fail' : 'Unknown';
      html += `<tr>
        <td>${k}</td>
        <td>${exp.toFixed(4)}</td>
        <td>${obs != null ? obs.toFixed(4) : '-'}</td>
        <td>${deltaSign}${delta}</td>
        <td class="${statusClass}">${statusText}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    html += `<p style="font-size:0.8rem;color:var(--muted);margin-top:0.5rem;">Elapsed: ${ev.elapsed_ms}ms</p>`;
    html += `<div style="margin-top:0.5rem;"><strong>Artifacts:</strong><br>`;
    html += `<span class="artifact-path">Run: ${artifacts.run || '-'}</span><br>`;
    html += `<span class="artifact-path">Eval: ${artifacts.eval || '-'}</span></div>`;
    els.evalContent.innerHTML = html;
  }

  function renderCommands(commands, artifacts) {
    let html = '';
    const order = ['java_check', 'fatjar_verify', 'corpus_download', 'index_build', 'search_collection', 'evaluation'];
    const labels = {
      java_check: 'Java Version Check',
      fatjar_verify: 'Fatjar Verification (CACM smoke test)',
      corpus_download: 'NFCorpus Download',
      index_build: 'Index Build',
      search_collection: 'BM25 SearchCollection',
      evaluation: 'TrecEval',
    };
    order.forEach(key => {
      if (commands[key]) {
        html += `<h4>${labels[key] || key}</h4><pre>${escapeHtml(commands[key])}</pre>`;
      }
    });
    html += '<h4>Artifacts</h4>';
    Object.entries(artifacts).forEach(([k, v]) => {
      html += `<div class="artifact-path">${k}: ${v}</div>`;
    });
    els.commandsContent.innerHTML = html;
  }

  function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  els.searchBtn.addEventListener('click', doSearch);
  els.searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

  els.rerunBtn.addEventListener('click', async () => {
    els.rerunBtn.disabled = true;
    els.evalContent.innerHTML = '<p style="color:var(--muted);">Rerunning evaluation...</p>';
    try {
      const data = await fetchJson(`${API_PREFIX}/api/evaluation/rerun`, { method: 'POST' });
      renderEvaluation(data, data.commands, data.artifacts);
    } catch (e) {
      els.evalContent.innerHTML = `<div class="error-box">Rerun failed: ${e.message}</div>`;
    } finally {
      els.rerunBtn.disabled = false;
    }
  });

  // Poll status every 2 seconds until ready, then every 10 seconds
  async function poll() {
    const ready = await updateStatus();
    setTimeout(poll, ready ? 10000 : 2000);
  }
  poll();
})();
