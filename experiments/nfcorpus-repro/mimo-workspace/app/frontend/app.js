/**
 * NFCorpus Retrieval Diagnostics Workbench — Frontend
 */

const API = {
    async getStatus() {
        const res = await fetch('/api/status');
        return res.json();
    },

    async search(query, hits = 10) {
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, hits })
        });
        return res.json();
    },

    async getEvaluation(force = false) {
        const url = '/api/evaluation' + (force ? '?force=true' : '');
        const res = await fetch(url);
        return res.json();
    },

    async rerunEvaluation() {
        const res = await fetch('/api/evaluation/rerun', { method: 'POST' });
        return res.json();
    },

    async getCommands() {
        const res = await fetch('/api/commands');
        return res.json();
    }
};

// State
let isReady = false;
let searchEnabled = false;
let evalEnabled = false;
let commandsVisible = false;

// Readiness polling
async function pollReadiness() {
    try {
        const status = await API.getStatus();
        updateReadinessPanel(status);

        if (status.setup_done && status.search_available) {
            enableSearch();
            if (status.evaluation_available) {
                loadEvaluation();
            }
            loadCommands();
            updateVerification(status);
            return; // Stop polling
        }
    } catch (e) {
        console.error('Status poll failed:', e);
    }

    setTimeout(pollReadiness, 3000);
}

function updateReadinessPanel(status) {
    const items = {
        'status-java': {
            ok: status.java?.ok,
            value: status.java?.version || 'not found'
        },
        'status-fatjar': {
            ok: status.fatjar?.ok,
            value: status.fatjar?.version ? `v${status.fatjar.version}` : 'not ready'
        },
        'status-nfcorpus': {
            ok: status.nfcorpus?.index_ready,
            value: status.nfcorpus?.index_ready ? `${status.nfcorpus.index_name}` : 'downloading...'
        },
        'status-search': {
            ok: status.search_available,
            value: status.search_available ? 'ready' : 'not ready'
        },
        'status-eval': {
            ok: status.evaluation_available,
            value: status.evaluation_available ? 'ready' : 'not ready'
        },
        'status-reproduction': {
            ok: status.reproduction?.discovered,
            value: status.reproduction?.discovered ? 'discovered' : 'not found'
        }
    };

    let readyCount = 0;
    const totalItems = Object.keys(items).length;

    for (const [id, info] of Object.entries(items)) {
        const el = document.getElementById(id);
        if (!el) continue;

        el.className = 'status-item ' + (info.ok ? 'ok' : (info.ok === false ? 'error' : 'loading'));
        el.querySelector('.status-icon').textContent = info.ok ? '✅' : (info.ok === false ? '❌' : '⏳');
        el.querySelector('.status-value').textContent = info.value;

        if (info.ok) readyCount++;
    }

    const progressFill = document.getElementById('setup-progress-fill');
    if (progressFill) {
        const pct = Math.round((readyCount / totalItems) * 100);
        progressFill.style.width = pct + '%';
        if (status.setup_done) {
            progressFill.classList.add('complete');
        }
    }
}

function enableSearch() {
    searchEnabled = true;
    const input = document.getElementById('search-input');
    const btn = document.getElementById('search-btn');
    if (input) input.disabled = false;
    if (btn) btn.disabled = false;
}

function setQuery(q) {
    const input = document.getElementById('search-input');
    if (input) {
        input.value = q;
        doSearch();
    }
}

async function doSearch() {
    const input = document.getElementById('search-input');
    const resultsDiv = document.getElementById('search-results');
    const query = input?.value?.trim();

    if (!query || !searchEnabled) return;

    resultsDiv.innerHTML = '<div class="search-loading">Searching NFCorpus via Anserini...</div>';

    try {
        const data = await API.search(query);

        if (data.error) {
            resultsDiv.innerHTML = `<div class="search-error">❌ ${data.error}</div>`;
            return;
        }

        if (!data.results || data.results.length === 0) {
            resultsDiv.innerHTML = '<div class="search-loading">No results found.</div>';
            return;
        }

        let html = '';
        const results = Array.isArray(data.results) ? data.results : [];
        results.forEach((r, i) => {
            const rank = r.rank || (i + 1);
            const docid = r.docid || r.id || r.doc || '—';
            const score = r.score !== undefined ? r.score.toFixed(4) : '—';
            const content = r.content || r.snippet || r.text || r.raw || '';
            const snippet = content.length > 300 ? content.substring(0, 300) + '…' : content;

            html += `
                <div class="search-result" data-testid="search-result">
                    <div class="result-header">
                        <span class="result-rank">#${rank}</span>
                        <span class="result-docid">${escapeHtml(String(docid))}</span>
                        <span class="result-score">score: ${score}</span>
                    </div>
                    <div class="result-content">
                        <div class="snippet">${escapeHtml(snippet)}</div>
                    </div>
                </div>
            `;
        });

        resultsDiv.innerHTML = html;
    } catch (e) {
        resultsDiv.innerHTML = `<div class="search-error">❌ Search failed: ${e.message}</div>`;
    }
}

async function loadEvaluation() {
    const contentDiv = document.getElementById('eval-content');
    const rerunBtn = document.getElementById('eval-rerun-btn');

    try {
        const data = await API.getEvaluation();

        if (data.error) {
            contentDiv.innerHTML = `<div class="search-error">❌ ${data.error}</div>`;
            return;
        }

        if (!data.comparison || Object.keys(data.comparison).length === 0) {
            contentDiv.innerHTML = '<div class="eval-loading">No evaluation data available yet.</div>';
            return;
        }

        evalEnabled = true;
        if (rerunBtn) rerunBtn.disabled = false;

        let html = `
            <div class="eval-meta">
                Elapsed: ${data.elapsed}s • Run file: <code>${escapeHtml(data.run_file || '')}</code>
                ${data.cached ? ' • <strong>(cached result)</strong>' : ''}
            </div>
            <table class="eval-metrics-table" data-testid="eval-metrics-table">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>Observed</th>
                        <th>Expected</th>
                        <th>Delta</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const [metric, info] of Object.entries(data.comparison)) {
            const observed = info.observed !== undefined ? info.observed.toFixed(4) : '—';
            const expected = info.expected !== undefined ? info.expected.toFixed(4) : '—';
            const delta = info.delta !== undefined ? info.delta.toFixed(6) : '—';
            const statusClass = `eval-status-${info.status || 'unknown'}`;
            const statusLabel = {
                'pass': '✅ PASS',
                'close': '⚠️ CLOSE',
                'fail': '❌ FAIL',
                'no_expected': '— N/A'
            }[info.status] || '—';

            html += `
                <tr data-testid="eval-row">
                    <td>${escapeHtml(metric)}</td>
                    <td>${observed}</td>
                    <td>${expected}</td>
                    <td>${delta}</td>
                    <td class="${statusClass}">${statusLabel}</td>
                </tr>
            `;
        }

        html += '</tbody></table>';

        if (data.search_command) {
            html += `<div class="eval-meta">Search: <code>${escapeHtml(data.search_command)}</code></div>`;
        }
        if (data.eval_command) {
            html += `<div class="eval-meta">Eval: <code>${escapeHtml(data.eval_command)}</code></div>`;
        }

        contentDiv.innerHTML = html;

        const timestamp = document.getElementById('eval-timestamp');
        if (timestamp) {
            timestamp.textContent = `Last run: ${new Date().toLocaleString()}`;
        }
    } catch (e) {
        contentDiv.innerHTML = `<div class="search-error">❌ Failed to load evaluation: ${e.message}</div>`;
    }
}

async function rerunEvaluation() {
    const contentDiv = document.getElementById('eval-content');
    const rerunBtn = document.getElementById('eval-rerun-btn');

    if (rerunBtn) rerunBtn.disabled = true;
    contentDiv.innerHTML = '<div class="eval-loading">🔄 Re-running BM25 evaluation...</div>';

    try {
        const data = await API.rerunEvaluation();
        loadEvaluation(); // Refresh
    } catch (e) {
        contentDiv.innerHTML = `<div class="search-error">❌ Rerun failed: ${e.message}</div>`;
    } finally {
        if (rerunBtn) rerunBtn.disabled = false;
    }
}

async function loadCommands() {
    try {
        const data = await API.getCommands();
        const listDiv = document.getElementById('commands-list');
        const artDiv = document.getElementById('artifacts-list');

        if (!data.commands || data.commands.length === 0) {
            listDiv.innerHTML = '<div class="eval-loading">No commands recorded yet.</div>';
            return;
        }

        let html = '';
        data.commands.forEach((cmd, i) => {
            const statusClass = cmd.status || 'running';
            const output = cmd.stdout || cmd.stderr || cmd.error || '';
            html += `
                <div class="command-entry" data-testid="command-entry">
                    <div class="cmd-status ${statusClass}">${statusClass.toUpperCase()}</div>
                    <div class="cmd-text">${escapeHtml(cmd.command)}</div>
                    ${output ? `<div class="cmd-output">${escapeHtml(output.substring(0, 1000))}</div>` : ''}
                </div>
            `;
        });
        listDiv.innerHTML = html;

        // Artifacts
        if (data.artifacts && Object.keys(data.artifacts).length > 0) {
            let artHtml = '<div class="artifacts-section"><h3>Generated Artifacts</h3>';
            for (const [key, path] of Object.entries(data.artifacts)) {
                artHtml += `<div class="artifact-item">${escapeHtml(key)}: ${escapeHtml(String(path))}</div>`;
            }
            artHtml += '</div>';
            artDiv.innerHTML = artHtml;
        }
    } catch (e) {
        console.error('Failed to load commands:', e);
    }
}

function toggleDrawer(id) {
    const content = document.getElementById(`${id}-content`);
    const toggle = document.getElementById(`${id}-toggle`);
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        toggle.className = 'toggle-icon open';
        commandsVisible = true;
        loadCommands(); // Refresh
    } else {
        content.style.display = 'none';
        toggle.className = 'toggle-icon closed';
        commandsVisible = false;
    }
}

function updateVerification(status) {
    const badge = document.getElementById('verification-badge');
    const icon = badge.querySelector('.badge-icon');
    const text = badge.querySelector('.badge-text');

    if (status.search_available && status.evaluation_available) {
        badge.className = 'verification-badge verified';
        icon.textContent = '✅';
        text.textContent = 'Verified: Real Anserini-backed search and evaluation active.';
    } else if (status.fatjar_ok) {
        badge.className = 'verification-badge partial';
        icon.textContent = '⚠️';
        text.textContent = 'Partial: Anserini available but NFCorpus not fully ready.';
    } else {
        badge.className = 'verification-badge pending';
        icon.textContent = '⏳';
        text.textContent = 'Verification pending: setup in progress.';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Enter key triggers search
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('search-input');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') doSearch();
        });
    }

    // Start polling
    pollReadiness();
});
