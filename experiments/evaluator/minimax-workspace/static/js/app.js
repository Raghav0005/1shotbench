// Anserini Prebuilt Index Evaluator - Frontend JavaScript

const API_BASE = window.location.origin;

let state = {
    indexes: [],
    topics: [],
    selectedIndex: null,
    selectedTopics: null,
    selectedQrels: null,
    selectedMetric: null,
    availableMetrics: [],
    isEvaluating: false,
    results: null
};

// DOM elements
const elements = {
    statusText: document.getElementById('status-text'),
    indexList: document.getElementById('index-list'),
    indexFilter: document.getElementById('index-filter'),
    showEvaluableOnly: document.getElementById('show-evaluable-only'),
    evalPanel: document.getElementById('eval-panel'),
    selectedIndex: document.getElementById('selected-index'),
    selectedTopics: document.getElementById('selected-topics'),
    selectedQrels: document.getElementById('selected-qrels'),
    metricSelect: document.getElementById('metric-select'),
    runBtn: document.getElementById('run-btn'),
    resultsSection: document.getElementById('results-section'),
    resultsContent: document.getElementById('results-content'),
    runFiles: document.getElementById('run-files'),
    loadingOverlay: document.getElementById('loading-overlay'),
    loadingText: document.getElementById('loading-text'),
    anseriniVersion: document.getElementById('anserini-version')
};

// Initialize
async function init() {
    updateStatus('Loading...', null);
    
    try {
        // Check health
        const health = await fetchAPI('/api/health');
        if (!health.jar_exists) {
            updateStatus('Error: Anserini jar not found at ' + health.jar_path, 'error');
            return;
        }
        updateStatus('Ready - Connected to Anserini fatjar', 'ok');
        
        // Load indexes and topics in parallel
        const [indexes, topics] = await Promise.all([
            fetchAPI('/api/indexes'),
            fetchAPI('/api/topics')
        ]);
        
        state.indexes = indexes;
        state.topics = topics;
        
        renderIndexList();
        await loadRunFiles();
        
        // Anserini version placeholder
        elements.anseriniVersion.textContent = 'v2.1.1';
        
    } catch (error) {
        console.error('Init error:', error);
        updateStatus('Error loading data: ' + error.message, 'error');
    }
}

// Fetch helper
async function fetchAPI(endpoint, options = {}) {
    const response = await fetch(API_BASE + endpoint, options);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    return response.json();
}

// Update status bar
function updateStatus(text, status) {
    elements.statusText.textContent = text;
    const statusBar = document.getElementById('status-bar');
    statusBar.className = 'status-bar';
    if (status) {
        statusBar.classList.add(status);
    }
}

// Show/hide loading overlay
function setLoading(show, text = 'Running evaluation...') {
    elements.loadingOverlay.classList.toggle('hidden', !show);
    elements.loadingText.textContent = text;
}

// Render index list
function renderIndexList() {
    const filter = elements.indexFilter.value.toLowerCase();
    const showEvaluableOnly = elements.showEvaluableOnly.checked;
    
    const filtered = state.indexes.filter(idx => {
        // Filter by text
        if (filter && !idx.name.toLowerCase().includes(filter)) {
            return false;
        }
        // Filter by evaluable
        if (showEvaluableOnly && !idx.evaluable) {
            return false;
        }
        return true;
    });
    
    if (filtered.length === 0) {
        elements.indexList.innerHTML = '<div class="loading">No indexes match your filter</div>';
        return;
    }
    
    elements.indexList.innerHTML = filtered.map(idx => {
        const isSelected = state.selectedIndex && state.selectedIndex.name === idx.name;
        const classes = ['index-item'];
        if (isSelected) classes.push('selected');
        if (idx.evaluable) {
            classes.push('evaluable');
        } else {
            classes.push('catalog-only');
        }
        
        return `
            <div class="${classes.join(' ')}" data-index="${idx.name}">
                <div class="index-name">
                    ${escapeHtml(idx.name)}
                    <span class="index-type">${escapeHtml(idx.type || 'unknown')}</span>
                    <span class="index-badge ${idx.evaluable ? 'evaluable' : 'catalog-only'}">
                        ${idx.evaluable ? 'Evaluable' : 'Catalog'}
                    </span>
                </div>
                ${idx.description ? `<div class="index-description">${escapeHtml(idx.description)}</div>` : ''}
                ${idx.evaluable ? `
                    <div class="index-paired">
                        Topics: <strong>${escapeHtml(idx.topics)}</strong> | 
                        Qrels: <strong>${escapeHtml(idx.qrels)}</strong>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
    
    // Add click handlers
    elements.indexList.querySelectorAll('.index-item').forEach(item => {
        item.addEventListener('click', () => selectIndex(item.dataset.index));
    });
}

// Select an index
function selectIndex(indexName) {
    const index = state.indexes.find(i => i.name === indexName);
    if (!index) return;
    
    state.selectedIndex = index;
    
    if (index.evaluable) {
        state.selectedTopics = index.topics;
        state.selectedQrels = index.qrels;
        state.availableMetrics = index.available_metrics || [];
        
        // Show evaluation panel
        elements.evalPanel.classList.remove('hidden');
        elements.selectedIndex.textContent = index.name;
        elements.selectedTopics.textContent = index.topics;
        elements.selectedQrels.textContent = index.qrels;
        
        // Populate metrics
        renderMetrics();
    } else {
        elements.evalPanel.classList.add('hidden');
        state.selectedTopics = null;
        state.selectedQrels = null;
        state.availableMetrics = [];
    }
    
    // Clear previous results
    state.results = null;
    elements.resultsSection.classList.add('hidden');
    
    renderIndexList();
}

// Render metrics dropdown
function renderMetrics() {
    elements.metricSelect.innerHTML = '<option value="">Select metric...</option>';
    
    state.availableMetrics.forEach(metric => {
        const option = document.createElement('option');
        option.value = metric.id;
        option.textContent = metric.label;
        elements.metricSelect.appendChild(option);
    });
    
    // Select nDCG@10 or Recall@1000 by default if available
    const preferredMetrics = ['ndcg_cut.10', 'recall.1000'];
    for (const preferred of preferredMetrics) {
        const option = elements.metricSelect.querySelector(`option[value="${preferred}"]`);
        if (option) {
            option.selected = true;
            state.selectedMetric = preferred;
            break;
        }
    }
    
    updateRunButton();
}

// Update run button state
function updateRunButton() {
    const canRun = state.selectedIndex && 
                   state.selectedIndex.evaluable && 
                   state.selectedMetric &&
                   !state.isEvaluating;
    elements.runBtn.disabled = !canRun;
}

// Run evaluation
async function runEvaluation() {
    if (!state.selectedIndex || !state.selectedMetric) return;
    
    state.isEvaluating = true;
    updateRunButton();
    setLoading(true, 'Running retrieval and evaluation...');
    
    try {
        const response = await fetchAPI('/api/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                index: state.selectedIndex.name,
                topics: state.selectedTopics,
                qrels: state.selectedQrels,
                metric: state.selectedMetric
            })
        });
        
        state.results = response;
        elements.resultsSection.classList.remove('hidden');
        renderResults();
        await loadRunFiles();
        
    } catch (error) {
        console.error('Evaluation error:', error);
        showError('Evaluation failed: ' + error.message);
    } finally {
        state.isEvaluating = false;
        updateRunButton();
        setLoading(false);
    }
}

// Render results
function renderResults() {
    if (!state.results) {
        elements.resultsContent.innerHTML = '<div class="loading">No results</div>';
        return;
    }
    
    if (state.results.error) {
        showError(state.results.error);
        return;
    }
    
    elements.resultsContent.innerHTML = `
        <div class="result-score">${escapeHtml(state.results.score || 'N/A')}</div>
        <div class="result-metric">${escapeHtml(state.results.metric)}</div>
        <div class="result-meta">
            <div class="meta-item">
                <span class="meta-label">Index</span>
                <span class="meta-value">${escapeHtml(state.results.index)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Topics</span>
                <span class="meta-value">${escapeHtml(state.results.topics)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Qrels</span>
                <span class="meta-value">${escapeHtml(state.results.qrels)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Run File</span>
                <span class="meta-value">${escapeHtml(state.results.run_file)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Metric</span>
                <span class="meta-value">${escapeHtml(state.results.metric)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Score</span>
                <span class="meta-value">${escapeHtml(state.results.score)}</span>
            </div>
        </div>
    `;
}

// Show error message
function showError(message) {
    elements.resultsContent.innerHTML = `
        <div class="error-message">${escapeHtml(message)}</div>
    `;
    elements.resultsSection.classList.remove('hidden');
}

// Load run files list
async function loadRunFiles() {
    try {
        const runs = await fetchAPI('/api/runs');
        
        if (runs.length === 0) {
            elements.runFiles.innerHTML = '<div class="loading">No run files yet</div>';
            return;
        }
        
        elements.runFiles.innerHTML = runs.map(run => `
            <div class="run-file-item">
                <span class="run-file-name">${escapeHtml(run.name)}</span>
                <span class="run-file-meta">${formatFileSize(run.size)} - ${formatDate(run.modified)}</span>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading runs:', error);
        elements.runFiles.innerHTML = '<div class="loading">Error loading run files</div>';
    }
}

// Utility: escape HTML
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Utility: format file size
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Utility: format date
function formatDate(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch {
        return isoString;
    }
}

// Event listeners
elements.indexFilter.addEventListener('input', renderIndexList);
elements.showEvaluableOnly.addEventListener('change', renderIndexList);

elements.metricSelect.addEventListener('change', (e) => {
    state.selectedMetric = e.target.value || null;
    updateRunButton();
});

elements.runBtn.addEventListener('click', runEvaluation);

// Start
init();