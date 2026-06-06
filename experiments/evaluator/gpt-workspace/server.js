const express = require('express');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const app = express();
const PORT = Number(process.env.PORT || 3000);
const ROOT = __dirname;
const ARTIFACT_DIR = path.join(ROOT, 'artifacts');
const RUN_DIR = path.join(ARTIFACT_DIR, 'runs');
const EVAL_DIR = path.join(ARTIFACT_DIR, 'evals');
const LOG_DIR = path.join(ARTIFACT_DIR, 'logs');

for (const dir of [ARTIFACT_DIR, RUN_DIR, EVAL_DIR, LOG_DIR]) {
  fs.mkdirSync(dir, { recursive: true });
}

app.use(express.json());
app.use(express.static(path.join(ROOT, 'public')));

let catalogCache = null;
let catalogCacheTime = 0;

const CACM_CONFIG = {
  index: 'cacm',
  topics: 'cacm',
  qrels: 'cacm',
  qrelsLabel: 'Anserini built-in qrels key: cacm',
  searchModel: 'BM25 (Anserini defaults: k1=0.9, b=0.4)',
  hits: 1000,
  metrics: [
    { label: 'nDCG@10', value: 'ndcg_cut.10', outputName: 'ndcg_cut_10' },
    { label: 'Recall@1000', value: 'recall.1000', outputName: 'recall_1000' },
    { label: 'MAP', value: 'map', outputName: 'map' },
    { label: 'P@30', value: 'P.30', outputName: 'P_30' }
  ]
};

function findAnseriniJar() {
  const envJar = process.env.ANSERINI_JAR;
  if (envJar && fs.existsSync(envJar)) return path.resolve(envJar);
  const localJar = fs.readdirSync(ROOT)
    .filter((name) => /^anserini-.*-fatjar\.jar$/.test(name))
    .sort()
    .pop();
  if (localJar) return path.join(ROOT, localJar);
  return null;
}

function runProcess(cmd, args, options = {}) {
  const timeoutMs = options.timeoutMs || 120000;
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const child = spawn(cmd, args, {
      cwd: options.cwd || ROOT,
      env: { ...process.env, ...(options.env || {}) },
      shell: false
    });
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 3000).unref();
    }, timeoutMs);

    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const result = { cmd, args, code, stdout, stderr, elapsedMs: Date.now() - started };
      if (timedOut) {
        const err = new Error(`Command timed out after ${Math.round(timeoutMs / 1000)}s`);
        err.result = result;
        reject(err);
      } else if (code !== 0) {
        const err = new Error(`Command failed with exit code ${code}: ${cmd} ${args.join(' ')}`);
        err.result = result;
        reject(err);
      } else {
        resolve(result);
      }
    });
  });
}

async function runJava(className, classArgs, options = {}) {
  const jar = findAnseriniJar();
  if (!jar) {
    throw new Error('Anserini fatjar not found. Download anserini-*-fatjar.jar or set ANSERINI_JAR.');
  }
  return runProcess('java', ['-cp', jar, className, ...classArgs], options);
}

function extractJson(text) {
  const trimmed = text.trim();
  if (!trimmed) throw new Error('No JSON emitted by Anserini registry.');
  return JSON.parse(trimmed);
}

function publicPath(filePath) {
  return path.relative(ROOT, filePath);
}

function withEvaluationMetadata(indexEntry, topicsList) {
  const isCacm = indexEntry.name === CACM_CONFIG.index;
  const hasCacmTopics = topicsList.includes(CACM_CONFIG.topics);
  return {
    ...indexEntry,
    evaluable: isCacm && hasCacmTopics,
    evaluation: isCacm && hasCacmTopics ? {
      topics: CACM_CONFIG.topics,
      qrels: CACM_CONFIG.qrels,
      qrelsLabel: CACM_CONFIG.qrelsLabel,
      metrics: CACM_CONFIG.metrics,
      defaultMetric: CACM_CONFIG.metrics[0].value,
      searchModel: CACM_CONFIG.searchModel,
      reason: 'Small end-to-end pairing verified by Anserini fatjar smoke-test workflow.'
    } : null,
    catalogOnlyReason: isCacm && !hasCacmTopics
      ? 'CACM index is present, but CACM topics were not discovered in TopicsRegistry.'
      : (isCacm ? null : 'Visible in PrebuiltIndexRegistry, but this app has not automatically discovered a safe topics/qrels pairing for it.')
  };
}

async function loadCatalog(force = false) {
  const now = Date.now();
  if (!force && catalogCache && (now - catalogCacheTime) < 5 * 60 * 1000) return catalogCache;

  const [indexResult, topicsResult] = await Promise.all([
    runJava('io.anserini.cli.PrebuiltIndexRegistry', ['--type', 'inverted', '--list'], { timeoutMs: 120000 }),
    runJava('io.anserini.cli.TopicsRegistry', ['--list'], { timeoutMs: 120000 })
  ]);
  const indexes = extractJson(indexResult.stdout);
  const topics = extractJson(topicsResult.stdout);
  if (!Array.isArray(indexes)) throw new Error('Unexpected PrebuiltIndexRegistry JSON shape.');
  if (!Array.isArray(topics)) throw new Error('Unexpected TopicsRegistry JSON shape.');

  const decorated = indexes
    .map((entry) => withEvaluationMetadata(entry, topics))
    .sort((a, b) => {
      if (a.name === 'cacm') return -1;
      if (b.name === 'cacm') return 1;
      if (a.evaluable !== b.evaluable) return a.evaluable ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

  catalogCache = {
    source: 'Anserini CLI registries: PrebuiltIndexRegistry --type inverted --list and TopicsRegistry --list',
    jar: findAnseriniJar(),
    generatedAt: new Date().toISOString(),
    indexes: decorated,
    topicsCount: topics.length,
    registryCommands: {
      indexes: 'java -cp <anserini-fatjar> io.anserini.cli.PrebuiltIndexRegistry --type inverted --list',
      topics: 'java -cp <anserini-fatjar> io.anserini.cli.TopicsRegistry --list'
    }
  };
  catalogCacheTime = now;
  return catalogCache;
}

function parseMetricScore(evalOutput, metric) {
  const desired = CACM_CONFIG.metrics.find((m) => m.value === metric);
  const aliases = new Set([metric, metric.replace(/\./g, '_')]);
  if (desired) aliases.add(desired.outputName);
  for (const line of evalOutput.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 3 && aliases.has(parts[0])) {
      const score = Number(parts[2]);
      if (Number.isFinite(score)) return { measure: parts[0], topic: parts[1], score };
    }
  }
  const fallback = evalOutput.match(/([0-9]+(?:\.[0-9]+)?)/);
  if (fallback) return { measure: metric, topic: 'all', score: Number(fallback[1]) };
  throw new Error(`Unable to parse numeric score for metric ${metric}.`);
}

app.get('/api/health', async (_req, res) => {
  const jar = findAnseriniJar();
  if (!jar) return res.status(500).json({ ok: false, error: 'Anserini fatjar not found.' });
  try {
    const java = await runProcess('java', ['-version'], { timeoutMs: 15000 });
    res.json({ ok: true, jar, java: java.stderr || java.stdout });
  } catch (err) {
    res.status(500).json({ ok: false, jar, error: err.message, details: err.result?.stderr || err.result?.stdout });
  }
});

app.get('/api/catalog', async (req, res) => {
  try {
    const catalog = await loadCatalog(req.query.refresh === '1');
    res.json(catalog);
  } catch (err) {
    res.status(500).json({
      error: err.message,
      details: err.result ? { stdout: err.result.stdout, stderr: err.result.stderr } : undefined
    });
  }
});

app.post('/api/evaluate', async (req, res) => {
  const requestedIndex = req.body?.index || CACM_CONFIG.index;
  const metric = req.body?.metric || CACM_CONFIG.metrics[0].value;
  const metricConfig = CACM_CONFIG.metrics.find((m) => m.value === metric);

  if (requestedIndex !== CACM_CONFIG.index) {
    return res.status(400).json({ error: `Index ${requestedIndex} is catalog-only in this app; no automatic topics/qrels pairing is available.` });
  }
  if (!metricConfig) {
    return res.status(400).json({ error: `Metric ${metric} is not available for CACM in this app.` });
  }

  const started = Date.now();
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const runFile = path.join(RUN_DIR, `run.cacm.${metricConfig.outputName}.${stamp}.txt`);
  const evalFile = path.join(EVAL_DIR, `eval.cacm.${metricConfig.outputName}.${stamp}.txt`);
  const searchLogFile = path.join(LOG_DIR, `search.cacm.${metricConfig.outputName}.${stamp}.log`);
  const evalLogFile = path.join(LOG_DIR, `eval.cacm.${metricConfig.outputName}.${stamp}.log`);

  const searchArgs = [
    '-threads', '1',
    '-index', CACM_CONFIG.index,
    '-topics', CACM_CONFIG.topics,
    '-output', runFile,
    '-hits', String(CACM_CONFIG.hits),
    '-bm25'
  ];
  const evalArgs = ['-c', '-m', metric, CACM_CONFIG.qrels, runFile];

  try {
    const search = await runJava('io.anserini.search.SearchCollection', searchArgs, { timeoutMs: 180000 });
    fs.writeFileSync(searchLogFile, `${search.stdout}\n${search.stderr}`);
    if (!fs.existsSync(runFile) || fs.statSync(runFile).size === 0) {
      throw new Error('Anserini retrieval completed but did not write a non-empty run file.');
    }

    const evaluation = await runJava('io.anserini.eval.TrecEval', evalArgs, { timeoutMs: 60000 });
    fs.writeFileSync(evalFile, evaluation.stdout);
    fs.writeFileSync(evalLogFile, `${evaluation.stdout}\n${evaluation.stderr}`);
    const parsed = parseMetricScore(evaluation.stdout, metric);

    const runPreview = fs.readFileSync(runFile, 'utf8').split(/\r?\n/).filter(Boolean).slice(0, 5).join('\n');
    res.json({
      status: 'completed',
      score: parsed.score,
      measure: parsed.measure,
      selectedMetric: metric,
      selectedMetricLabel: metricConfig.label,
      elapsedMs: Date.now() - started,
      index: CACM_CONFIG.index,
      topics: CACM_CONFIG.topics,
      qrels: CACM_CONFIG.qrels,
      qrelsLabel: CACM_CONFIG.qrelsLabel,
      searchModel: CACM_CONFIG.searchModel,
      commands: {
        retrieval: `java -cp <anserini-fatjar> io.anserini.search.SearchCollection ${searchArgs.map((a) => a.includes(' ') ? JSON.stringify(a) : a).join(' ')}`,
        evaluation: `java -cp <anserini-fatjar> io.anserini.eval.TrecEval ${evalArgs.map((a) => a.includes(' ') ? JSON.stringify(a) : a).join(' ')}`
      },
      artifacts: {
        runFile: publicPath(runFile),
        evalFile: publicPath(evalFile),
        searchLogFile: publicPath(searchLogFile),
        evalLogFile: publicPath(evalLogFile)
      },
      evaluationOutput: evaluation.stdout.trim(),
      runPreview
    });
  } catch (err) {
    const details = err.result ? `${err.result.stdout}\n${err.result.stderr}`.trim() : '';
    res.status(500).json({
      status: 'failed',
      error: err.message,
      details,
      elapsedMs: Date.now() - started,
      index: CACM_CONFIG.index,
      topics: CACM_CONFIG.topics,
      metric,
      artifacts: {
        runFile: publicPath(runFile),
        evalFile: publicPath(evalFile),
        searchLogFile: publicPath(searchLogFile),
        evalLogFile: publicPath(evalLogFile)
      }
    });
  }
});

if (require.main === module) {
  app.listen(PORT, () => {
    const jar = findAnseriniJar();
    console.log(`Anserini evaluator listening on http://localhost:${PORT}`);
    console.log(jar ? `Using Anserini fatjar: ${jar}` : 'No Anserini fatjar found; set ANSERINI_JAR or download one locally.');
  });
}

module.exports = app;
