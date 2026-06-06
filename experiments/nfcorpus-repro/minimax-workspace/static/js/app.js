/**
 * NFCorpus Live Retrieval Diagnostics Workbench - Frontend
 * Uses real Anserini-backed search and evaluation.
 */

const API_BASE = window.location.origin;

// State
let appState = {
    status: null,
    commands: null,
    artifacts: null,
    lastSearchResults: null,
    isSearching: false,
    isEvaluating: false,
    evaluationCached: false
};

// DOM elements
const $ = (id) => document.getElementById(id);

const elements = {
    // Status
    javaStatus: $('java-status'),
    anseriniStatus: $('anserini-status'),
    indexStatus: $('index-status'),
    searchStatus: $('search-status'),
    evalStatus: $('eval-status'),
    restStatus: $('rest-status'),
    statusBar: $('status-bar'),
    statusMessage: $('status-message'),

    // Search
    searchQuery: $('search-query'),
    searchBtn: $('search-btn'),
    clearBtn: $('clear-btn'),
    sampleList: $('sample-list'),
    searchLoading: $('search-loading'),
    searchError: $('search-error'),
    searchResults: $('search-results'),
    resultsMeta: $('results-meta'),
    resultList: $('result-list'),

    // Evaluation
    runEvalBtn: $('run-eval-btn'),
    rerunEvalBtn: $('rerun-eval-btn'),
    evalCacheIndicator: $('eval-cache-indicator'),
    evalLoading: $('eval-loading'),
    evalError: $('eval-error'),
    evalResults: $('eval-results'),
    evalMeta: $('eval-meta'),
    metricsTbody: $('metrics-tbody'),
    evalArtifactsList: $('eval-artifacts-list'),
    evalRawOutput: $('eval-raw-output'),
    evalNotReady: $('eval-not-ready'),

    // Commands
    toggleCommands: $('toggle-commands'),
    commandsDrawer: $('commands-drawer'),
    commandsContent: $('commands-content'),
    artifactsContent: $('artifacts-content'),

    // Overlay
    loadingOverlay: $('loading-overlay'),
    loadingText: $('loading-text')
};

// Initialize
async function init() {
    showOverlay('Loading NFCorpus Diagnostics...');

    try {
        // Load status
        await loadStatus();

        // Load commands and artifacts info
        await loadCommandsInfo();
        await loadArtifactsInfo();

        // Populate sample queries once we have status
        if (appState.status && appState.status.sample_queries) {
            renderSampleQueries(appState.status.sample_queries);
        }

        // Run initial evaluation during startup (cached after first run)
        if (appState.status && appState.status.nfcorpus_ready) {
            await runInitialEvaluation();
        }

        updateStatusBar('ready', 'NFCorpus Diagnostics ready');
        hideOverlay();

    } catch (error) {
        console.error('Init error:', error);
        updateStatusBar('error', 'Failed to initialize: ' + error.message);
        hideOverlay();
    }
}

// API helpers
async function apiGet(endpoint) {
    const response = await fetch(API_BASE + endpoint);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    return response.json();
}

async function apiPost(endpoint, data) {
    const response = await fetch(API_BASE + endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    return response.json();
}

// Load status
async function loadStatus() {
    try {
        const status = await apiGet('/api/status');
        appState.status = status;
        renderStatus(status);
    } catch (error) {
        console.error('Failed to load status:', error);
        updateStatusBar('error', 'Failed to connect to server');
        throw error;
    }
}

// Render status panel
function renderStatus(status) {
    // Java
    elements.javaStatus.textContent = status.java_available ? `v${status.java_version}` : 'Not found';
    elements.javaStatus.className = 'status-value ' + (status.java_available ? 'ok' : 'error');

    // Anserini
    elements.anseriniStatus.textContent = status.anserini_jar_available ? `v${status.anserini_version}` : 'Not found';
    elements.anseriniStatus.className = 'status-value ' + (status.anserini_jar_available ? 'ok' : 'error');

    // NFCorpus Index
    elements.indexStatus.textContent = status.nfcorpus_index_ready ? 'Ready' : 'Not ready';
    elements.indexStatus.className = 'status-value ' + (status.nfcorpus_index_ready ? 'ok' : 'warning');

    // Search
    elements.searchStatus.textContent = status.search_available ? 'Available' : 'Unavailable';
    elements.searchStatus.className = 'status-value ' + (status.search_available ? 'ok' : 'warning');

    // Evaluation
    elements.evalStatus.textContent = status.evaluation_available ? 'Available' : 'Unavailable';
    elements.evalStatus.className = 'status-value ' + (status.evaluation_available ? 'ok' : 'warning');

    // REST Server
    elements.restStatus.textContent = status.rest_server_ready ? `Port ${status.rest_server_port}` : 'Not started';
    elements.restStatus.className = 'status-value ' + (status.rest_server_ready ? 'ok' : 'warning');

    // Show not ready message if needed
    if (!status.nfcorpus_index_ready) {
        elements.evalNotReady.classList.remove('hidden');
    } else {
        elements.evalNotReady.classList.add('hidden');
    }
}

// Update status bar
function updateStatusBar(type, message) {
    elements.statusBar.className = 'status-bar ' + type;
    elements.statusMessage.textContent = message;
}

// Load commands info
async function loadCommandsInfo() {
    try {
        const commands = await apiGet('/api/commands');
        appState.commands = commands;
        renderCommands(commands);
    } catch (error) {
        console.error('Failed to load commands:', error);
    }
}

// Render commands
function renderCommands(commands) {
    if (!commands) {
        elements.commandsContent.innerHTML = '<p class="info-message">Commands not available</p>';
        return;
    }

    elements.commandsContent.innerHTML = Object.entries(commands).map(([key, cmd]) => `
        <div class="command-item">
            <div class="command-label">${escapeHtml(cmd.description)}</div>
            <div class="command-text">${escapeHtml(cmd.command)}</div>
        </div>
    `).join('');
}

// Load artifacts info
async function loadArtifactsInfo() {
    try {
        const artifacts = await apiGet('/api/artifacts');
        appState.artifacts = artifacts;
        renderArtifacts(artifacts);
    } catch (error) {
        console.error('Failed to load artifacts:', error);
    }
}

// Render artifacts
function renderArtifacts(artifacts) {
    if (!artifacts) {
        elements.artifactsContent.innerHTML = '<p class="info-message">Artifacts not available</p>';
        return;
    }

    const items = [
        { label: 'Cache Directory', path: artifacts.cache_dir },
        { label: 'Runs Directory', path: artifacts.runs_dir },
        { label: 'Logs Directory', path: artifacts.logs_dir },
        { label: 'NFCorpus Index', path: artifacts.nfcorpus_index },
        { label: 'Last Run File', path: artifacts.last_run_file }
    ];

    elements.artifactsContent.innerHTML = items.map(item => `
        <div class="artifact-item">
            <div class="artifact-label">${escapeHtml(item.label)}</div>
            <div class="artifact-path">${escapeHtml(item.path || 'Not generated yet')}</div>
        </div>
    `).join('');
}

// Render sample queries
function renderSampleQueries(queries) {
    if (!queries || queries.length === 0) {
        elements.sampleList.innerHTML = '<span class="info-message">No sample queries available</span>';
        return;
    }

    elements.sampleList.innerHTML = queries.map(q => `
        <button class="sample-chip" data-query="${escapeHtml(q.text)}">
            ${escapeHtml(q.text)}
        </button>
    `).join('');

    // Add click handlers
    elements.sampleList.querySelectorAll('.sample-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            elements.searchQuery.value = chip.dataset.query;
            runSearch(chip.dataset.query);
        });
    });
}

// Search
async function runSearch(query) {
    if (!query || query.trim() === '') {
        showError(elements.searchError, 'Please enter a query');
        return;
    }

    if (appState.isSearching) return;

    appState.isSearching = true;
    elements.searchBtn.disabled = true;
    elements.searchLoading.classList.remove('hidden');
    elements.searchError.classList.add('hidden');
    elements.searchResults.classList.add('hidden');

    try {
        const results = await apiGet(`/api/search?q=${encodeURIComponent(query)}&hits=10`);
        appState.lastSearchResults = results;
        renderSearchResults(query, results);
    } catch (error) {
        showError(elements.searchError, 'Search failed: ' + error.message);
    } finally {
        appState.isSearching = false;
        elements.searchBtn.disabled = false;
        elements.searchLoading.classList.add('hidden');
    }
}

// Render search results
function renderSearchResults(query, results) {
    if (results.error) {
        showError(elements.searchError, results.error);
        return;
    }

    elements.searchResults.classList.remove('hidden');

    // Parse results based on format (TREC or JSON)
    let parsedResults = [];

    if (results.candidates) {
        // JSON format from REST API
        parsedResults = results.candidates.map((c, i) => ({
            rank: i + 1,
            docid: c.docid,
            score: c.score,
            doc: c.doc || ''
        }));
    } else if (typeof results === 'object' && results.results) {
        parsedResults = results.results;
    } else {
        // Try to parse as TREC format
        elements.searchError.textContent = 'Unexpected result format';
        elements.searchError.classList.remove('hidden');
        return;
    }

    elements.resultsMeta.textContent = `${parsedResults.length} hits for "${escapeHtml(query)}"`;

    if (parsedResults.length === 0) {
        elements.resultList.innerHTML = '<li class="info-message">No results found</li>';
        return;
    }

    elements.resultList.innerHTML = parsedResults.map(r => `
        <li class="result-item">
            <div class="result-topline">
                <span class="rank">Rank ${r.rank || '?'}</span>
                ${typeof r.score === 'number' ? `<span class="score">Score ${r.score.toFixed(4)}</span>` : ''}
            </div>
            <p class="docid">Document ID: ${escapeHtml(String(r.docid || 'unknown'))}</p>
            <p class="doc-content">${escapeHtml(r.doc || 'No content available')}</p>
        </li>
    `).join('');
}

// Run initial evaluation (during startup)
async function runInitialEvaluation() {
    try {
        const result = await apiPost('/api/evaluate', {});
        if (!result.error) {
            appState.evaluationCached = true;
            renderEvaluationResults(result, true);
        }
    } catch (error) {
        console.error('Initial evaluation failed:', error);
    }
}

// Run evaluation
async function runEvaluation() {
    if (appState.isEvaluating) return;

    appState.isEvaluating = true;
    elements.runEvalBtn.disabled = true;
    elements.rerunEvalBtn.disabled = true;
    elements.evalLoading.classList.remove('hidden');
    elements.evalError.classList.add('hidden');
    elements.evalResults.classList.add('hidden');
    elements.evalCacheIndicator.classList.add('hidden');

    try {
        const result = await apiPost('/api/evaluate', {});
        if (result.error) {
            showError(elements.evalError, result.error);
        } else {
            appState.evaluationCached = false;
            renderEvaluationResults(result, false);
        }
    } catch (error) {
        showError(elements.evalError, 'Evaluation failed: ' + error.message);
    } finally {
        appState.isEvaluating = false;
        elements.runEvalBtn.disabled = false;
        elements.rerunEvalBtn.disabled = false;
        elements.evalLoading.classList.add('hidden');
    }
}

// Rerun evaluation
async function rerunEvaluation() {
    if (appState.isEvaluating) return;

    appState.isEvaluating = true;
    elements.runEvalBtn.disabled = true;
    elements.rerunEvalBtn.disabled = true;
    elements.evalLoading.classList.remove('hidden');
    elements.evalCacheIndicator.classList.add('hidden');

    try {
        const result = await apiPost('/api/evaluate/rerun', {});
        if (result.error) {
            showError(elements.evalError, result.error);
        } else {
            appState.evaluationCached = false;
            renderEvaluationResults(result, false);
        }
    } catch (error) {
        showError(elements.evalError, 'Rerun failed: ' + error.message);
    } finally {
        appState.isEvaluating = false;
        elements.runEvalBtn.disabled = false;
        elements.rerunEvalBtn.disabled = false;
        elements.evalLoading.classList.add('hidden');
    }
}

// Render evaluation results
function renderEvaluationResults(result, cached) {
    elements.evalResults.classList.remove('hidden');

    const cachedText = cached ? ' <span class="cache-indicator">(Cached from setup)</span>' : '';
    elements.evalMeta.innerHTML = `BM25 Evaluation Results${cachedText}`;

    if (cached) {
        elements.evalCacheIndicator.classList.remove('hidden');
    }

    // Render metrics table
    const metrics = result.metrics || {};
    const metricNames = {
        'map': 'MAP',
        'ndcg_cut.10': 'NDCG@10',
        'P.30': 'P@30',
        'recall.1000': 'Recall@1000'
    };

    if (Object.keys(metrics).length === 0) {
        elements.metricsTbody.innerHTML = '<tr><td colspan="5" class="info-message">No metrics computed</td></tr>';
    } else {
        elements.metricsTbody.innerHTML = Object.entries(metrics).map(([key, data]) => {
            const name = metricNames[key] || key;
            const observed = data.observed || 'N/A';
            const expected = data.expected || 'N/A';
            const delta = data.delta || '-';
            const status = data.status || 'unknown';

            return `
                <tr>
                    <td>${escapeHtml(name)}</td>
                    <td>${escapeHtml(observed)}</td>
                    <td>${escapeHtml(expected)}</td>
                    <td>${escapeHtml(delta)}</td>
                    <td class="status-${status}">${formatStatus(status)}</td>
                </tr>
            `;
        }).join('');
    }

    // Render artifacts
    const artifacts = [
        { label: 'Run File', path: result.run_file }
    ];
    elements.evalArtifactsList.innerHTML = artifacts.map(a => `
        <div class="artifact-item">
            <div class="artifact-label">${escapeHtml(a.label)}</div>
            <div class="artifact-path">${escapeHtml(a.path || 'N/A')}</div>
        </div>
    `).join('');

    // Show raw output
    if (result.eval_output) {
        elements.evalRawOutput.parentElement.classList.remove('hidden');
        elements.evalRawOutput.textContent = result.eval_output;
    } else {
        elements.evalRawOutput.parentElement.classList.add('hidden');
    }
}

// Format status
function formatStatus(status) {
    const labels = {
        'pass': 'PASS',
        'close': 'CLOSE',
        'fail': 'FAIL',
        'unknown': 'Unknown',
        'no_expected': 'No expected'
    };
    return labels[status] || status;
}

// Show error
function showError(element, message) {
    element.textContent = message;
    element.classList.remove('hidden');
}

// Show overlay
function showOverlay(text) {
    elements.loadingText.textContent = text;
    elements.loadingOverlay.classList.remove('hidden');
}

// Hide overlay
function hideOverlay() {
    elements.loadingOverlay.classList.add('hidden');
}

// Escape HTML
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Event listeners
elements.searchBtn.addEventListener('click', () => runSearch(elements.searchQuery.value));
elements.clearBtn.addEventListener('click', () => {
    elements.searchQuery.value = '';
    elements.searchResults.classList.add('hidden');
    appState.lastSearchResults = null;
});

elements.searchQuery.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        runSearch(elements.searchQuery.value);
    }
});

elements.runEvalBtn.addEventListener('click', runEvaluation);
elements.rerunEvalBtn.addEventListener('click', rerunEvaluation);

elements.toggleCommands.addEventListener('click', () => {
    const drawer = elements.commandsDrawer;
    const button = elements.toggleCommands;
    if (drawer.classList.contains('hidden')) {
        drawer.classList.remove('hidden');
        button.textContent = 'Hide Commands';
    } else {
        drawer.classList.add('hidden');
        button.textContent = 'Show Commands';
    }
});

// Start
init();