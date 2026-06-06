'use strict';

const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const { execFile, spawnSync } = require('child_process');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ─── Serve generated run/eval files ──────────────────────────────────────────
const RUNS_DIR = path.join(__dirname, 'runs');
if (!fs.existsSync(RUNS_DIR)) fs.mkdirSync(RUNS_DIR, { recursive: true });
app.use('/runs', express.static(RUNS_DIR));

// ─── Evaluable index pairings ─────────────────────────────────────────────────
//
// These are the indexes that can be evaluated end-to-end without large downloads.
// CACM is the canonical small end-to-end dataset: its prebuilt index, topics,
// and qrels are all bundled in Anserini and download automatically (<3 MB).
//
// The qrelsArg is passed directly to TrecEval as the qrels/collection argument.
// The topicsArg is passed as -topics to SearchCollection.
// The metricFlag maps to -m <flag> in TrecEval.
// The metricId is the key in the TrecEval output line.
//
const EVALUABLE_PAIRINGS = {
  cacm: {
    label: 'CACM',
    description: 'Cranfield-style CACM corpus: 3,204 documents, 64 queries',
    topics: 'cacm',
    qrelsArg: 'cacm',
    defaultMetric: 'ndcg_cut.10',
    metrics: [
      { label: 'nDCG@10',     flag: 'ndcg_cut.10', id: 'ndcg_cut_10'  },
      { label: 'Recall@1000', flag: 'recall.1000',  id: 'recall_1000'  },
      { label: 'MAP',         flag: 'map',          id: 'map'          },
      { label: 'P@30',        flag: 'P.30',         id: 'P_30'         },
    ],
  },
};

// ─── Fatjar discovery ─────────────────────────────────────────────────────────
function findFatjar() {
  // 1. Explicit env var
  if (process.env.ANSERINI_JAR && fs.existsSync(process.env.ANSERINI_JAR)) {
    return process.env.ANSERINI_JAR;
  }

  // 2. Workspace directory (where this server.js lives)
  const wsDir = __dirname;
  const wsCandidates = fs.readdirSync(wsDir).filter(f => f.match(/anserini-.*-fatjar\.jar$/));
  if (wsCandidates.length > 0) {
    return path.join(wsDir, wsCandidates[0]);
  }

  // 3. Parent workspaces in the same project
  const searchRoots = [
    path.join(wsDir, '..'),
    path.join(wsDir, '..', '..'),
    path.join(wsDir, '..', '..', 'anserini-frontend'),
  ];
  for (const root of searchRoots) {
    if (!fs.existsSync(root)) continue;
    try {
      const entries = fs.readdirSync(root);
      for (const entry of entries) {
        const sub = path.join(root, entry);
        try {
          const files = fs.readdirSync(sub);
          const jar = files.find(f => f.match(/anserini-.*-fatjar\.jar$/));
          if (jar) return path.join(sub, jar);
        } catch {}
      }
    } catch {}
  }

  // 4. System-wide search under common dev dirs
  const homeDev = path.join(require('os').homedir(), 'dev');
  if (fs.existsSync(homeDev)) {
    try {
      const result = spawnSync('find', [homeDev, '-name', 'anserini-*-fatjar.jar', '-maxdepth', '6'], {
        encoding: 'utf8', timeout: 5000,
      });
      if (result.stdout) {
        const lines = result.stdout.trim().split('\n').filter(Boolean);
        if (lines.length > 0) return lines[0];
      }
    } catch {}
  }

  return null;
}

let ANSERINI_JAR = findFatjar();

// ─── Java version check ───────────────────────────────────────────────────────
function getJavaVersion() {
  try {
    const result = spawnSync('java', ['-version'], { encoding: 'utf8', timeout: 5000 });
    const output = result.stderr || result.stdout || '';
    const match = output.match(/version "([^"]+)"/);
    return match ? match[1] : output.split('\n')[0];
  } catch {
    return null;
  }
}

// ─── Run a Java command with a timeout ────────────────────────────────────────
async function runJava(args, { timeout = 120000 } = {}) {
  if (!ANSERINI_JAR) throw new Error('Anserini fatjar not found. Set ANSERINI_JAR env var or place the jar in the app directory.');
  return execFileAsync('java', ['-cp', ANSERINI_JAR, ...args], { timeout, maxBuffer: 20 * 1024 * 1024 });
}

// ─── API: /api/status ─────────────────────────────────────────────────────────
app.get('/api/status', (req, res) => {
  // Re-discover jar on each call in case it was downloaded after startup
  if (!ANSERINI_JAR || !fs.existsSync(ANSERINI_JAR)) {
    ANSERINI_JAR = findFatjar();
  }
  res.json({
    jarFound: Boolean(ANSERINI_JAR && fs.existsSync(ANSERINI_JAR)),
    jarPath: ANSERINI_JAR || null,
    javaVersion: getJavaVersion(),
    evaluablePairings: Object.keys(EVALUABLE_PAIRINGS),
  });
});

// ─── API: /api/indexes ────────────────────────────────────────────────────────
app.get('/api/indexes', async (req, res) => {
  try {
    const { stdout } = await runJava(
      ['io.anserini.cli.PrebuiltIndexRegistry', '--list'],
      { timeout: 30000 },
    );
    let indexes;
    try {
      indexes = JSON.parse(stdout);
    } catch {
      return res.status(500).json({ error: 'Failed to parse PrebuiltIndexRegistry output', raw: stdout.slice(0, 500) });
    }

    // Annotate each index with evaluability info
    const annotated = indexes.map(idx => {
      const pairing = EVALUABLE_PAIRINGS[idx.name];
      return {
        name: idx.name,
        type: idx.type || 'unknown',
        description: idx.description || '',
        documents: idx.documents ?? null,
        size: idx.size ?? null,
        evaluable: Boolean(pairing),
        pairing: pairing
          ? {
              topics: pairing.topics,
              qrelsArg: pairing.qrelsArg,
              defaultMetric: pairing.defaultMetric,
              metrics: pairing.metrics,
            }
          : null,
      };
    });

    res.json({ indexes: annotated, total: annotated.length });
  } catch (err) {
    console.error('indexes error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ─── API: /api/evaluate ───────────────────────────────────────────────────────
//
// POST body: { indexName: "cacm", metricFlag: "ndcg_cut.10" }
//
// Runs:
//   java SearchCollection -index <name> -topics <topics> -output <runFile> -hits 1000 -bm25
//   java TrecEval -c -m <metric> <qrelsArg> <runFile>
//
// Returns run metadata and the parsed score.
//
app.post('/api/evaluate', async (req, res) => {
  const { indexName, metricFlag } = req.body;

  if (!indexName) return res.status(400).json({ error: 'indexName is required' });

  const pairing = EVALUABLE_PAIRINGS[indexName];
  if (!pairing) {
    return res.status(400).json({
      error: `No topic/qrels pairing found for index "${indexName}". This index is catalog-only.`,
    });
  }

  const metric = pairing.metrics.find(m => m.flag === metricFlag) || pairing.metrics[0];
  const ts = Date.now();
  const safeMetric = metric.flag.replace('.', '_').replace('/', '_');
  const runFileName = `run.${indexName}.${safeMetric}.${ts}.txt`;
  const evalFileName = `eval.${indexName}.${safeMetric}.${ts}.txt`;
  const runFilePath = path.join(RUNS_DIR, runFileName);
  const evalFilePath = path.join(RUNS_DIR, evalFileName);

  const startTime = Date.now();

  try {
    // ── Step 1: Retrieval ────────────────────────────────────────────────────
    console.log(`[eval] SearchCollection: index=${indexName} topics=${pairing.topics} output=${runFileName}`);
    const searchArgs = [
      'io.anserini.search.SearchCollection',
      '-threads', '4',
      '-index', indexName,
      '-topics', pairing.topics,
      '-output', runFilePath,
      '-hits', '1000',
      '-bm25',
    ];
    let searchStdout = '';
    let searchStderr = '';
    try {
      const r = await runJava(searchArgs, { timeout: 180000 });
      searchStdout = r.stdout || '';
      searchStderr = r.stderr || '';
    } catch (err) {
      searchStdout = err.stdout || '';
      searchStderr = err.stderr || '';
      // SearchCollection writes progress to stderr; non-zero exit might still succeed
      if (!fs.existsSync(runFilePath)) {
        return res.status(500).json({
          error: `SearchCollection failed: ${err.message}`,
          stderr: searchStderr.slice(-2000),
        });
      }
    }

    // ── Step 2: Evaluation ───────────────────────────────────────────────────
    console.log(`[eval] TrecEval: metric=${metric.flag} qrels=${pairing.qrelsArg}`);
    const evalArgs = [
      'io.anserini.eval.TrecEval',
      '-c',
      '-m', metric.flag,
      pairing.qrelsArg,
      runFilePath,
    ];
    let evalOutput = '';
    try {
      const r = await runJava(evalArgs, { timeout: 60000 });
      evalOutput = (r.stdout || '') + (r.stderr || '');
    } catch (err) {
      evalOutput = (err.stdout || '') + (err.stderr || '');
      if (!evalOutput.trim()) {
        return res.status(500).json({ error: `TrecEval failed: ${err.message}` });
      }
    }

    // Save eval output
    fs.writeFileSync(evalFilePath, evalOutput, 'utf8');

    // ── Parse score ──────────────────────────────────────────────────────────
    // TrecEval output format:  <metric_id>\t<subset>\t<score>
    // e.g.: "ndcg_cut_10\tall\t0.4543"
    const scorePattern = new RegExp(`^${metric.id}\\s+all\\s+(\\S+)`, 'm');
    const match = evalOutput.match(scorePattern);
    const score = match ? parseFloat(match[1]) : null;

    const elapsed = Date.now() - startTime;

    res.json({
      status: 'success',
      score,
      metricLabel: metric.label,
      metricFlag: metric.flag,
      metricId: metric.id,
      indexName,
      topics: pairing.topics,
      qrelsArg: pairing.qrelsArg,
      runFile: `/runs/${runFileName}`,
      evalFile: `/runs/${evalFileName}`,
      evalOutput: evalOutput.trim(),
      elapsed,
      startedAt: new Date(startTime).toISOString(),
    });
  } catch (err) {
    console.error('[eval] error:', err.message);
    res.status(500).json({ error: err.message, stack: err.stack });
  }
});

// ─── API: /api/pairings ───────────────────────────────────────────────────────
app.get('/api/pairings', (req, res) => {
  const out = {};
  for (const [key, val] of Object.entries(EVALUABLE_PAIRINGS)) {
    out[key] = {
      label: val.label,
      description: val.description,
      topics: val.topics,
      qrelsArg: val.qrelsArg,
      defaultMetric: val.defaultMetric,
      metrics: val.metrics,
    };
  }
  res.json(out);
});

// ─── Start ────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3579;
app.listen(PORT, () => {
  console.log(`Anserini Evaluator running at http://localhost:${PORT}`);
  if (ANSERINI_JAR) {
    console.log(`Using fatjar: ${ANSERINI_JAR}`);
  } else {
    console.warn('WARNING: Anserini fatjar not found. Set ANSERINI_JAR env var.');
  }
});
