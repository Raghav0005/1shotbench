const express = require('express');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const PORT = process.env.PORT || 3000;

// ── Fatjar Discovery ──────────────────────────────────────────────
function findFatjar() {
  const dir = __dirname;
  const files = fs.readdirSync(dir);
  const jar = files.find(f => /^anserini-[\d.]+-fatjar\.jar$/.test(f));
  if (!jar) return null;
  return path.join(dir, jar);
}

const ANSERINI_JAR = findFatjar();

function javaCmd(args, opts = {}) {
  return new Promise((resolve, reject) => {
    if (!ANSERINI_JAR) {
      return reject(new Error('Anserini fatjar not found. Place an anserini-*-fatjar.jar in the project root.'));
    }
    const allArgs = ['-cp', ANSERINI_JAR, ...args];
    const { timeout: timeoutSecs, ...restOpts } = opts;
    const child = execFile('java', allArgs, {
      maxBuffer: 50 * 1024 * 1024,
      timeout: (timeoutSecs || 300) * 1000,
      ...restOpts,
    }, (err, stdout, stderr) => {
      if (err) {
        reject({ error: err, stdout, stderr });
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
}

// ── Known evaluable index/topic/qrels pairings ──────────────────
// Derived from Anserini reproduction configs and CLI skill docs.
// CACM is the canonical small dataset.
const EVALUABLE_INDEXES = {
  cacm: {
    index: 'cacm',
    topics: 'cacm',
    qrels: 'cacm',
    metrics: [
      { label: 'MAP', flag: '-m map', key: 'map' },
      { label: 'P@30', flag: '-m P.30', key: 'P_30' },
      { label: 'nDCG@10', flag: '-m ndcg_cut.10', key: 'ndcg_cut_10' },
      { label: 'Recall@1000', flag: '-m recall.1000', key: 'recall_1000' },
    ],
  },
};

// ── API: Server status ──────────────────────────────────────────
app.get('/api/status', (req, res) => {
  res.json({
    fatjar: ANSERINI_JAR ? path.basename(ANSERINI_JAR) : null,
    javaAvailable: true, // if we got here, java works
  });
});

// ── API: Catalog of prebuilt inverted indexes ───────────────────
app.get('/api/catalog', async (req, res) => {
  try {
    const { stdout } = await javaCmd([
      'io.anserini.cli.PrebuiltIndexRegistry',
      '--type', 'inverted',
      '--list',
    ]);
    const indexes = JSON.parse(stdout);
    const enriched = indexes.map(idx => {
      const evalConfig = EVALUABLE_INDEXES[idx.name];
      return {
        name: idx.name,
        type: idx.type,
        description: idx.description,
        documents: idx.documents || null,
        evaluable: !!evalConfig,
        evalConfig: evalConfig || null,
      };
    });
    res.json({ indexes: enriched });
  } catch (e) {
    const msg = (e.stderr || '') + (e.error ? e.error.message : '');
    res.status(500).json({ error: 'Failed to list indexes: ' + msg });
  }
});

// ── API: Run evaluation ─────────────────────────────────────────
app.post('/api/evaluate', async (req, res) => {
  const { indexName, metricFlag, metricKey, metricLabel } = req.body;
  const config = EVALUABLE_INDEXES[indexName];
  if (!config) {
    return res.status(400).json({ error: `Index "${indexName}" is not evaluable in this application.` });
  }
  if (!metricFlag || !metricKey) {
    return res.status(400).json({ error: 'Metric not specified.' });
  }

  const runFile = path.join(os.tmpdir(), `run.${indexName}.bm25.${Date.now()}.txt`);
  const startTime = Date.now();

  try {
    // Step 1: Retrieval
    const searchArgs = [
      'io.anserini.search.SearchCollection',
      '-threads', '1',
      '-index', config.index,
      '-topics', config.topics,
      '-output', runFile,
      '-hits', '1000',
      '-bm25',
    ];
    const searchResult = await javaCmd(searchArgs, { timeout: 600 });

    // Step 2: Evaluation
    const evalArgs = [
      'io.anserini.eval.TrecEval',
      '-c',
      ...metricFlag.split(' '),
      config.qrels,
      runFile,
    ];
    const evalResult = await javaCmd(evalArgs, { timeout: 120 });

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    // Parse the evaluation score
    const evalOutput = evalResult.stdout.trim();
    const lines = evalOutput.split('\n');
    let score = null;
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      if (parts.length >= 3 && parts[0] === metricKey && parts[1] === 'all') {
        score = parseFloat(parts[2]);
      }
    }

    // Read first few lines of run file for preview
    let runPreview = '';
    try {
      const content = fs.readFileSync(runFile, 'utf-8');
      const previewLines = content.split('\n').slice(0, 20);
      runPreview = previewLines.join('\n');
    } catch (_) { /* ignore */ }

    res.json({
      success: true,
      score,
      metric: metricLabel,
      metricKey,
      index: config.index,
      topics: config.topics,
      qrels: config.qrels,
      elapsedSeconds: elapsed,
      runFilePath: runFile,
      evalOutput,
      runPreview,
      searchLog: searchResult.stderr,
    });
  } catch (e) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const stderr = e.stderr || '';
    const errorMsg = e.error ? e.error.message : String(e);
    res.status(500).json({
      success: false,
      error: errorMsg,
      stderr,
      elapsedSeconds: elapsed,
      runFilePath: runFile,
    });
  }
});

// ── Start server ────────────────────────────────────────────────
const server = app.listen(PORT, () => {
  console.log(`Anserini Prebuilt Index Evaluator running at http://localhost:${PORT}`);
  if (ANSERINI_JAR) {
    console.log(`Using fatjar: ${path.basename(ANSERINI_JAR)}`);
  } else {
    console.warn('WARNING: No Anserini fatjar found. Place anserini-*-fatjar.jar in the project root.');
  }
});

// Graceful shutdown
process.on('SIGTERM', () => server.close());
process.on('SIGINT', () => server.close());

module.exports = { app, server };
