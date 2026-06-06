(function() {
    const state = {
        catalog: [],
        selectedIndex: null,
        selectedPairing: null,
        selectedMetric: null,
        runs: [],
    };

    async function loadCatalog() {
        try {
            const res = await fetch('/api/catalog');
            const data = await res.json();
            if (data.error) {
                showCatalogError(data.error);
                return;
            }
            state.catalog = data.catalog || [];
            renderCatalog();
            // Auto-select CACM if available
            const cacm = state.catalog.find(i => i.name === 'cacm' && i.evaluable);
            if (cacm) {
                selectIndex(cacm);
            }
        } catch (e) {
            showCatalogError(e.message);
        }
    }

    function showCatalogError(msg) {
        document.getElementById('indexList').innerHTML = `<div class="error">Failed to load catalog: ${escapeHtml(msg)}</div>`;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function renderCatalog() {
        const filter = document.getElementById('searchInput').value.toLowerCase();
        const list = document.getElementById('indexList');
        const items = state.catalog.filter(idx =>
            (idx.name || '').toLowerCase().includes(filter) ||
            (idx.description || '').toLowerCase().includes(filter)
        );

        if (items.length === 0) {
            list.innerHTML = '<div class="index-item">No indexes match your search.</div>';
            return;
        }

        list.innerHTML = items.map(idx => {
            const isSelected = state.selectedIndex && state.selectedIndex.name === idx.name;
            const cls = ['index-item', isSelected ? 'selected' : '', idx.evaluable ? '' : 'catalog-only'].join(' ');
            const badge = idx.evaluable
                ? '<span class="index-badge badge-evaluable">Evaluable</span>'
                : '<span class="index-badge badge-catalog">Catalog-only</span>';
            const meta = [
                idx.type,
                idx.documents != null ? `${idx.documents.toLocaleString()} docs` : null,
                idx.description,
            ].filter(Boolean).join(' · ');
            return `<div class="${cls}" data-name="${escapeHtml(idx.name)}" onclick="window.onIndexClick('${escapeHtml(idx.name)}')">
                <div style="flex:1">
                    <div class="index-name">${escapeHtml(idx.name)}</div>
                    <div class="index-meta">${escapeHtml(meta)}</div>
                </div>
                ${badge}
            </div>`;
        }).join('');
    }

    window.onIndexClick = function(name) {
        const idx = state.catalog.find(i => i.name === name);
        if (!idx) return;
        selectIndex(idx);
    };

    function selectIndex(idx) {
        state.selectedIndex = idx;
        state.selectedPairing = null;
        state.selectedMetric = null;
        renderCatalog();
        renderEvalPanel();
    }

    function renderEvalPanel() {
        const panel = document.getElementById('evalPanel');
        if (!state.selectedIndex) {
            panel.innerHTML = '<p class="pending">Select an evaluable index to begin.</p>';
            return;
        }
        const idx = state.selectedIndex;
        if (!idx.evaluable) {
            panel.innerHTML = `<p class="pending">${escapeHtml(idx.name)} is catalog-only and does not have a discovered topics/qrels pairing.</p>`;
            return;
        }

        const pairings = idx.pairings || [];
        const pairingOptions = pairings.map((p, i) =>
            `<option value="${i}">${escapeHtml(p.topic_key)} → ${escapeHtml(p.eval_key)}</option>`
        ).join('');

        let metricOptions = '';
        if (pairings.length > 0) {
            const first = pairings[0];
            metricOptions = Object.keys(first.metrics).map(m =>
                `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`
            ).join('');
        }

        panel.innerHTML = `
            <div class="form-row">
                <label>Selected Index</label>
                <input type="text" value="${escapeHtml(idx.name)}" disabled>
            </div>
            <div class="form-row">
                <label>Topics / Qrels Pairing</label>
                <select id="pairingSelect">${pairingOptions}</select>
            </div>
            <div class="form-row">
                <label>Metric</label>
                <select id="metricSelect">${metricOptions}</select>
            </div>
            <button id="runBtn">Run Evaluation</button>
            <div id="evalError"></div>
        `;

        const pairingSel = document.getElementById('pairingSelect');
        const metricSel = document.getElementById('metricSelect');

        function updateMetrics() {
            const p = pairings[parseInt(pairingSel.value, 10)];
            state.selectedPairing = p;
            if (p) {
                metricSel.innerHTML = Object.keys(p.metrics).map(m =>
                    `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`
                ).join('');
            }
        }

        pairingSel.addEventListener('change', updateMetrics);
        updateMetrics();

        document.getElementById('runBtn').addEventListener('click', async () => {
            const p = pairings[parseInt(pairingSel.value, 10)];
            const m = metricSel.value;
            if (!p || !m) return;
            await runEvaluation(idx.name, p, m);
        });
    }

    async function runEvaluation(indexName, pairing, metricName) {
        const btn = document.getElementById('runBtn');
        const errDiv = document.getElementById('evalError');
        btn.disabled = true;
        errDiv.innerHTML = '';
        document.getElementById('resultsPanel').innerHTML = '<p class="pending">Running retrieval and evaluation...</p>';

        try {
            const res = await fetch('/api/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    index: indexName,
                    topic_key: pairing.topic_key,
                    eval_key: pairing.eval_key,
                    metric: metricName,
                    condition: pairing.condition || 'bm25',
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                errDiv.innerHTML = `<div class="error">Evaluation failed: ${escapeHtml(data.error || 'Unknown error')}</div>`;
                document.getElementById('resultsPanel').innerHTML = '<p class="pending">No evaluation run yet.</p>';
                return;
            }
            state.runs.unshift(data);
            renderResults(data);
        } catch (e) {
            errDiv.innerHTML = `<div class="error">Request failed: ${escapeHtml(e.message)}</div>`;
            document.getElementById('resultsPanel').innerHTML = '<p class="pending">No evaluation run yet.</p>';
        } finally {
            btn.disabled = false;
        }
    }

    function renderResults(run) {
        const panel = document.getElementById('resultsPanel');
        const scoreDisplay = run.score != null
            ? `<div class="score">${run.score.toFixed(4)}</div><div class="score-label">${escapeHtml(run.metric)}</div>`
            : `<div class="score">N/A</div><div class="score-label">${escapeHtml(run.metric)}</div>`;

        panel.innerHTML = `
            <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap">
                ${scoreDisplay}
                <div style="flex:1;min-width:200px">
                    <div class="meta-grid">
                        <div class="meta-item"><div class="meta-key">Index</div><div class="meta-value">${escapeHtml(run.index)}</div></div>
                        <div class="meta-item"><div class="meta-key">Topics</div><div class="meta-value">${escapeHtml(run.topic_key)}</div></div>
                        <div class="meta-item"><div class="meta-key">Qrels</div><div class="meta-value">${escapeHtml(run.eval_key)}</div></div>
                        <div class="meta-item"><div class="meta-key">Metric</div><div class="meta-value">${escapeHtml(run.metric)}</div></div>
                        <div class="meta-item"><div class="meta-key">Elapsed</div><div class="meta-value">${run.elapsed_seconds}s</div></div>
                        <div class="meta-item"><div class="meta-key">Run File</div><div class="meta-value">${escapeHtml(run.run_file)}</div></div>
                        <div class="meta-item"><div class="meta-key">Eval File</div><div class="meta-value">${escapeHtml(run.eval_file)}</div></div>
                    </div>
                </div>
            </div>
            <details style="margin-top:12px">
                <summary>Evaluation output</summary>
                <pre>${escapeHtml(run.eval_output || '')}</pre>
            </details>
        `;
    }

    document.getElementById('searchInput').addEventListener('input', renderCatalog);

    loadCatalog();
})();
