"""
NFCorpus Live Retrieval Diagnostics Workbench
Flask web application for Render deployment.
"""

import os
import json
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

from ans_worker import AnseriniWorker

# ---- App Setup ----

WORKSPACE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="static", static_url_path="/static")
worker = AnseriniWorker(str(WORKSPACE_DIR))

# ---- HTML Template (inline for single-file simplicity) ----

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NFCorpus Live Retrieval Diagnostics</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #f5f5f5; color: #222; }
header { background: #1a1a2e; color: #e0e0e0; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
header h1 { font-size: 1.3rem; }
header .dataset-badge { background: #16213e; padding: 4px 12px; border-radius: 4px; font-size: 0.85rem; color: #53d8fb; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }

/* Panels */
.panels { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
@media (max-width: 800px) { .panels { grid-template-columns: 1fr; } }
.panel { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.panel h2 { font-size: 1.0rem; margin-bottom: 12px; border-bottom: 2px solid #16213e; padding-bottom: 6px; }

/* Status indicators */
.status-ok { color: #16a34a; }
.status-warn { color: #d97706; }
.status-err { color: #dc2626; }
.status-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.9rem; }
.status-label { font-weight: 500; }

/* Search */
.search-box { display: flex; gap: 8px; margin-bottom: 12px; }
.search-box input { flex: 1; padding: 10px 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.95rem; }
.search-box button { padding: 10px 20px; background: #1a56db; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
.search-box button:hover { background: #1e40af; }
.search-box button:disabled { background: #94a3b8; cursor: not-allowed; }
.sample-queries { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.sample-query { background: #e2e8f0; padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; cursor: pointer; border: none; }
.sample-query:hover { background: #cbd5e1; }
.results { max-height: 500px; overflow-y: auto; }
.result-item { padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }
.result-item .rank { font-weight: 700; color: #1a56db; margin-right: 8px; }
.result-item .docid { font-size: 0.8rem; color: #666; margin-right: 8px; }
.result-item .score { font-size: 0.8rem; color: #059669; margin-right: 8px; }
.result-item .text { font-size: 0.9rem; margin-top: 2px; line-height: 1.4; color: #333; word-break: break-word; }
.no-results, .search-error { padding: 20px; text-align: center; color: #666; }

/* Evaluation */
.eval-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 8px; }
.eval-table th, .eval-table td { padding: 8px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; }
.eval-table th { background: #f8fafc; font-weight: 600; }
.eval-status-match { color: #16a34a; font-weight: 600; }
.eval-status-close { color: #d97706; font-weight: 600; }
.eval-status-fail { color: #dc2626; font-weight: 600; }
.eval-status-missing { color: #9333ea; }
.eval-actions { margin: 8px 0; }
.eval-actions button { padding: 8px 16px; margin-right: 8px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; font-size: 0.85rem; }
.eval-actions button:hover { background: #f1f5f9; }
.eval-actions button:disabled { opacity: 0.5; cursor: not-allowed; }

/* Command/Artifact drawer */
.drawer-toggle { cursor: pointer; padding: 8px 0; color: #1a56db; font-weight: 500; font-size: 0.9rem; }
.drawer { display: none; margin-top: 8px; }
.drawer.open { display: block; }
.drawer pre { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 0.8rem; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
.drawer .artifact-block { margin: 8px 0; }
.drawer .artifact-block h3 { font-size: 0.9rem; margin-bottom: 4px; }

/* Loading spinner */
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #ccc; border-top-color: #1a56db; border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 6px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Status banner */
.banner { padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; }
.banner-ok { background: #dbeafe; border: 1px solid #93c5fd; }
.banner-warn { background: #fef3c7; border: 1px solid #fcd34d; }
.banner-err { background: #fee2e2; border: 1px solid #fca5a5; }
</style>
</head>
<body>
<header>
  <h1>NFCorpus Live Retrieval Diagnostics</h1>
  <span class="dataset-badge">NFCorpus &bull; Anserini BM25</span>
</header>

<div class="container">
  <!-- Status Banner -->
  <div id="banner" class="banner banner-warn">
    <span class="spinner"></span> Checking system readiness...
  </div>

  <div class="panels">
    <!-- Readiness Panel -->
    <div class="panel" id="readiness-panel">
      <h2>System Readiness</h2>
      <div id="readiness-content">
        <span class="spinner"></span> Loading...
      </div>
    </div>

    <!-- Evaluation Panel -->
    <div class="panel" id="eval-panel">
      <h2>BM25 Evaluation</h2>
      <div class="eval-actions">
        <button id="btn-eval" onclick="triggerEvaluation(false)">View Cached / Run Eval</button>
        <button id="btn-rerun" onclick="triggerEvaluation(true)">Re-run Fresh</button>
      </div>
      <div id="eval-content">
        <p style="color:#666; font-size:0.9rem;">Click "View Cached" to load evaluation results.</p>
      </div>
    </div>
  </div>

  <!-- Search Panel -->
  <div class="panel" style="margin-bottom:20px;">
    <h2>Live Search &mdash; NFCorpus</h2>
    <div class="sample-queries" id="sample-queries">
      <button class="sample-query" onclick="doSearch('cancer treatment')">cancer treatment</button>
      <button class="sample-query" onclick="doSearch('heart disease prevention')">heart disease prevention</button>
      <button class="sample-query" onclick="doSearch('diabetes management')">diabetes management</button>
      <button class="sample-query" onclick="doSearch('Alzheimer symptoms')">Alzheimer symptoms</button>
      <button class="sample-query" onclick="doSearch('vaccine development')">vaccine development</button>
    </div>
    <div class="search-box">
      <input type="text" id="search-input" placeholder="Enter a medical/health query..." onkeydown="if(event.key==='Enter')doSearch()">
      <button id="btn-search" onclick="doSearch()">Search</button>
    </div>
    <div id="search-results">
      <p style="color:#666; padding:20px; text-align:center;">Enter a query or click a sample query above.</p>
    </div>
  </div>

  <!-- Commands & Artifacts Drawer -->
  <div class="panel">
    <div class="drawer-toggle" onclick="toggleDrawer()">
      &#9660; Commands &amp; Artifacts
    </div>
    <div class="drawer" id="drawer">
      <div class="artifact-block" id="artifacts-list">
        <h3>Artifacts</h3>
        <p style="color:#666;">Click "View Cached" in evaluation panel to load.</p>
      </div>
      <div class="artifact-block">
        <h3>Commands Executed</h3>
        <div id="commands-list"></div>
      </div>
    </div>
  </div>
</div>

<script>
const BASE = '';

async function loadStatus() {
  try {
    const r = await fetch(BASE + '/api/status');
    const data = await r.json();

    // Banner
    const banner = document.getElementById('banner');
    if (data.search_available) {
      banner.className = 'banner banner-ok';
      banner.innerHTML = '&#9989; System ready &mdash; Anserini ' + (data.fatjar.version || '') + ', NFCorpus ready for live search and evaluation.';
    } else if (data.fatjar.available) {
      banner.className = 'banner banner-warn';
      banner.innerHTML = '&#9888; Fatjar found but search not yet verified. Run setup to complete.';
    } else {
      banner.className = 'banner banner-err';
      banner.innerHTML = '&#10060; Anserini fatjar not found. Check deployment setup.';
    }

    // Readiness Panel
    const rc = document.getElementById('readiness-content');
    const jv = data.java;
    const fj = data.fatjar;
    const ix = data.nfcorpus_index;
    const sm = data.smoke_test;
    rc.innerHTML = `
      <div class="status-row"><span class="status-label">Java</span><span class="${jv.is_java21 ? 'status-ok' : 'status-err'}">${jv.is_java21 ? '&#9989;' : '&#10060;'} ${jv.version || 'not found'}</span></div>
      <div class="status-row"><span class="status-label">Anserini Fatjar</span><span class="${fj.available ? 'status-ok' : 'status-err'}">${fj.available ? '&#9989; v' + fj.version : '&#10060; missing'}</span></div>
      <div class="status-row"><span class="status-label">NFCorpus Index</span><span class="${ix.available ? 'status-ok' : 'status-warn'}">${ix.available ? '&#9989; cached' : '&#9888; auto-download'}</span></div>
      <div class="status-row"><span class="status-label">CACM Smoke Test</span><span class="${sm && sm.eval_ok ? 'status-ok' : 'status-err'}">${sm && sm.eval_ok ? '&#9989; pass' : sm ? '&#10060; fail' : '&#10060; not run'}</span></div>
      <div class="status-row"><span class="status-label">NFCorpus Dataset</span><span class="status-ok">&#9989; NFCorpus (BEIR)</span></div>
      <div class="status-row"><span class="status-label">Search Available</span><span class="${data.search_available ? 'status-ok' : 'status-err'}">${data.search_available ? '&#9989; yes' : '&#10060; no'}</span></div>
      <div class="status-row"><span class="status-label">Evaluation Available</span><span class="${data.evaluation_available ? 'status-ok' : 'status-err'}">${data.evaluation_available ? '&#9989; yes' : '&#10060; no'}</span></div>
      <div style="margin-top:8px; font-size:0.8rem; color:#888;">Index: ${ix.index_name}<br>Path: ${ix.path}</div>
    `;

    // Pre-populate evaluation if available
    if (data.evaluation && data.evaluation.observed) {
      renderEvaluation(data.evaluation);
    }

    // Enable/disable search
    document.getElementById('btn-search').disabled = !data.search_available;

  } catch (err) {
    document.getElementById('banner').className = 'banner banner-err';
    document.getElementById('banner').innerHTML = '&#10060; Failed to load status: ' + err.message;
  }
}

async function doSearch(query) {
  const q = query || document.getElementById('search-input').value.trim();
  if (!q) return;

  const resultsDiv = document.getElementById('search-results');
  resultsDiv.innerHTML = '<span class="spinner"></span> Searching...';

  try {
    const r = await fetch(BASE + '/api/search?query=' + encodeURIComponent(q));
    const data = await r.json();

    let html = '';
    if (data.results && data.results.length > 0) {
      html += `<p style="font-size:0.85rem; color:#666; margin-bottom:8px;">${data.results.length} results in ${data.elapsed_ms}ms</p>`;
      data.results.forEach((doc, i) => {
        const rank = i + 1;
        const docid = (doc.docid || doc.id || '?');
        const score = (doc.score !== undefined ? Number(doc.score).toFixed(4) : '-');
        const text = (doc.contents || doc.text || doc.title || doc.body || '');
        const snippet = text.length > 400 ? text.substring(0, 400) + '...' : text;
        html += `<div class="result-item">
          <span class="rank">${rank}.</span>
          <span class="docid">${escapeHtml(docid)}</span>
          <span class="score">score: ${score}</span>
          <div class="text">${escapeHtml(snippet)}</div>
        </div>`;
      });
      resultsDiv.innerHTML = html;
    } else if (data.error) {
      resultsDiv.innerHTML = '<div class="search-error">Search error: ' + escapeHtml(data.error) + '</div>';
    } else {
      resultsDiv.innerHTML = '<div class="no-results">No results found for "' + escapeHtml(q) + '"</div>';
    }
  } catch (err) {
    resultsDiv.innerHTML = '<div class="search-error">Error: ' + escapeHtml(err.message) + '</div>';
  }
}

async function triggerEvaluation(force) {
  const content = document.getElementById('eval-content');
  content.innerHTML = '<span class="spinner"></span> Running evaluation... This may take a minute.';

  document.getElementById('btn-eval').disabled = true;
  document.getElementById('btn-rerun').disabled = true;

  try {
    const r = await fetch(BASE + '/api/evaluate' + (force ? '?force=1' : ''));
    const data = await r.json();
    renderEvaluation(data);

    // Also refresh commands & artifacts
    loadCommandsAndArtifacts();

  } catch (err) {
    content.innerHTML = '<div class="search-error">Error: ' + escapeHtml(err.message) + '</div>';
  } finally {
    document.getElementById('btn-eval').disabled = false;
    document.getElementById('btn-rerun').disabled = false;
  }
}

function renderEvaluation(data) {
  const content = document.getElementById('eval-content');
  if (data.status === 'error') {
    content.innerHTML = `<div class="search-error">Evaluation error: ${escapeHtml(data.error || 'unknown')}</div>`;
    return;
  }

  let rows = '';
  if (data.comparison) {
    data.comparison.forEach(c => {
      let statusClass = 'eval-status-missing';
      let statusLabel = 'missing';
      if (c.status === 'match') { statusClass = 'eval-status-match'; statusLabel = 'MATCH'; }
      else if (c.status === 'close') { statusClass = 'eval-status-close'; statusLabel = 'CLOSE'; }
      else if (c.status === 'fail') { statusClass = 'eval-status-fail'; statusLabel = 'FAIL'; }

      rows += `<tr>
        <td><strong>${escapeHtml(c.metric)}</strong></td>
        <td>${c.expected !== undefined && c.expected !== null ? c.expected.toFixed(4) : '-'}</td>
        <td>${c.observed !== undefined && c.observed !== null ? c.observed.toFixed(4) : '-'}</td>
        <td>${c.delta !== undefined && c.delta !== null ? (c.delta >= 0 ? '+' : '') + c.delta.toFixed(6) : '-'}</td>
        <td class="${statusClass}">${statusLabel}</td>
      </tr>`;
    });
  } else {
    rows = '<tr><td colspan="5">No comparison data</td></tr>';
  }

  const cachedNote = data.was_cached ? '<span style="font-size:0.8rem; color:#888;">(cached result)</span>' : '<span style="font-size:0.8rem; color:#16a34a;">(fresh run)</span>';

  content.innerHTML = `
    <table class="eval-table">
      <tr><th>Metric</th><th>Expected</th><th>Observed</th><th>Delta</th><th>Status</th></tr>
      ${rows}
    </table>
    <p style="margin-top:8px; font-size:0.8rem; color:#666;">
      Run file: ${escapeHtml(data.run_path || '-')} ${cachedNote}
      <br>Search: ${data.search_elapsed_ms || 0}ms &bull; Eval: ${data.eval_elapsed_ms || 0}ms
    </p>
  `;
}

async function loadCommandsAndArtifacts() {
  try {
    const cr = await fetch(BASE + '/api/commands');
    const cmds = await cr.json();

    let html = '';
    cmds.slice().reverse().forEach(c => {
      html += `<p style="font-size:0.8rem; margin:6px 0;"><strong>Exit ${c.exit_code}</strong> (${c.elapsed_ms}ms)</p>`;
      html += `<pre>${escapeHtml(c.command)}\n\n${escapeHtml(c.output_preview || '')}</pre>`;
    });
    document.getElementById('commands-list').innerHTML = html || '<p style="color:#666;">No commands executed yet.</p>';

    const ar = await fetch(BASE + '/api/artifacts');
    const arts = await ar.json();
    let ahtml = '<h3>Artifacts</h3>';
    for (const [name, info] of Object.entries(arts)) {
      ahtml += `<div class="artifact-block">
        <h3>${escapeHtml(name)} (${(info.size/1024).toFixed(1)} KB)</h3>
        <p style="font-size:0.8rem; color:#666;">Path: ${escapeHtml(info.path)}</p>
        <pre>${escapeHtml(info.preview || '')}</pre>
      </div>`;
    }
    document.getElementById('artifacts-list').innerHTML = ahtml || '<p style="color:#666;">No artifacts yet.</p>';

  } catch (err) {
    // silent
  }
}

function toggleDrawer() {
  const d = document.getElementById('drawer');
  d.classList.toggle('open');
  if (d.classList.contains('open')) {
    loadCommandsAndArtifacts();
  }
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Load on start
loadStatus();
// Auto-load commands
setTimeout(loadCommandsAndArtifacts, 2000);
</script>
</body>
</html>"""

# ---- Routes ----

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/health")
def health():
    status = worker.full_readiness()
    return jsonify({
        "app_status": status["app_status"],
        "anserini_available": status["fatjar"]["available"],
        "anserini_version": status["fatjar"]["version"],
        "nfcorpus_ready": status["nfcorpus_index"]["available"] or True,
        "search_available": status["search_available"],
        "evaluation_available": status["evaluation_available"],
        "java": status["java"],
    })

@app.route("/api/status")
def api_status():
    return jsonify(worker.full_readiness())

@app.route("/api/search")
def api_search():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter"}), 400
    result = worker.search(query, hits=10)
    return jsonify(result)

@app.route("/api/evaluate")
def api_evaluate():
    force = request.args.get("force", "0") == "1"
    result = worker.run_evaluation(force=force)
    return jsonify(result)

@app.route("/api/commands")
def api_commands():
    return jsonify(worker.get_commands())

@app.route("/api/artifacts")
def api_artifacts():
    return jsonify(worker.get_artifacts())


# ---- Main ----

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
