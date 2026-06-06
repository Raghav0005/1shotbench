const express = require('express');
const { execSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const WORKSPACE = __dirname;
const ANSERINI_JAR = path.join(WORKSPACE, 'anserini-2.1.1-fatjar.jar');
const RUNS_DIR = path.join(WORKSPACE, 'runs');

// Ensure runs directory exists
if (!fs.existsSync(RUNS_DIR)) fs.mkdirSync(RUNS_DIR, { recursive: true });

// Known evaluable datasets: maps index prefix/name -> { topics, qrels }
// These are confirmed working evaluation pairings
const EVALUABLE_DATASETS = {
  'cacm': {
    topics: 'cacm',
    qrels: 'cacm',
    label: 'CACM',
    metrics: ['map', 'P.30', 'ndcg_cut.10', 'recall.1000', 'P.10', 'P.20', 'P.100', 'recip_rank']
  },
};

// BEIR evaluable datasets (topics follow BEIR_V1_0_0_<name>_TEST pattern)
const BEIR_DATASETS = [
  'arguana', 'bioasq', 'climate-fever', 'cqadupstack-android', 'cqadupstack-english',
  'cqadupstack-gaming', 'cqadupstack-gis', 'cqadupstack-mathematica', 'cqadupstack-physics',
  'cqadupstack-programmers', 'cqadupstack-stats', 'cqadupstack-tex', 'cqadupstack-unix',
  'cqadupstack-webmasters', 'cqadupstack-wordpress', 'dbpedia-entity', 'fever',
  'fiqa', 'hotpotqa', 'msmarco', 'nfcorpus', 'nq', 'quora', 'robust04',
  'scidocs', 'scifact', 'signal1m', 'trec-covid', 'trec-news', 'webis-touche2020'
];

// Standard TREC evaluation metrics
const METRIC_LABELS = {
  'map': 'MAP (Mean Average Precision)',
  'P.30': 'P@30 (Precision at 30)',
  'P.10': 'P@10 (Precision at 10)',
  'P.20': 'P@20 (Precision at 20)',
  'P.100': 'P@100 (Precision at 100)',
  'ndcg_cut.10': 'nDCG@10 (Normalized Discounted Cumulative Gain at 10)',
  'recall.1000': 'Recall@1000',
  'recip_rank': 'MRR (Mean Reciprocal Rank)',
  'Rprec': 'R-Precision',
  'set_recall': 'Set Recall'
};

// Cache for registry data
let indexCache = null;
let topicsCache = null;
let evaluableCache = null;

function runAnserini(args, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    const proc = spawn('java', ['-cp', ANSERINI_JAR, ...args], {
      cwd: WORKSPACE,
      timeout: timeoutMs,
      env: { ...process.env }
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', d => stdout += d.toString());
    proc.stderr.on('data', d => stderr += d.toString());
    proc.on('close', code => {
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(`Command failed (exit ${code}): ${stderr || stdout}`));
    });
    proc.on('error', err => reject(err));
  });
}

function checkStatus() {
  try {
    execSync('java -version', { stdio: 'pipe' });
  } catch (e) {
    return { ready: false, error: 'Java 21 not found on PATH' };
  }
  if (!fs.existsSync(ANSERINI_JAR)) {
    return { ready: false, error: `Anserini fatjar not found at ${ANSERINI_JAR}` };
  }
  return { ready: true, jar: ANSERINI_JAR };
}

// Load prebuilt indexes from registry
async function loadIndexes() {
  if (indexCache) return indexCache;
  try {
    const { stdout } = await runAnserini([
      'io.anserini.cli.PrebuiltIndexRegistry', '--list'
    ]);
    indexCache = JSON.parse(stdout);
    return indexCache;
  } catch (e) {
    console.error('Failed to load index registry:', e.message);
    return [];
  }
}

// Load topics from registry
async function loadTopics() {
  if (topicsCache) return topicsCache;
  try {
    const { stdout } = await runAnserini([
      'io.anserini.cli.TopicsRegistry', '--list'
    ]);
    topicsCache = JSON.parse(stdout);
    return topicsCache;
  } catch (e) {
    console.error('Failed to load topics registry:', e.message);
    return [];
  }
}

// Determine which indexes are evaluable by checking topics registry
async function loadEvaluableMap() {
  if (evaluableCache) return evaluableCache;
  const indexes = await loadIndexes();
  const topics = await loadTopics();
  const topicSet = new Set(topics);

  evaluableCache = {};

  for (const [key, cfg] of Object.entries(EVALUABLE_DATASETS)) {
    if (topicSet.has(cfg.topics)) {
      evaluableCache[key] = cfg;
    }
  }

  // Check BEIR datasets - match inverted indexes to topics
  for (const ds of BEIR_DATASETS) {
    const topicKey = `BEIR_V1_0_0_${ds.toUpperCase().replace(/-/g, '_')}_TEST`;
    if (topicSet.has(topicKey)) {
      // Find matching inverted index
      const idxCandidates = [
        `beir-v1.0.0-${ds}.flat`,
        `beir-v1.0.0-${ds}.multifield`,
        `beir-v1.0.0-${ds}`
      ];
      for (const idxName of idxCandidates) {
        if (indexes.find(i => i.name === idxName)) {
          if (!evaluableCache[idxName]) {
            evaluableCache[idxName] = {
              topics: topicKey,
              qrels: topicKey,
              label: `BEIR ${ds}`,
              metrics: ['map', 'ndcg_cut.10', 'recall.1000', 'recip_rank', 'P.10', 'Rprec']
            };
          }
        }
      }
    }
  }

  return evaluableCache;
}

// API Routes

app.get('/api/status', (req, res) => {
  res.json(checkStatus());
});

app.get('/api/indexes', async (req, res) => {
  try {
    const indexes = await loadIndexes();
    const evalMap = await loadEvaluableMap();

    const evalIndexNames = new Set();
    for (const key of Object.keys(evalMap)) {
      // Add exact matches and any index starting with the key
      indexes.forEach(idx => {
        if (idx.name === key || idx.name.startsWith(key + '.')) {
          evalIndexNames.add(idx.name);
        }
      });
    }

    const filter = req.query.filter || '';
    const typeFilter = req.query.type || '';

    let filtered = indexes.map(idx => ({
      ...idx,
      evaluable: evalIndexNames.has(idx.name),
      evalConfig: evalIndexNames.has(idx.name) ? (evalMap[idx.name] || evalMap[idx.name.split('.')[0]]) : null
    }));

    if (filter) {
      const re = new RegExp(filter, 'i');
      filtered = filtered.filter(idx => re.test(idx.name) || re.test(idx.description || ''));
    }
    if (typeFilter) {
      filtered = filtered.filter(idx => idx.type === typeFilter);
    }

    res.json({
      total: indexes.length,
      filtered: filtered.length,
      indexes: filtered
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/topics', async (req, res) => {
  try {
    const topics = await loadTopics();
    const filter = req.query.filter || '';
    let filtered = topics;
    if (filter) {
      const re = new RegExp(filter, 'i');
      filtered = topics.filter(t => re.test(t));
    }
    res.json({ total: topics.length, topics: filtered });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/metrics', (req, res) => {
  res.json(METRIC_LABELS);
});

app.post('/api/evaluate', async (req, res) => {
  const { indexName, topicsName, metric } = req.body;

  if (!indexName || !topicsName || !metric) {
    return res.status(400).json({ error: 'Missing required fields: indexName, topicsName, metric' });
  }

  // Validate metric
  if (!METRIC_LABELS[metric]) {
    return res.status(400).json({ error: `Unsupported metric: ${metric}` });
  }

  const timestamp = Date.now();
  const runFile = path.join(RUNS_DIR, `run.${indexName}.${timestamp}.txt`);
  const evalFile = path.join(RUNS_DIR, `eval.${indexName}.${timestamp}.txt`);

  const startTime = Date.now();
  const metadata = {
    index: indexName,
    topics: topicsName,
    metric,
    metricLabel: METRIC_LABELS[metric],
    runFile,
    evalFile,
    startTime: new Date().toISOString()
  };

  try {
    // Step 1: Run retrieval
    const searchArgs = [
      'io.anserini.search.SearchCollection',
      '-threads', '1',
      '-index', indexName,
      '-topics', topicsName,
      '-output', runFile,
      '-hits', '1000',
      '-bm25'
    ];

    const searchResult = await runAnserini(searchArgs, 300000);
    metadata.searchOutput = searchResult.stderr;

    if (!fs.existsSync(runFile)) {
      return res.status(500).json({ error: 'Retrieval did not produce a run file', metadata });
    }

    metadata.runFileLines = fs.readFileSync(runFile, 'utf-8').split('\n').filter(l => l.trim()).length;

    // Step 2: Evaluate
    // Determine qrels name - try to find it from evalConfig or use topics name
    const evalMap = await loadEvaluableMap();
    let qrelsName = topicsName;
    for (const [key, cfg] of Object.entries(evalMap)) {
      if (cfg.topics === topicsName) {
        qrelsName = cfg.qrels;
        break;
      }
    }

    const evalArgs = [
      'io.anserini.eval.TrecEval',
      '-c',
      '-m', metric,
      qrelsName,
      runFile
    ];

    const evalResult = await runAnserini(evalArgs, 60000);
    metadata.evalOutput = evalResult.stdout;

    // Parse evaluation output
    const evalLines = evalResult.stdout.trim().split('\n').filter(l => l.trim());
    fs.writeFileSync(evalFile, evalResult.stdout);

    // Parse the metric score from trec_eval output
    // Format: metric_name    all    score
    const scores = {};
    for (const line of evalLines) {
      const parts = line.trim().split(/\s+/);
      if (parts.length >= 3) {
        scores[parts[0]] = parseFloat(parts[2]);
      }
    }

    const elapsed = Date.now() - startTime;
    metadata.elapsed = elapsed;
    metadata.endTime = new Date().toISOString();

    res.json({
      success: true,
      score: scores[metric] !== undefined ? scores[metric] : Object.values(scores)[0],
      scores,
      metadata
    });
  } catch (e) {
    metadata.elapsed = Date.now() - startTime;
    metadata.error = e.message;
    res.status(500).json({ error: e.message, metadata });
  }
});

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', time: new Date().toISOString() });
});

const PORT = process.env.PORT || 3456;
const server = app.listen(PORT, () => {
  console.log(`Anserini Prebuilt Index Evaluator running on http://localhost:${PORT}`);
});

module.exports = { app, server };
