'use strict';

const express = require('express');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const os = require('os');
const net = require('net');

const { AnseriniRunner, parseTrecEval } = require('./lib/anserini');
const { AppState, loadCachedArtifacts } = require('./lib/state');
const { SAMPLE_QUERIES, getSamples } = require('./lib/samples');

const PORT = Number(process.env.PORT || 10000);
const HOST = process.env.HOST || '0.0.0.0';
const ANSERINI_JAR_ENV = process.env.ANSERINI_JAR || '';
const CACHE_DIR = process.env.ANSERINI_CACHE_DIR || path.join(process.env.DATA_DIR || '/data', 'pyserini');
const APP_DATA_DIR = process.env.APP_DATA_DIR || path.join(process.env.DATA_DIR || '/data', 'workbench');
const LOGS_DIR = path.join(APP_DATA_DIR, 'logs');
const REST_PORT = Number(process.env.REST_PORT || 0); // 0 => auto-pick

const app = express();
app.use(express.json({ limit: '64kb' }));
app.use(express.static(path.join(__dirname, 'public'), { extensions: ['html'] }));

// ---------------------------------------------------------------------------
// Directory bootstrap
// ---------------------------------------------------------------------------

function ensureDirSync(p) {
  fs.mkdirSync(p, { recursive: true });
}

ensureDirSync(CACHE_DIR);
ensureDirSync(APP_DATA_DIR);
ensureDirSync(LOGS_DIR);

// Make pyserini see our cache.
process.env.PYSERINI_CACHE = CACHE_DIR;
const PYSERINI_INDEXES = path.join(CACHE_DIR, 'indexes');
ensureDirSync(PYSERINI_INDEXES);

const state = new AppState();

// ---------------------------------------------------------------------------
// Resolve Anserini fatjar
// ---------------------------------------------------------------------------

function resolveFatjar() {
  if (ANSERINI_JAR_ENV) {
    return ANSERINI_JAR_ENV;
  }
  // Search a few predictable locations.
  const candidates = [
    path.join(APP_DATA_DIR, 'anserini-fatjar.jar'),
    path.join(APP_DATA_DIR, 'anserini-2.1.1-fatjar.jar'),
    path.join(APP_DATA_DIR, 'anserini-*-fatjar.jar'),
    '/opt/anserini/anserini-fatjar.jar',
    '/opt/anserini/anserini-2.1.1-fatjar.jar',
  ];
  for (const c of candidates) {
    if (c.includes('*')) {
      const dir = path.dirname(c);
      if (fs.existsSync(dir)) {
        const matches = fs.readdirSync(dir).filter((n) => n.includes('fatjar') && n.endsWith('.jar'));
        if (matches.length) return path.join(dir, matches.sort().pop());
      }
      continue;
    }
    if (fs.existsSync(c)) return c;
  }
  return '';
}

async function maybeDownloadFatjar(targetPath) {
  // Avoid hammering Maven Central if we already have a file.
  if (fs.existsSync(targetPath) && fs.statSync(targetPath).size > 1_000_000) {
    return targetPath;
  }
  const version = process.env.ANSERINI_VERSION || '2.1.1';
  const url = `https://repo1.maven.org/maven2/io/anserini/anserini/${version}/anserini-${version}-fatjar.jar`;
  state.addWarning(`Downloading Anserini ${version} fatjar from ${url}`);
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to download Anserini fatjar (HTTP ${res.status} from ${url})`);
  }
  ensureDirSync(path.dirname(targetPath));
  const file = await fsp.open(targetPath, 'w');
  try {
    await new Promise((resolve, reject) => {
      const stream = require('stream');
      const passthrough = new stream.PassThrough();
      file.createWriteStream().then((ws) => {
        passthrough.pipe(ws);
        passthrough.on('error', reject);
        ws.on('error', reject);
        ws.on('finish', resolve);
      });
      res.body.pipe(passthrough);
    });
  } finally {
    await file.close();
  }
  return targetPath;
}

async function prepareFatjar() {
  let jar = resolveFatjar();
  if (!jar) {
    jar = path.join(APP_DATA_DIR, `anserini-${process.env.ANSERINI_VERSION || '2.1.1'}-fatjar.jar`);
    await maybeDownloadFatjar(jar);
  }
  if (!fs.existsSync(jar)) {
    throw new Error(`ANSERINI_JAR does not exist: ${jar}`);
  }
  const stat = await fsp.stat(jar);
  state.fatjar = { path: jar, exists: true, sizeBytes: stat.size };
  return jar;
}

// ---------------------------------------------------------------------------
// Anserini setup
// ---------------------------------------------------------------------------

const runner = new AnseriniRunner({
  jar: '', // set in setupAnserini
  cacheDir: CACHE_DIR,
  dataDir: APP_DATA_DIR,
  logsDir: LOGS_DIR,
});

// Wrap runMain so we can also keep the command log in app state.
const origRunMain = runner.runMain.bind(runner);
runner.runMain = async function patchedRunMain(...args) {
  const res = await origRunMain(...args);
  state.recordCommand({
    label: res.label,
    command: res.command,
    mainClass: res.mainClass,
    args: res.args,
    exitCode: res.exitCode,
    startedAt: res.startedAt,
    finishedAt: res.finishedAt,
    durationMs: res.durationMs,
    logFile: res.logFile || null,
  });
  state.markUpdated();
  return res;
};

async function setupAnserini() {
  // 1. Java probe
  state.java = await runner.probeJava();
  if (!state.java.ok) {
    throw new Error(`Java is not available on PATH: ${state.java.raw || state.java.error || 'unknown'}`);
  }
  if (state.java.major !== 21) {
    state.addWarning(`Detected Java major version ${state.java.major}; Anserini 2.1.x is built for Java 21.`);
  }

  // 2. Fatjar
  const jar = await prepareFatjar();
  runner.jar = jar;

  // 3. Reproduction discovery
  const configs = await runner.listReproductions();
  state.reproduction.configs = configs;
  const beirCore = await runner.showReproduction('beir.core');
  state.reproduction.beirCore = beirCore;
  // Persist the raw YAML for inspection in the UI.
  const reproRawPath = path.join(APP_DATA_DIR, 'reproduction.beir.core.yaml');
  const yamlText = require('js-yaml').dump(beirCore);
  await fsp.writeFile(reproRawPath, yamlText);
  state.reproduction.rawShowPath = reproRawPath;

  const flat = beirCore.conditions.find((c) => c.name === 'flat');
  if (!flat) throw new Error("beir.core does not contain 'flat' condition");
  const nfTopic = flat.topics.find((t) => t.topic_key === 'nfcorpus');
  if (!nfTopic) throw new Error("beir.core 'flat' condition has no nfcorpus topic");
  state.reproduction.nfcorpus = {
    condition: flat.name,
    display: flat.display,
    command: flat.command,
    evalKey: nfTopic.eval_key,
    topicKey: nfTopic.topic_key,
    expected: nfTopic.expected_scores,
    metricDefinitions: nfTopic.metric_definitions,
  };

  // 4. Prebuilt index discovery
  const prebuilt = await runner.lookupPrebuiltIndex('^beir-v1.0.0-nfcorpus\\.flat$');
  if (!prebuilt.length) {
    throw new Error('Prebuilt index beir-v1.0.0-nfcorpus.flat not advertised by the fatjar');
  }
  state.prebuiltIndex.entry = prebuilt[0];
  state.prebuiltIndex.path = path.join(PYSERINI_INDEXES, prebuilt[0].filename.replace(/\.tar\.gz$|\.tar$/, ''));
  state.prebuiltIndex.downloadRequired = !fs.existsSync(state.prebuiltIndex.path);

  // 5. Topics (just count)
  const topics = await runner.getTopics('beir-nfcorpus');
  state.topics.count = Object.keys(topics).length;
  state.topics.raw = topics;
}

async function runEvaluation({ force = false } = {}) {
  if (state.eval.status === 'running') {
    throw new Error('Evaluation already in progress');
  }
  state.eval.status = 'running';
  state.eval.messages.push({ at: new Date().toISOString(), kind: 'status', text: force ? 'Forced re-run' : 'Starting' });
  state.eval.cached = false;
  state.markUpdated();

  try {
    // 1. SearchCollection
    const searchResult = await runner.runNfcorpusSearch({});
    state.eval.runFile = { path: searchResult.runPath, sizeBytes: searchResult.sizeBytes, mtime: new Date().toISOString() };
    state.search.lastCommand = searchResult.command;
    state.search.lastDurationMs = searchResult.durationMs;

    // 2. TrecEval
    const metrics = state.reproduction.nfcorpus.metricDefinitions['nDCG@10'] || '-c -m ndcg_cut.10';
    const evalResult = await runner.evaluateNfcorpusRun({ runPath: searchResult.runPath, metricArgs: metrics });
    const evalFilePath = path.join(APP_DATA_DIR, 'eval.nfcorpus.bm25.txt');
    await fsp.writeFile(evalFilePath, evalResult.raw);
    state.eval.observed = evalResult.observed;
    state.eval.evalFile = { path: evalFilePath, mtime: new Date().toISOString() };
    state.eval.lastDurationMs = evalResult.durationMs;
    state.eval.lastRunAt = new Date().toISOString();
    state.eval.expected = state.reproduction.nfcorpus.expected;
    state.eval.metricDefinitions = state.reproduction.nfcorpus.metricDefinitions;
    state.eval.status = 'completed';
    state.eval.messages.push({ at: new Date().toISOString(), kind: 'status', text: 'Completed' });
  } catch (err) {
    state.eval.status = 'failed';
    state.eval.messages.push({ at: new Date().toISOString(), kind: 'error', text: String(err.message) });
    state.addError(err);
    throw err;
  } finally {
    state.markUpdated();
  }
  return state.eval;
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

function publicState() {
  return {
    app: {
      name: 'NFCorpus Live Retrieval Diagnostics Workbench',
      version: '1.0.0',
      phase: state.phase,
      startedAt: state.startedAt,
      lastUpdatedAt: state.lastUpdatedAt,
      ports: state.ports,
      env: {
        PORT,
        HOST,
        CACHE_DIR,
        APP_DATA_DIR,
        LOGS_DIR,
        PYSERINI_INDEXES,
        NODE_ENV: process.env.NODE_ENV || 'development',
      },
      host: { hostname: os.hostname(), cpus: os.cpus().length, platform: os.platform(), release: os.release() },
    },
    java: state.java,
    fatjar: state.fatjar,
    reproduction: {
      dataset: 'nfcorpus',
      beirCoreCondition: state.reproduction.nfcorpus,
      configs: state.reproduction.configs,
      rawShowPath: state.reproduction.rawShowPath,
    },
    prebuiltIndex: state.prebuiltIndex,
    topics: {
      set: state.topics.set,
      count: state.topics.count,
      samples: SAMPLE_QUERIES.slice(0, 12),
    },
    search: state.search,
    eval: {
      status: state.eval.status,
      runFile: state.eval.runFile,
      evalFile: state.eval.evalFile,
      observed: state.eval.observed,
      expected: state.eval.expected,
      metricDefinitions: state.eval.metricDefinitions,
      lastDurationMs: state.eval.lastDurationMs,
      lastRunAt: state.eval.lastRunAt,
      cached: state.eval.cached,
      messages: state.eval.messages.slice(-20),
    },
    restServer: {
      running: state.restServer.running,
      port: state.restServer.port,
      lastError: state.restServer.lastError,
    },
    errors: state.errors,
    warnings: state.warnings,
    commands: state.commands.slice(-50),
  };
}

function readinessFlags() {
  return {
    app: state.phase === 'ready' || state.phase === 'live' ? 'ok' : 'starting',
    anserini: state.fatjar.exists && state.java && state.java.ok ? 'ok' : 'unavailable',
    nfcorpus: state.reproduction.nfcorpus ? 'configured' : 'unconfigured',
    search: state.restServer.running ? 'available' : 'unavailable',
    evaluation: state.eval.status === 'completed' || state.eval.status === 'cached' ? 'available' : state.eval.status,
  };
}

app.get('/health', (req, res) => {
  const flags = readinessFlags();
  const ok = state.phase === 'ready' || state.phase === 'live';
  res.status(ok ? 200 : 503).json({
    status: ok ? 'ok' : 'starting',
    ...flags,
    dataset: 'nfcorpus',
    uptimeSec: Math.round((Date.now() - state.startedAt.getTime()) / 1000),
    timestamp: new Date().toISOString(),
  });
});

app.get('/api/status', (req, res) => {
  res.json(publicState());
});

app.get('/api/samples', (req, res) => {
  res.json({ samples: SAMPLE_QUERIES });
});

app.get('/api/commands', (req, res) => {
  res.json({ commands: state.commands });
});

app.get('/api/artifacts', (req, res) => {
  const list = [];
  for (const c of state.commands) {
    if (c.logFile) list.push({ kind: 'log', path: c.logFile });
  }
  if (state.eval.runFile) list.push({ kind: 'run', path: state.eval.runFile.path });
  if (state.eval.evalFile) list.push({ kind: 'eval', path: state.eval.evalFile.path });
  if (state.reproduction.rawShowPath) list.push({ kind: 'reproduction-yaml', path: state.reproduction.rawShowPath });
  res.json({ artifacts: list });
});

app.get('/api/eval', async (req, res) => {
  try {
    const force = req.query.rerun === '1' || req.query.rerun === 'true';
    if (force || state.eval.status !== 'completed') {
      await runEvaluation({ force });
    }
    res.json({
      ...publicState().eval,
      comparison: comparisonRows(),
    });
  } catch (err) {
    res.status(500).json({ error: err.message, eval: publicState().eval });
  }
});

app.get('/api/eval/rerun', async (req, res) => {
  try {
    await runEvaluation({ force: true });
    res.json({ ok: true, eval: publicState().eval, comparison: comparisonRows() });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message, eval: publicState().eval });
  }
});

app.get('/api/search', async (req, res) => {
  const q = (req.query.q || '').toString().trim();
  const hits = Math.min(50, Math.max(1, Number(req.query.hits || 10)));
  if (!q) return res.status(400).json({ error: 'Missing required query parameter "q"' });
  if (!state.restServer.running) {
    return res.status(503).json({ error: 'Search backend is not ready. Check /health.' });
  }
  const url = `http://127.0.0.1:${state.restServer.port}/v1/beir-v1.0.0-nfcorpus.flat/search?query=${encodeURIComponent(q)}&hits=${hits}`;
  const startedAt = Date.now();
  try {
    const r = await fetch(url);
    const text = await r.text();
    let json;
    try { json = JSON.parse(text); } catch (_) { json = null; }
    if (!r.ok) {
      return res.status(502).json({ error: `RestServer returned ${r.status}`, body: text });
    }
    if (!json) {
      return res.status(502).json({ error: 'RestServer returned non-JSON', body: text });
    }
    const candidates = Array.isArray(json.candidates) ? json.candidates : [];
    const results = candidates.map((c) => ({
      rank: c.rank,
      docid: c.docid,
      score: c.score,
      title: c.doc && c.doc.title ? c.doc.title : '',
      text: c.doc && c.doc.text ? c.doc.text : '',
      snippet: makeSnippet(c.doc && c.doc.text ? c.doc.text : '', q),
      url: c.doc && c.doc.metadata && c.doc.metadata.url ? c.doc.metadata.url : '',
    }));
    state.search.lastResultCount = results.length;
    state.search.lastDurationMs = Date.now() - startedAt;
    state.search.lastCommand = `curl "${url}"`;
    res.json({
      query: q,
      index: 'beir-v1.0.0-nfcorpus.flat',
      hitsRequested: hits,
      hits: results.length,
      durationMs: state.search.lastDurationMs,
      results,
    });
  } catch (err) {
    res.status(502).json({ error: `RestServer unreachable: ${err.message}` });
  }
});

app.get('/artifacts/*', async (req, res) => {
  const rel = req.params[0];
  const full = path.normalize(path.join(APP_DATA_DIR, rel));
  if (!full.startsWith(APP_DATA_DIR)) return res.status(400).json({ error: 'invalid path' });
  if (!fs.existsSync(full)) return res.status(404).json({ error: 'not found' });
  const data = await fsp.readFile(full, 'utf8');
  res.type('text/plain').send(data);
});

app.get('/logs/*', async (req, res) => {
  const rel = req.params[0];
  const full = path.normalize(path.join(LOGS_DIR, rel));
  if (!full.startsWith(LOGS_DIR)) return res.status(400).json({ error: 'invalid path' });
  if (!fs.existsSync(full)) return res.status(404).json({ error: 'not found' });
  const data = await fsp.readFile(full, 'utf8');
  res.type('text/plain').send(data);
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSnippet(text, query) {
  if (!text) return '';
  const MAX = 360;
  const terms = query.split(/\s+/).filter((t) => t.length > 2);
  let lower = text.toLowerCase();
  let bestIdx = -1;
  for (const t of terms) {
    const i = lower.indexOf(t.toLowerCase());
    if (i >= 0 && (bestIdx === -1 || i < bestIdx)) bestIdx = i;
  }
  if (bestIdx === -1) return text.slice(0, MAX) + (text.length > MAX ? '…' : '');
  const start = Math.max(0, bestIdx - 80);
  const end = Math.min(text.length, bestIdx + MAX - 80);
  const snippet = (start > 0 ? '…' : '') + text.slice(start, end) + (end < text.length ? '…' : '');
  return snippet;
}

function comparisonRows() {
  const observed = state.eval.observed || [];
  const expected = state.eval.expected || {};
  const rows = [];
  for (const obs of observed) {
    const expectedKey = canonicalMetricKey(obs.metric);
    const exp = expected[expectedKey];
    if (exp == null) {
      rows.push({
        metric: obs.metric,
        observed: obs.score,
        expected: null,
        delta: null,
        status: 'no-expected',
      });
      continue;
    }
    const delta = obs.score - Number(exp);
    const abs = Math.abs(delta);
    let status = 'fail';
    if (abs < 1e-4) status = 'pass';
    else if (abs < 0.005) status = 'close';
    rows.push({ metric: obs.metric, observed: obs.score, expected: Number(exp), delta, status });
  }
  return rows;
}

function canonicalMetricKey(metricName) {
  if (!metricName) return metricName;
  // TrecEval emits `ndcg_cut.10`, expected is `nDCG@10`. Normalize.
  const m = metricName.match(/^(\w+?)(?:_cut[._](\d+))?$/i);
  if (m) {
    return `${m[1].toLowerCase()}@${m[2] || 'all'}`.replace('ndcg@', 'nDCG@');
  }
  return metricName;
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

let restServerHandle = null;

async function startRestServer() {
  // Try the preferred port; fall back to a free high port on conflict.
  const preferred = REST_PORT || pickPort();
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const port = attempt === 0 ? preferred : pickPort();
    try {
      const handle = await runner.startRestServer({ port });
      restServerHandle = handle;
      state.restServer = { running: true, pid: handle.child.pid, port: handle.port, lastError: null };
      state.ports.rest = handle.port;
      state.markUpdated();
      return;
    } catch (err) {
      state.addWarning(`RestServer failed to bind port ${port}: ${err.message}`);
    }
  }
  throw new Error('Could not start Anserini RestServer after 5 attempts');
}

function pickPort() {
  return 20000 + Math.floor(Math.random() * 20000);
}

function logPublicEndpoints() {
  // Print a clear summary on startup so the container log tells the operator
  // exactly where to point a browser.
  const divider = '═'.repeat(72);
  console.log(divider);
  console.log('NFCorpus Live Retrieval Diagnostics Workbench');
  console.log(divider);
  console.log(`HTTP listening on http://${HOST}:${PORT}`);
  console.log(`RestServer bound to 127.0.0.1:${state.ports.rest}`);
  console.log(`Anserini fatjar: ${state.fatjar.path}`);
  console.log(`Java major: ${state.java && state.java.major}`);
  console.log(`Data dir: ${APP_DATA_DIR}`);
  console.log(`Cache dir: ${CACHE_DIR}`);
  console.log(`Reproduction dataset: nfcorpus (condition: ${state.reproduction.nfcorpus && state.reproduction.nfcorpus.condition})`);
  console.log(`Prebuilt index entry: ${state.prebuiltIndex.name}`);
  console.log(`Eval status: ${state.eval.status}`);
  console.log(divider);
}

async function bootstrap() {
  state.phase = 'setup-anserini';
  state.markUpdated();
  await setupAnserini();
  state.phase = 'setup-eval';
  state.markUpdated();
  // Pre-load any cached artifacts.
  await loadCachedArtifacts(state, { dataDir: APP_DATA_DIR, logsDir: LOGS_DIR });
  if (state.eval.status !== 'completed') {
    await runEvaluation({});
  }
  state.phase = 'starting-rest';
  state.markUpdated();
  await startRestServer();
  state.phase = 'ready';
  state.markUpdated();
}

async function start() {
  try {
    await bootstrap();
  } catch (err) {
    state.phase = 'error';
    state.addError(err);
    state.markUpdated();
    console.error('FATAL during bootstrap:', err);
  }
  app.listen(PORT, HOST, () => {
    state.ports.http = PORT;
    state.markUpdated();
    logPublicEndpoints();
  });
}

process.on('unhandledRejection', (err) => {
  state.addError(err);
  console.error('unhandledRejection', err);
});
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

function shutdown() {
  console.log('Shutting down...');
  if (restServerHandle && restServerHandle.child) {
    try { restServerHandle.child.kill('SIGTERM'); } catch (_) { /* ignore */ }
  }
  process.exit(0);
}

start();
