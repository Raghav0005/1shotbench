import express from 'express';
import fs from 'fs/promises';
import { existsSync, statSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import https from 'https';
import yaml from 'js-yaml';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const dataDir = path.resolve(process.env.DATA_DIR || path.join(rootDir, 'data'));
const logsDir = path.join(dataDir, 'logs');
const runsDir = path.join(dataDir, 'runs');
const cacheDir = path.join(dataDir, '.cache');
const jarsDir = path.join(dataDir, 'jars');
const port = Number(process.env.PORT || 10000);

const DATASET = {
  id: 'NFCorpus',
  topicKey: 'nfcorpus',
  topics: 'beir-nfcorpus',
  index: 'beir-v1.0.0-nfcorpus.flat',
  evalKey: 'beir-v1.0.0-nfcorpus.test',
  config: 'beir.core',
  condition: 'flat',
  metric: 'nDCG@10',
  trecMetric: 'ndcg_cut.10',
  note: 'Only the small BEIR NFCorpus prebuilt flat index, NFCorpus topics, and NFCorpus qrels are prepared.'
};

const SAMPLE_QUERIES = [
  'dietary fiber',
  'vitamin d deficiency',
  'omega 3 cardiovascular disease',
  'green tea cancer prevention'
];

const state = {
  app: { status: 'initializing', startedAt: new Date().toISOString(), error: null },
  dataset: DATASET,
  samples: SAMPLE_QUERIES,
  java: { available: false, version: null, error: null },
  anserini: { available: false, jar: null, version: null, verified: false, error: null },
  nfcorpus: { ready: false, index: DATASET.index, artifactPath: null, error: null },
  reproduction: { discovered: false, config: DATASET.config, expected: {}, dryRunSnippet: '', showPath: null, dryRunPath: null, error: null },
  search: { available: false, lastQuery: null, lastCommandId: null, error: null },
  evaluation: { available: false, running: false, cached: false, lastRunAt: null, elapsedMs: null, runFile: null, evalFile: null, metrics: {}, expected: {}, comparisons: {}, commandIds: [], error: null },
  commands: [],
  artifacts: [],
  provenance: { realAnseriniCommandsExecuted: false, mocksUsed: false }
};

function shellQuote(s) {
  if (/^[A-Za-z0-9_./:=@%+,-]+$/.test(String(s))) return String(s);
  return `'${String(s).replace(/'/g, `'\\''`)}'`;
}

function commandLine(executable, args) {
  return [executable, ...args].map(shellQuote).join(' ');
}

function truncate(s, n = 4000) {
  if (!s) return '';
  return s.length > n ? `${s.slice(0, n)}\n… truncated ${s.length - n} chars` : s;
}

async function ensureDirs() {
  await fs.mkdir(logsDir, { recursive: true });
  await fs.mkdir(runsDir, { recursive: true });
  await fs.mkdir(cacheDir, { recursive: true });
  await fs.mkdir(jarsDir, { recursive: true });
}

async function readIfExists(file, max = 4000) {
  try {
    const text = await fs.readFile(file, 'utf8');
    return truncate(text, max);
  } catch {
    return '';
  }
}

function commandEnv() {
  return {
    ...process.env,
    HOME: dataDir,
    XDG_CACHE_HOME: cacheDir,
    PYSERINI_CACHE: cacheDir,
    ANSERINI_JAR: state.anserini.jar || process.env.ANSERINI_JAR || ''
  };
}

async function runProcess(label, executable, args, opts = {}) {
  await ensureDirs();
  const id = `${String(state.commands.length + 1).padStart(3, '0')}-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`;
  const stdoutPath = path.join(logsDir, `${id}.stdout.log`);
  const stderrPath = path.join(logsDir, `${id}.stderr.log`);
  const cmd = {
    id,
    label,
    command: commandLine(executable, args),
    cwd: opts.cwd || rootDir,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    durationMs: null,
    exitCode: null,
    status: 'running',
    stdoutPath,
    stderrPath,
    stdoutPreview: '',
    stderrPreview: ''
  };
  state.commands.push(cmd);
  const started = Date.now();

  let stdout = '';
  let stderr = '';
  const timeoutMs = opts.timeoutMs || 120000;

  return await new Promise((resolve) => {
    let settled = false;
    const child = spawn(executable, args, {
      cwd: opts.cwd || rootDir,
      env: { ...commandEnv(), ...(opts.env || {}) },
      shell: false
    });
    const timer = setTimeout(() => {
      if (!settled) {
        stderr += `\nCommand timed out after ${timeoutMs} ms`;
        child.kill('SIGTERM');
      }
    }, timeoutMs);

    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('error', (err) => { stderr += `\n${err.stack || err.message}`; });
    child.on('close', async (code) => {
      settled = true;
      clearTimeout(timer);
      await fs.writeFile(stdoutPath, stdout);
      await fs.writeFile(stderrPath, stderr);
      cmd.finishedAt = new Date().toISOString();
      cmd.durationMs = Date.now() - started;
      cmd.exitCode = code;
      cmd.status = code === 0 ? 'ok' : 'failed';
      cmd.stdoutPreview = truncate(stdout);
      cmd.stderrPreview = truncate(stderr);
      state.artifacts.push({ label: `${label} stdout`, path: stdoutPath, kind: 'log' });
      state.artifacts.push({ label: `${label} stderr`, path: stderrPath, kind: 'log' });
      resolve({ code, stdout, stderr, cmd });
    });
  });
}

async function fetchText(url) {
  return await new Promise((resolve, reject) => {
    https.get(url, (res) => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        reject(new Error(`GET ${url} returned ${res.statusCode}`));
        res.resume();
        return;
      }
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

async function latestAnseriniVersion() {
  const metadataUrl = 'https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml';
  const xml = await fetchText(metadataUrl);
  const release = xml.match(/<release>([^<]+)<\/release>/)?.[1];
  if (!release) throw new Error('Could not parse Maven Central Anserini release metadata');
  return release;
}

async function downloadFile(url, outputPath) {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  return await new Promise((resolve, reject) => {
    const fileChunks = [];
    https.get(url, (res) => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        reject(new Error(`GET ${url} returned ${res.statusCode}`));
        res.resume();
        return;
      }
      res.on('data', (chunk) => fileChunks.push(chunk));
      res.on('end', async () => {
        await fs.writeFile(outputPath, Buffer.concat(fileChunks));
        resolve();
      });
    }).on('error', reject);
  });
}

async function resolveAnseriniJar() {
  const envJar = process.env.ANSERINI_JAR;
  if (envJar && existsSync(envJar)) {
    state.anserini.jar = path.resolve(envJar);
    const m = envJar.match(/anserini-([^-]+)-fatjar\.jar/);
    state.anserini.version = m?.[1] || 'env';
    return;
  }

  const candidates = [
    process.env.ANSERINI_VERSION ? `/opt/anserini/anserini-${process.env.ANSERINI_VERSION}-fatjar.jar` : null,
    '/opt/anserini/anserini-2.1.1-fatjar.jar'
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      state.anserini.jar = candidate;
      state.anserini.version = candidate.match(/anserini-([^-]+)-fatjar\.jar/)?.[1] || process.env.ANSERINI_VERSION || 'bundled';
      return;
    }
  }

  const preexisting = (await fs.readdir(jarsDir).catch(() => [])).find((f) => /^anserini-.*-fatjar\.jar$/.test(f));
  if (preexisting) {
    state.anserini.jar = path.join(jarsDir, preexisting);
    state.anserini.version = preexisting.match(/anserini-([^-]+)-fatjar\.jar/)?.[1] || 'cached';
    return;
  }

  const version = process.env.ANSERINI_VERSION || await latestAnseriniVersion();
  const jarPath = path.join(jarsDir, `anserini-${version}-fatjar.jar`);
  const url = `https://repo1.maven.org/maven2/io/anserini/anserini/${version}/anserini-${version}-fatjar.jar`;
  const downloadCmd = {
    id: `${String(state.commands.length + 1).padStart(3, '0')}-download-anserini-fatjar`,
    label: 'download Anserini fatjar from Maven Central',
    command: `GET ${url} -> ${jarPath}`,
    cwd: rootDir,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    durationMs: null,
    exitCode: null,
    status: 'running',
    stdoutPath: jarPath,
    stderrPath: '',
    stdoutPreview: '',
    stderrPreview: ''
  };
  state.commands.push(downloadCmd);
  const started = Date.now();
  try {
    await downloadFile(url, jarPath);
    downloadCmd.exitCode = 0;
    downloadCmd.status = 'ok';
    downloadCmd.stdoutPreview = `Downloaded ${statSync(jarPath).size} bytes`;
  } catch (err) {
    downloadCmd.exitCode = 1;
    downloadCmd.status = 'failed';
    downloadCmd.stderrPreview = err.message;
    throw err;
  } finally {
    downloadCmd.finishedAt = new Date().toISOString();
    downloadCmd.durationMs = Date.now() - started;
  }
  state.anserini.jar = jarPath;
  state.anserini.version = version;
}

function javaArgs(mainClass, args = []) {
  return ['-cp', state.anserini.jar, mainClass, ...args];
}

async function verifyJavaAndFatjar() {
  const javaVersion = await runProcess('Java version check', 'java', ['-version'], { timeoutMs: 20000 });
  if (javaVersion.code !== 0) throw new Error(`Java is not available: ${javaVersion.stderr || javaVersion.stdout}`);
  state.java.available = true;
  state.java.version = (javaVersion.stderr || javaVersion.stdout).split('\n')[0];

  await resolveAnseriniJar();
  if (!state.anserini.jar || !existsSync(state.anserini.jar)) throw new Error('Anserini fatjar was not found after resolution');
  state.anserini.available = true;

  const verify = await runProcess('fatjar verification via SearchCollection -options', 'java', javaArgs('io.anserini.search.SearchCollection', ['-options']), { timeoutMs: 30000 });
  const verifyOutput = `${verify.stdout}\n${verify.stderr}`;
  if (verify.code !== 0 || !verifyOutput.includes('Options for SearchCollection')) {
    throw new Error(`Anserini fatjar verification failed: ${verify.stderr || verify.stdout}`);
  }
  state.anserini.verified = true;
}

function parseExpectedFromYaml(showText) {
  const doc = yaml.load(showText);
  const condition = doc?.conditions?.find((c) => c.name === DATASET.condition);
  const topic = condition?.topics?.find((t) => t.topic_key === DATASET.topicKey);
  if (!topic) return {};
  return {
    condition: condition.name,
    display: condition.display,
    commandTemplate: condition.command,
    topicKey: topic.topic_key,
    evalKey: topic.eval_key,
    expectedScores: topic.expected_scores || {},
    metricDefinitions: topic.metric_definitions || {}
  };
}

function nfcorpusDryRunSnippet(text) {
  const lines = text.split(/\r?\n/);
  const snippets = [];
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('topic_key: nfcorpus') || lines[i].includes('beir-v1.0.0-nfcorpus.flat')) {
      snippets.push(...lines.slice(Math.max(0, i - 2), Math.min(lines.length, i + 5)));
    }
  }
  return [...new Set(snippets)].join('\n').slice(0, 6000);
}

async function discoverReproduction() {
  const list = await runProcess('reproduction config list', 'java', javaArgs('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--list']), { timeoutMs: 60000 });
  if (list.code !== 0 || !list.stdout.includes(DATASET.config)) throw new Error(`Could not list Anserini prebuilt reproduction configs: ${list.stderr || list.stdout}`);

  const show = await runProcess('reproduction show beir.core', 'java', javaArgs('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--config', DATASET.config, '--show']), { timeoutMs: 60000 });
  if (show.code !== 0) throw new Error(`Could not show ${DATASET.config}: ${show.stderr || show.stdout}`);
  state.reproduction.showPath = show.cmd.stdoutPath;
  state.reproduction.expected = parseExpectedFromYaml(show.stdout);
  state.evaluation.expected = state.reproduction.expected.expectedScores || {};

  const dry = await runProcess('reproduction dry-run beir.core', 'java', javaArgs('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--config', DATASET.config, '--dry-run', '--runs-directory', runsDir]), { timeoutMs: 60000 });
  if (dry.code !== 0) throw new Error(`Could not dry-run ${DATASET.config}: ${dry.stderr || dry.stdout}`);
  state.reproduction.dryRunPath = dry.cmd.stdoutPath;
  state.reproduction.dryRunSnippet = nfcorpusDryRunSnippet(dry.stdout);
  state.reproduction.discovered = Boolean(state.reproduction.expected?.expectedScores);
}

function parseSearchJson(stdout) {
  const start = stdout.indexOf('{"query"');
  if (start < 0) throw new Error(`Search output did not contain JSON: ${truncate(stdout, 500)}`);
  const jsonText = stdout.slice(start).trim();
  return JSON.parse(jsonText);
}

function normalizeSearchResults(parsed) {
  return (parsed.candidates || []).map((c, i) => ({
    rank: i + 1,
    docid: c.docid,
    score: c.score,
    title: c.doc?.title || '',
    text: c.doc?.text || c.doc?.contents || '',
    snippet: truncate(c.doc?.text || c.doc?.contents || '', 700),
    metadata: c.doc?.metadata || {}
  }));
}

async function runSearch(query, hits = 10) {
  if (!state.anserini.verified) throw new Error('Anserini is not verified yet');
  const safeHits = Math.max(1, Math.min(Number(hits) || 10, 50));
  const args = javaArgs('io.anserini.cli.Search', ['--index', DATASET.index, '--query', query, '--hits', String(safeHits), '--json']);
  const result = await runProcess(`live NFCorpus search: ${query}`, 'java', args, { timeoutMs: 120000 });
  state.search.lastQuery = query;
  state.search.lastCommandId = result.cmd.id;
  if (result.code !== 0) {
    state.search.error = result.stderr || result.stdout;
    throw new Error(`Search failed: ${state.search.error}`);
  }
  const parsed = parseSearchJson(result.stdout);
  const results = normalizeSearchResults(parsed);
  if (!results.length) throw new Error('Anserini returned zero results');
  state.search.available = true;
  state.search.error = null;
  state.nfcorpus.ready = true;
  state.nfcorpus.artifactPath = cacheDir;
  return { query, hits: safeHits, command: result.cmd, results };
}

function parseTrecEval(stdout) {
  const metrics = {};
  for (const line of stdout.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 3 && Number.isFinite(Number(parts[2]))) {
      metrics[parts[0]] = Number(parts[2]);
    }
  }
  return metrics;
}

function compareMetrics(observed) {
  const expected = state.evaluation.expected || {};
  const comparisons = {};
  for (const [name, expectedValue] of Object.entries(expected)) {
    const observedKey = name === 'nDCG@10' ? 'ndcg_cut_10' : name.replace('@', '_').replace('.', '_');
    const obs = observed[observedKey];
    if (typeof obs !== 'number') {
      comparisons[name] = { expected: expectedValue, observed: null, delta: null, status: 'missing' };
      continue;
    }
    const delta = obs - Number(expectedValue);
    const abs = Math.abs(delta);
    comparisons[name] = {
      expected: Number(expectedValue),
      observed: obs,
      delta,
      status: abs <= 0.0001 ? 'pass' : abs <= 0.002 ? 'close' : 'fail'
    };
  }
  return comparisons;
}

async function runEvaluation({ cached = false } = {}) {
  if (state.evaluation.running) throw new Error('Evaluation is already running');
  state.evaluation.running = true;
  state.evaluation.error = null;
  const started = Date.now();
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const runFile = path.join(runsDir, `run.beir.core.flat.nfcorpus.${stamp}.txt`);
  const evalFile = path.join(runsDir, `eval.beir.core.flat.nfcorpus.${stamp}.txt`);
  try {
    const searchArgs = javaArgs('io.anserini.search.SearchCollection', [
      '-threads', String(process.env.ANSERINI_THREADS || 2),
      '-index', DATASET.index,
      '-topics', DATASET.topics,
      '-output', runFile,
      '-bm25',
      '-removeQuery',
      '-hits', '1000'
    ]);
    const retrieval = await runProcess('BM25 retrieval over NFCorpus topics', 'java', searchArgs, { timeoutMs: 240000 });
    if (retrieval.code !== 0 || !existsSync(runFile)) throw new Error(`BM25 retrieval failed: ${retrieval.stderr || retrieval.stdout}`);

    const evalArgs = javaArgs('io.anserini.eval.TrecEval', ['-c', '-m', DATASET.trecMetric, DATASET.evalKey, runFile]);
    const evaluation = await runProcess('TrecEval NFCorpus BM25 run', 'java', evalArgs, { timeoutMs: 120000 });
    await fs.writeFile(evalFile, evaluation.stdout + evaluation.stderr);
    state.artifacts.push({ label: 'TREC run file', path: runFile, kind: 'run' });
    state.artifacts.push({ label: 'Evaluation output', path: evalFile, kind: 'evaluation' });
    if (evaluation.code !== 0) throw new Error(`TrecEval failed: ${evaluation.stderr || evaluation.stdout}`);

    const observed = parseTrecEval(evaluation.stdout);
    state.evaluation.available = Object.keys(observed).length > 0;
    state.evaluation.cached = cached;
    state.evaluation.lastRunAt = new Date().toISOString();
    state.evaluation.elapsedMs = Date.now() - started;
    state.evaluation.runFile = runFile;
    state.evaluation.evalFile = evalFile;
    state.evaluation.metrics = observed;
    state.evaluation.comparisons = compareMetrics(observed);
    state.evaluation.commandIds = [retrieval.cmd.id, evaluation.cmd.id];
    state.evaluation.error = null;
    state.provenance.realAnseriniCommandsExecuted = true;
    return state.evaluation;
  } catch (err) {
    state.evaluation.error = err.message;
    state.evaluation.available = false;
    throw err;
  } finally {
    state.evaluation.running = false;
  }
}

async function startup() {
  await ensureDirs();
  try {
    await verifyJavaAndFatjar();
    await discoverReproduction();
    await runSearch(SAMPLE_QUERIES[0], 5);
    await runEvaluation({ cached: true });
    state.app.status = 'ready';
  } catch (err) {
    state.app.status = state.search.available || state.evaluation.available ? 'degraded' : 'error';
    state.app.error = err.stack || err.message;
    if (!state.java.available) state.java.error = err.message;
    if (!state.anserini.verified) state.anserini.error = err.message;
    if (!state.reproduction.discovered) state.reproduction.error = err.message;
    if (!state.nfcorpus.ready) state.nfcorpus.error = err.message;
  }
}

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(rootDir, 'public')));

app.get('/health', (_req, res) => {
  res.json({
    app: state.app.status,
    anseriniAvailable: state.anserini.available && state.anserini.verified,
    nfcorpusReady: state.nfcorpus.ready,
    searchAvailable: state.search.available,
    evaluationAvailable: state.evaluation.available,
    dataset: state.dataset.id,
    jar: state.anserini.jar,
    error: state.app.error
  });
});

app.get('/api/status', async (_req, res) => {
  const artifactPreviews = [];
  for (const artifact of state.artifacts.slice(-12)) {
    artifactPreviews.push({ ...artifact, preview: await readIfExists(artifact.path, 1200) });
  }
  res.json({ ...state, artifactPreviews });
});

app.post('/api/search', async (req, res) => {
  try {
    const query = String(req.body?.query || '').trim();
    if (!query) return res.status(400).json({ error: 'query is required' });
    const result = await runSearch(query, req.body?.hits || 10);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/evaluation/rerun', async (_req, res) => {
  try {
    const result = await runEvaluation({ cached: false });
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/artifact', async (req, res) => {
  const requested = String(req.query.path || '');
  const resolved = path.resolve(requested);
  if (!resolved.startsWith(dataDir)) return res.status(403).send('Artifact path is outside DATA_DIR');
  try {
    res.type('text/plain').send(await readIfExists(resolved, 20000));
  } catch {
    res.status(404).send('Artifact not found');
  }
});

const server = app.listen(port, '0.0.0.0', () => {
  console.log(`NFCorpus diagnostics workbench listening on 0.0.0.0:${port}`);
  console.log(`DATA_DIR=${dataDir}`);
});
server.on('error', (err) => {
  state.app.status = 'error';
  state.app.error = `HTTP bind failure on 0.0.0.0:${port}: ${err.message}`;
  console.error(state.app.error);
});

startup();
