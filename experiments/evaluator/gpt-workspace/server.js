'use strict';

const express = require('express');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = __dirname;
const PORT = Number(process.env.PORT || 3000);
const COMMAND_TIMEOUT_MS = Number(process.env.ANSERINI_COMMAND_TIMEOUT_MS || 10 * 60 * 1000);

const CACM_PAIRING = {
  index: 'cacm',
  topics: 'cacm',
  qrels: 'cacm',
  qrelsSource: 'Anserini built-in TrecEval qrels key: cacm',
  retrievalModel: 'BM25',
  hits: 1000,
  metrics: [
    { label: 'nDCG@10', id: 'ndcg_cut.10', outputKey: 'ndcg_cut_10' },
    { label: 'Recall@1000', id: 'recall.1000', outputKey: 'recall_1000' },
    { label: 'MAP', id: 'map', outputKey: 'map' },
    { label: 'P@30', id: 'P.30', outputKey: 'P_30' }
  ],
  inferredFrom: 'Repo-local Anserini skills: CACM SearchCollection and TrecEval smoke-test workflow.'
};

let catalogCache = null;
let catalogCacheAt = 0;
const CATALOG_TTL_MS = 5 * 60 * 1000;

function isFile(p) {
  try {
    return fs.statSync(p).isFile();
  } catch {
    return false;
  }
}

function findAnseriniJar() {
  if (process.env.ANSERINI_JAR && isFile(process.env.ANSERINI_JAR)) {
    return path.resolve(process.env.ANSERINI_JAR);
  }

  const dirs = [path.join(ROOT, '.anserini'), ROOT];
  const jars = [];
  for (const dir of dirs) {
    try {
      for (const entry of fs.readdirSync(dir)) {
        if (/^anserini-.+-fatjar\.jar$/.test(entry)) {
          const candidate = path.join(dir, entry);
          if (isFile(candidate)) jars.push(candidate);
        }
      }
    } catch {
      // directory does not exist; ignore
    }
  }
  jars.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  return jars.length ? path.resolve(jars[jars.length - 1]) : null;
}

function runCommand(command, args, options = {}) {
  const timeoutMs = options.timeoutMs || COMMAND_TIMEOUT_MS;
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const child = spawn(command, args, {
      cwd: ROOT,
      env: { ...process.env, ...(options.env || {}) },
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 3000).unref();
    }, timeoutMs);

    child.stdout.on('data', chunk => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', chunk => {
      stderr += chunk.toString();
    });
    child.on('error', err => {
      clearTimeout(timer);
      reject(Object.assign(new Error(`Failed to start ${command}: ${err.message}`), { cause: err }));
    });
    child.on('close', code => {
      clearTimeout(timer);
      const result = { command, args, stdout, stderr, code, elapsedMs: Date.now() - startedAt };
      if (code === 0) {
        resolve(result);
      } else {
        const message = code === null
          ? `${command} timed out after ${timeoutMs} ms`
          : `${command} exited with code ${code}`;
        reject(Object.assign(new Error(message), result));
      }
    });
  });
}

function runAnserini(jar, mainClass, args, options = {}) {
  return runCommand('java', ['-cp', jar, mainClass, ...args], options);
}

function parseJsonFromOutput(output) {
  const trimmed = output.trim();
  const start = trimmed.indexOf('[');
  const end = trimmed.lastIndexOf(']');
  if (start === -1 || end === -1 || end < start) {
    throw new Error('Anserini registry did not return a JSON array.');
  }
  return JSON.parse(trimmed.slice(start, end + 1));
}

function parseCacmReproductionConfig(output) {
  const topicMatch = output.match(/topic_key:\s*([^\s]+)/);
  const evalMatch = output.match(/eval_key:\s*([^\s]+)/);
  const commandMatch = output.match(/command:\s*(.+)/);
  return {
    ...CACM_PAIRING,
    topics: topicMatch ? topicMatch[1] : CACM_PAIRING.topics,
    qrels: evalMatch ? evalMatch[1] : CACM_PAIRING.qrels,
    reproductionCommandTemplate: commandMatch ? commandMatch[1].trim() : null,
    inferredFrom: 'Anserini ReproduceFromPrebuiltIndexes --config cacm --show, plus repo-local Anserini skills for current TrecEval metric identifiers.'
  };
}

async function discoverCatalog({ force = false } = {}) {
  const now = Date.now();
  if (!force && catalogCache && now - catalogCacheAt < CATALOG_TTL_MS) {
    return catalogCache;
  }

  const jar = findAnseriniJar();
  if (!jar) {
    const err = new Error('Missing Anserini fatjar. Run `npm run setup:anserini` or set ANSERINI_JAR to an anserini-*-fatjar.jar file.');
    err.status = 500;
    throw err;
  }

  const [indexResult, topicsResult, cacmConfigResult] = await Promise.all([
    runAnserini(jar, 'io.anserini.cli.PrebuiltIndexRegistry', ['--type', 'inverted', '--list'], { timeoutMs: 120000 }),
    runAnserini(jar, 'io.anserini.cli.TopicsRegistry', ['--list'], { timeoutMs: 120000 }),
    runAnserini(jar, 'io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--config', 'cacm', '--show'], { timeoutMs: 120000 })
  ]);

  const rawIndexes = parseJsonFromOutput(indexResult.stdout);
  const topics = parseJsonFromOutput(topicsResult.stdout);
  const topicsSet = new Set(topics.map(t => String(t).toLowerCase()));
  const cacmPairing = parseCacmReproductionConfig(cacmConfigResult.stdout);

  const indexes = rawIndexes.map(item => {
    const name = item.name || item.corpus_index || '';
    const isCacm = name === cacmPairing.index;
    const topicAvailable = topicsSet.has(cacmPairing.topics.toLowerCase());
    const evaluable = isCacm && topicAvailable;
    return {
      ...item,
      name,
      evaluable,
      status: evaluable ? 'Ready for evaluation' : 'Catalog-only',
      pairing: evaluable ? cacmPairing : null,
      readyReason: evaluable ? cacmPairing.inferredFrom : null,
      catalogOnlyReason: evaluable ? null : 'No automatic topics/qrels pairing has been inferred for this index.'
    };
  });

  indexes.sort((a, b) => {
    if (a.name === 'cacm') return -1;
    if (b.name === 'cacm') return 1;
    if (a.evaluable !== b.evaluable) return a.evaluable ? -1 : 1;
    return String(a.name).localeCompare(String(b.name));
  });

  catalogCache = {
    jar,
    generatedAt: new Date().toISOString(),
    registryCommands: {
      prebuiltIndexes: `java -cp ${jar} io.anserini.cli.PrebuiltIndexRegistry --type inverted --list`,
      topics: `java -cp ${jar} io.anserini.cli.TopicsRegistry --list`,
      cacmReproductionConfig: `java -cp ${jar} io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config cacm --show`
    },
    topics,
    indexes
  };
  catalogCacheAt = now;
  return catalogCache;
}

function safeSlug(value) {
  return String(value).replace(/[^A-Za-z0-9._-]+/g, '_');
}

function parseEvaluationScore(output, metric) {
  const lines = output.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const expectedKeys = [metric.outputKey, metric.id.replace(/\./g, '_')];
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3 && expectedKeys.includes(parts[0])) {
      const score = Number(parts[2]);
      if (Number.isFinite(score)) return { key: parts[0], score, line };
    }
  }

  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3) {
      const score = Number(parts[2]);
      if (Number.isFinite(score)) return { key: parts[0], score, line };
    }
  }
  throw new Error(`Could not parse a numeric score for metric ${metric.label} from Anserini evaluator output.`);
}

function relativeArtifact(p) {
  return path.relative(ROOT, p);
}

async function runEvaluation(body) {
  const catalog = await discoverCatalog();
  const indexName = body.indexName || body.index;
  const selected = catalog.indexes.find(index => index.name === indexName);
  if (!selected) {
    const err = new Error(`Index '${indexName}' was not found in the Anserini prebuilt inverted-index registry.`);
    err.status = 404;
    throw err;
  }
  if (!selected.evaluable || !selected.pairing) {
    const err = new Error(`Index '${indexName}' is catalog-only: ${selected.catalogOnlyReason}`);
    err.status = 400;
    throw err;
  }

  const metricId = body.metricId || body.metric;
  const metric = selected.pairing.metrics.find(m => m.id === metricId || m.label === metricId);
  if (!metric) {
    const err = new Error(`Metric '${metricId}' is not available for ${indexName}.`);
    err.status = 400;
    throw err;
  }

  const startedAt = Date.now();
  const runId = `${safeSlug(indexName)}-${safeSlug(metric.id)}-${new Date().toISOString().replace(/[:.]/g, '-')}`;
  const runDir = path.join(ROOT, 'artifacts', 'runs');
  const evalDir = path.join(ROOT, 'artifacts', 'eval');
  await fsp.mkdir(runDir, { recursive: true });
  await fsp.mkdir(evalDir, { recursive: true });
  const runFile = path.join(runDir, `run.${runId}.txt`);
  const evalFile = path.join(evalDir, `eval.${runId}.txt`);

  const searchArgs = [
    '-threads', '1',
    '-index', selected.pairing.index,
    '-topics', selected.pairing.topics,
    '-output', runFile,
    '-hits', String(selected.pairing.hits),
    '-bm25'
  ];
  const searchResult = await runAnserini(catalog.jar, 'io.anserini.search.SearchCollection', searchArgs);

  if (!isFile(runFile) || fs.statSync(runFile).size === 0) {
    const err = new Error('Retrieval completed but did not create a non-empty TREC run file.');
    err.status = 500;
    throw err;
  }

  const evalArgs = ['-c', '-m', metric.id, selected.pairing.qrels, runFile];
  const evalResult = await runAnserini(catalog.jar, 'io.anserini.eval.TrecEval', evalArgs);
  await fsp.writeFile(evalFile, evalResult.stdout + (evalResult.stderr ? `\n--- stderr ---\n${evalResult.stderr}` : ''), 'utf8');

  const parsed = parseEvaluationScore(evalResult.stdout, metric);
  const elapsedMs = Date.now() - startedAt;
  const preview = (evalResult.stdout + (evalResult.stderr ? `\n${evalResult.stderr}` : '')).trim().slice(0, 4000);

  return {
    status: 'completed',
    score: parsed.score,
    scoreLine: parsed.line,
    metric: {
      label: metric.label,
      id: metric.id,
      outputKey: parsed.key
    },
    selectedIndex: selected.name,
    topics: selected.pairing.topics,
    qrels: selected.pairing.qrels,
    qrelsSource: selected.pairing.qrelsSource,
    retrievalModel: selected.pairing.retrievalModel,
    hits: selected.pairing.hits,
    elapsedMs,
    anseriniJar: catalog.jar,
    runFile: relativeArtifact(runFile),
    evaluationOutputFile: relativeArtifact(evalFile),
    runFileAbsolute: runFile,
    evaluationOutputFileAbsolute: evalFile,
    searchCommand: `java -cp ${catalog.jar} io.anserini.search.SearchCollection ${searchArgs.join(' ')}`,
    evalCommand: `java -cp ${catalog.jar} io.anserini.eval.TrecEval ${evalArgs.join(' ')}`,
    searchElapsedMs: searchResult.elapsedMs,
    evalElapsedMs: evalResult.elapsedMs,
    evaluationPreview: preview
  };
}

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(ROOT, 'public')));

app.get('/api/environment', async (req, res) => {
  const jar = findAnseriniJar();
  try {
    const java = await runCommand('java', ['-version'], { timeoutMs: 30000 });
    res.json({ ok: Boolean(jar), jar, java: java.stderr || java.stdout });
  } catch (err) {
    res.status(500).json({ ok: false, jar, error: 'Missing Java or unable to run java -version.', details: err.message });
  }
});

app.get('/api/catalog', async (req, res) => {
  try {
    const catalog = await discoverCatalog({ force: req.query.refresh === '1' });
    res.json(catalog);
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message, details: err.stderr || undefined });
  }
});

app.post('/api/evaluate', async (req, res) => {
  try {
    const result = await runEvaluation(req.body || {});
    res.json(result);
  } catch (err) {
    res.status(err.status || 500).json({
      error: err.message,
      stdout: err.stdout,
      stderr: err.stderr,
      command: err.command ? `${err.command} ${(err.args || []).join(' ')}` : undefined
    });
  }
});

app.get('/api/artifacts/*', async (req, res) => {
  const rel = req.params[0] || '';
  const artifactPath = path.resolve(ROOT, 'artifacts', rel);
  if (!artifactPath.startsWith(path.resolve(ROOT, 'artifacts') + path.sep)) {
    return res.status(400).send('Invalid artifact path');
  }
  if (!isFile(artifactPath)) return res.status(404).send('Artifact not found');
  res.type('text/plain').sendFile(artifactPath);
});

app.get('*', (req, res) => {
  res.sendFile(path.join(ROOT, 'public', 'index.html'));
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Anserini Prebuilt Index Evaluator running at http://localhost:${PORT}`);
  });
}

module.exports = { app, findAnseriniJar, discoverCatalog, runEvaluation };
