/**
 * Anserini Prebuilt Index Evaluator — local web server.
 *
 * Endpoints:
 *   GET  /api/health             - check fatjar + Java availability
 *   GET  /api/catalog            - registry-derived index catalog (+ pairings)
 *   POST /api/evaluate           - run retrieval + evaluation for one pairing
 *   GET  /api/artifacts/:name    - serve a run or eval artifact for inspection
 *
 * All Anserini work is delegated to lib/anserini.js, which shells out to
 * `java -cp $ANSERINI_JAR ...`. No retrieval results, run files, evaluation
 * scores, or catalog entries are mocked or hardcoded.
 */

const express = require('express');
const fs = require('node:fs');
const path = require('node:path');
const anserini = require('./lib/anserini');
const catalog = require('./lib/catalog');

const PORT = parseInt(process.env.PORT || '4317', 10);
const ROOT = __dirname;
const ARTIFACTS_DIR = path.join(ROOT, 'artifacts');
fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(ROOT, 'public')));

// In-memory catalog cache (build is expensive: 17 JVM spawns ~ 1 min).
let catalogPromise = null;
function getCatalog(force = false) {
  if (force || !catalogPromise) {
    catalogPromise = catalog.buildCatalog().catch((err) => {
      catalogPromise = null;
      throw err;
    });
  }
  return catalogPromise;
}

// Warm up the catalog as soon as the server starts so the UI loads fast.
function warmCatalog() {
  getCatalog().catch((err) => {
    console.error('[catalog] warmup failed:', err.message);
  });
}

// ---------- Endpoints ----------

app.get('/api/health', async (_req, res) => {
  const javaCheck = await anserini.verifyJava();
  const jarCheck = anserini.verifyAnseriniJar();
  res.json({
    ok: javaCheck.ok && jarCheck.ok,
    java: javaCheck,
    anseriniJar: jarCheck,
  });
});

app.get('/api/catalog', async (_req, res) => {
  try {
    const data = await getCatalog();
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/catalog/refresh', async (_req, res) => {
  try {
    const data = await getCatalog(true);
    res.json({ ok: true, generatedAt: data.generatedAt });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * Body shape:
 *   {
 *     indexName: "cacm",
 *     topics:    "cacm",
 *     evalKey:   "cacm",
 *     metricLabel: "MAP",         // or "nDCG@10" / "Recall@1000" / ...
 *     metricArgs:  ["-c","-m","map"]  // optional; falls back to lookup
 *   }
 */
app.post('/api/evaluate', async (req, res) => {
  const start = Date.now();
  const { indexName, topics, evalKey, metricLabel } = req.body || {};
  let metricArgs = Array.isArray(req.body?.metricArgs) ? req.body.metricArgs : null;

  if (!indexName || !topics || !evalKey || !metricLabel) {
    res.status(400).json({
      error: 'indexName, topics, evalKey, and metricLabel are required',
    });
    return;
  }

  // Look up the pairing in the catalog so we can prefer the reproduction
  // config's per-pairing metric args when the client did not supply them.
  let resolvedPairing = null;
  try {
    const cat = await getCatalog();
    const idx = cat.indexes.find((i) => i.name === indexName);
    if (!idx) {
      res.status(400).json({ error: `Unknown index: ${indexName}` });
      return;
    }
    if (!idx.evaluable) {
      res.status(400).json({
        error: `Index ${indexName} is catalog-only: no topics/qrels pairing is registered for it.`,
      });
      return;
    }
    resolvedPairing = idx.pairings.find(
      (p) => p.topics === topics && p.evalKey === evalKey
    );
    if (!resolvedPairing) {
      res.status(400).json({
        error: `No registered pairing on ${indexName} for topics=${topics}, evalKey=${evalKey}`,
      });
      return;
    }
    if (!metricArgs) {
      const m = resolvedPairing.metrics.find((mm) => mm.label === metricLabel);
      if (!m) {
        res.status(400).json({
          error: `Metric "${metricLabel}" is not available for this pairing`,
        });
        return;
      }
      metricArgs = m.args;
    }
  } catch (err) {
    res.status(500).json({ error: `Catalog lookup failed: ${err.message}` });
    return;
  }

  // Build artifact paths. Names include a timestamp so repeated runs do not
  // clobber prior artifacts; the user can inspect them via /api/artifacts/:name.
  const safeIndex = indexName.replace(/[^A-Za-z0-9._-]/g, '_');
  const safeTopics = topics.replace(/[^A-Za-z0-9._-]/g, '_');
  const safeMetric = metricLabel.replace(/[^A-Za-z0-9._-]/g, '_');
  const stamp = new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 14);
  const runBase = `run.${safeIndex}.${safeTopics}.bm25.${stamp}.txt`;
  const evalBase = `eval.${safeIndex}.${safeTopics}.${safeMetric}.${stamp}.txt`;
  const runFile = path.join(ARTIFACTS_DIR, runBase);
  const evalFile = path.join(ARTIFACTS_DIR, evalBase);

  // ---- Retrieval ----
  let searchRes;
  try {
    searchRes = await anserini.searchCollection({
      index: indexName,
      topics,
      output: runFile,
      hits: 1000,
      threads: 1,
      bm25: true,
    });
  } catch (err) {
    res.status(500).json({
      error: `SearchCollection failed to launch: ${err.message}`,
      stage: 'retrieval',
    });
    return;
  }
  if (searchRes.code !== 0 || !fs.existsSync(runFile)) {
    res.status(500).json({
      error: 'SearchCollection did not produce a run file',
      stage: 'retrieval',
      command: searchRes.command,
      exitCode: searchRes.code,
      stderr: tail(searchRes.stderr, 4000),
    });
    return;
  }

  // ---- Evaluation ----
  let evalRes;
  try {
    evalRes = await anserini.trecEval({
      metricArgs,
      qrels: evalKey,
      runFile,
    });
  } catch (err) {
    res.status(500).json({
      error: `TrecEval failed to launch: ${err.message}`,
      stage: 'evaluation',
    });
    return;
  }
  if (evalRes.code !== 0) {
    res.status(500).json({
      error: 'TrecEval exited with a non-zero status',
      stage: 'evaluation',
      command: evalRes.command,
      exitCode: evalRes.code,
      stderr: tail(evalRes.stderr, 4000),
      stdout: tail(evalRes.stdout, 4000),
    });
    return;
  }

  fs.writeFileSync(evalFile, evalRes.stdout);

  const parsed = parseTrecEvalOutput(evalRes.stdout);
  // Match the user-visible metric label to a row in the trec_eval output.
  const primary = pickPrimaryScore(parsed, metricLabel, metricArgs);

  res.json({
    ok: true,
    indexName,
    topics,
    evalKey,
    metric: { label: metricLabel, args: metricArgs },
    score: primary ? primary.score : null,
    scoreRow: primary ? primary.row : null,
    allScores: parsed,
    expectedScores: resolvedPairing.expectedScores,
    runFile: path.relative(ROOT, runFile),
    runArtifact: runBase,
    runPreview: tail(fs.readFileSync(runFile, 'utf8'), 4000),
    evalFile: path.relative(ROOT, evalFile),
    evalArtifact: evalBase,
    evalOutput: evalRes.stdout,
    retrievalCommand: searchRes.command,
    evaluationCommand: evalRes.command,
    retrievalMs: searchRes.durationMs,
    evaluationMs: evalRes.durationMs,
    totalMs: Date.now() - start,
  });
});

app.get('/api/artifacts/:name', (req, res) => {
  const name = req.params.name;
  if (!/^[A-Za-z0-9._-]+$/.test(name)) {
    res.status(400).send('Invalid artifact name');
    return;
  }
  const file = path.join(ARTIFACTS_DIR, name);
  if (!fs.existsSync(file)) {
    res.status(404).send('Artifact not found');
    return;
  }
  res.type('text/plain').send(fs.readFileSync(file));
});

// ---------- Helpers ----------

function tail(text, max) {
  if (!text) return '';
  return text.length > max ? text.slice(text.length - max) : text;
}

/**
 * Parse `trec_eval` style output. Each line looks like:
 *   "map                   \tall\t0.3123"
 * Returns rows for the "all" aggregate only, which is what the UI surfaces.
 */
function parseTrecEvalOutput(stdout) {
  const rows = [];
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split(/\s+/);
    if (parts.length < 3) continue;
    const [metric, qid, value] = parts;
    if (qid !== 'all') continue;
    const score = Number(value);
    if (Number.isNaN(score)) continue;
    rows.push({ metric, qid, score });
  }
  return rows;
}

/**
 * Translate a user-visible metric label (and its TrecEval args) into the
 * matching row in the parsed output.
 */
function pickPrimaryScore(rows, label, args) {
  if (rows.length === 0) return null;

  // The actual metric name appears as the last `-m <name>` argument.
  let mFlag = null;
  for (let i = 0; i < args.length - 1; i++) {
    if (args[i] === '-m') mFlag = args[i + 1];
  }
  if (mFlag) {
    // Convert e.g. "ndcg_cut.10" -> "ndcg_cut_10" because trec_eval normalises
    // dots to underscores in its output column.
    const normalised = mFlag.replace(/\./g, '_');
    const match = rows.find(
      (r) => r.metric === normalised || r.metric === mFlag
    );
    if (match) return { row: match, score: match.score };
  }

  // Fall back to label-based fuzzy match (covers MAP vs map, P@30 vs P_30).
  const fuzz = label.toLowerCase().replace(/[^a-z0-9]/g, '');
  const match = rows.find(
    (r) => r.metric.toLowerCase().replace(/[^a-z0-9]/g, '') === fuzz
  );
  if (match) return { row: match, score: match.score };

  return { row: rows[0], score: rows[0].score };
}

if (require.main === module) {
  const server = app.listen(PORT, () => {
    console.log(`Anserini evaluator listening on http://localhost:${PORT}`);
    warmCatalog();
  });
  process.on('SIGTERM', () => server.close());
  process.on('SIGINT', () => { server.close(); process.exit(0); });
}

module.exports = { app, getCatalog };
