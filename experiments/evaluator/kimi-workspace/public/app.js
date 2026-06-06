(async () => {
  const indexList = document.getElementById('index-list');
  const indexSearch = document.getElementById('index-search');
  const healthStatus = document.getElementById('health-status');
  const evaluationEmpty = document.getElementById('evaluation-empty');
  const evaluationForm = document.getElementById('evaluation-form');
  const selectedIndexName = document.getElementById('selected-index-name');
  const topicSelect = document.getElementById('topic-select');
  const metricSelect = document.getElementById('metric-select');
  const evalKeyDisplay = document.getElementById('eval-key-display');
  const runBtn = document.getElementById('run-evaluation');
  const loadingEl = document.getElementById('evaluation-loading');
  const resultEl = document.getElementById('evaluation-result');
  const errorEl = document.getElementById('evaluation-error');

  let indexes = [];
  let selectedIndex = null;
  let evaluableData = null;

  // Health check
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    if (data.ok) {
      healthStatus.textContent = `Java OK • ${data.java}`;
      healthStatus.classList.add('ok');
    } else {
      healthStatus.textContent = 'Java or fatjar unavailable';
      healthStatus.classList.add('error');
    }
  } catch (e) {
    healthStatus.textContent = 'Server unreachable';
    healthStatus.classList.add('error');
  }

  // Load indexes
  try {
    const res = await fetch('/api/indexes');
    indexes = await res.json();
    renderIndexes(indexes);
    // Preselect CACM if available
    const cacm = indexes.find(i => i.name === 'cacm');
    if (cacm) selectIndex(cacm);
  } catch (e) {
    indexList.textContent = 'Failed to load indexes: ' + e.message;
  }

  indexSearch.addEventListener('input', () => {
    const q = indexSearch.value.toLowerCase();
    renderIndexes(indexes.filter(i =>
      i.name.toLowerCase().includes(q) ||
      (i.description || '').toLowerCase().includes(q)
    ));
  });

  function renderIndexes(list) {
    indexList.innerHTML = '';
    if (list.length === 0) {
      indexList.textContent = 'No indexes found.';
      return;
    }
    for (const idx of list) {
      const card = document.createElement('div');
      card.className = 'index-card' + (idx.evaluable ? '' : ' catalog-only');
      if (selectedIndex && selectedIndex.name === idx.name) card.classList.add('selected');

      const badge = document.createElement('span');
      badge.className = 'badge ' + (idx.evaluable ? 'evaluable' : 'catalog');
      badge.textContent = idx.evaluable ? 'Evaluable' : 'Catalog only';

      const title = document.createElement('h3');
      title.textContent = idx.name;

      const desc = document.createElement('p');
      desc.textContent = idx.description || '';

      const meta = document.createElement('div');
      meta.className = 'meta';
      const parts = [];
      if (idx.type) parts.push(`Type: ${idx.type}`);
      if (idx.documents != null) parts.push(`Docs: ${idx.documents.toLocaleString()}`);
      if (idx.size != null) parts.push(`Size: ${(idx.size / 1024 / 1024).toFixed(1)} MB`);
      meta.textContent = parts.join(' • ');

      card.appendChild(badge);
      card.appendChild(title);
      card.appendChild(desc);
      card.appendChild(meta);

      if (idx.evaluable) {
        card.addEventListener('click', () => selectIndex(idx));
      }

      indexList.appendChild(card);
    }
  }

  async function selectIndex(idx) {
    selectedIndex = idx;
    renderIndexes(indexes);

    evaluationEmpty.classList.add('hidden');
    evaluationForm.classList.remove('hidden');
    resultEl.classList.add('hidden');
    errorEl.classList.add('hidden');
    selectedIndexName.textContent = idx.name;

    // Load evaluable details
    try {
      const res = await fetch(`/api/evaluable/${encodeURIComponent(idx.name)}`);
      evaluableData = await res.json();
      populateTopics();
    } catch (e) {
      evaluableData = { topics: [] };
      topicSelect.innerHTML = '<option>Error loading topics</option>';
    }
  }

  function populateTopics() {
    topicSelect.innerHTML = '';
    if (!evaluableData || !evaluableData.topics || evaluableData.topics.length === 0) {
      topicSelect.innerHTML = '<option>No topics available</option>';
      metricSelect.innerHTML = '<option>No metrics available</option>';
      evalKeyDisplay.textContent = '—';
      return;
    }
    for (const t of evaluableData.topics) {
      const opt = document.createElement('option');
      opt.value = t.topic;
      opt.textContent = t.topic;
      opt.dataset.eval = t.eval;
      opt.dataset.metrics = JSON.stringify(t.metrics);
      topicSelect.appendChild(opt);
    }
    updateMetrics();
  }

  topicSelect.addEventListener('change', updateMetrics);

  function updateMetrics() {
    const opt = topicSelect.selectedOptions[0];
    if (!opt) return;
    evalKeyDisplay.textContent = opt.dataset.eval || '—';
    const metrics = JSON.parse(opt.dataset.metrics || '[]');
    metricSelect.innerHTML = '';

    // Map labels to trec_eval args based on known patterns
    const metricMap = {
      'nDCG@10': '-c -m ndcg_cut.10',
      'nDCG@20': '-c -m ndcg_cut.20',
      'nDCG@30': '-c -m ndcg_cut.30',
      'nDCG@100': '-c -m ndcg_cut.100',
      'Recall@100': '-c -m recall.100',
      'Recall@1000': '-c -m recall.1000',
      'R@100': '-c -m recall.100',
      'R@1K': '-c -m recall.1000',
      'MAP': '-c -m map',
      'P30': '-c -m P.30',
      'MRR@10': '-c -M 10 -m recip_rank',
      'MRR@100': '-c -M 100 -m recip_rank',
      'AP@100': '-c -l 2 -m map',
    };

    // Build available metrics with friendly labels
    const added = new Set();
    for (const m of metrics) {
      const args = metricMap[m];
      if (args && !added.has(args)) {
        added.add(args);
        const mopt = document.createElement('option');
        mopt.value = args;
        mopt.textContent = m;
        mopt.dataset.label = m;
        metricSelect.appendChild(mopt);
      }
    }
    if (metricSelect.options.length === 0) {
      metricSelect.innerHTML = '<option>No supported metrics</option>';
    }
  }

  runBtn.addEventListener('click', async () => {
    const topic = topicSelect.value;
    const evalKey = topicSelect.selectedOptions[0]?.dataset.eval;
    const metricArgs = metricSelect.value;
    const metricLabel = metricSelect.selectedOptions[0]?.dataset.label || metricArgs;

    if (!topic || !evalKey || !metricArgs || metricArgs.startsWith('No')) {
      errorEl.textContent = 'Please select a valid topic and metric.';
      errorEl.classList.remove('hidden');
      return;
    }

    runBtn.disabled = true;
    loadingEl.classList.remove('hidden');
    resultEl.classList.add('hidden');
    errorEl.classList.add('hidden');

    try {
      const res = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          index: selectedIndex.name,
          topic,
          evalKey,
          metricLabel,
          metricArgs
        })
      });
      const data = await res.json();
      loadingEl.classList.add('hidden');
      runBtn.disabled = false;

      if (!data.success) {
        errorEl.textContent = data.error || 'Evaluation failed.';
        errorEl.classList.remove('hidden');
        return;
      }

      resultEl.classList.remove('hidden');
      document.getElementById('result-score').textContent = data.score != null ? data.score.toFixed(4) : '—';
      document.getElementById('result-metric').textContent = data.metric;
      document.getElementById('meta-index').textContent = data.index;
      document.getElementById('meta-topic').textContent = data.topic;
      document.getElementById('meta-qrels').textContent = data.evalKey;
      document.getElementById('meta-metric').textContent = data.metric;
      document.getElementById('meta-status').textContent = 'Completed';
      document.getElementById('meta-elapsed').textContent = `${data.elapsedMs} ms`;
      document.getElementById('meta-runfile').textContent = data.runFile;
      document.getElementById('meta-evalfile').textContent = data.evalFile;
      document.getElementById('eval-preview').textContent = data.evalOutput;
    } catch (e) {
      loadingEl.classList.add('hidden');
      runBtn.disabled = false;
      errorEl.textContent = 'Request failed: ' + e.message;
      errorEl.classList.remove('hidden');
    }
  });
})();
