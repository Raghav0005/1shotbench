const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { URL } = require('url');

const PORT = Number(process.env.PORT || 10000);
const HOST = '0.0.0.0';
const ROOT = __dirname;
const CACHE_DIR = path.resolve(process.env.APP_CACHE_DIR || path.join(ROOT, '.cache'));
const ANSERINI_DIR = path.join(CACHE_DIR, 'anserini');
const RUNS_DIR = path.join(CACHE_DIR, 'runs');
const LOGS_DIR = path.join(CACHE_DIR, 'logs');
const PYSERINI_CACHE = path.join(CACHE_DIR, 'pyserini');

const DATASET = {
  name: 'NFCorpus',
  index: 'beir-v1.0.0-nfcorpus.flat',
  topics: 'beir-nfcorpus',
  evalKey: 'beir-v1.0.0-nfcorpus.test',
  reproductionConfig: 'beir.core',
  condition: 'flat',
  runFile: path.join(RUNS_DIR, 'run.beir-v1.0.0-nfcorpus.flat.bm25.txt'),
  evalFile: path.join(RUNS_DIR, 'eval.beir-v1.0.0-nfcorpus.flat.bm25.txt')
};

const state = {
  app: { status: 'starting', startedAt: new Date().toISOString(), errors: [] },
  dataset: DATASET,
  anserini: { status: 'pending', available: false, java: null, version: null, jar: null, smoke: null, error: null },
  nfcorpus: { status: 'pending', ready: false, searchAvailable: false, evaluationAvailable: false, indexStatus: 'pending', downloadPolicy: 'Only the NFCorpus BEIR prebuilt index and NFCorpus topics/qrels are used; the full BEIR corpus archive is never downloaded by this app.' },
  reproduction: { status: 'pending', expected: {}, metricDefinitions: {}, commandTemplate: null, evalKey: DATASET.evalKey, showPreview: '', dryRunPreview: '', error: null },
  evaluation: { status: 'pending', observed: {}, expected: {}, comparisons: [], runFile: DATASET.runFile, evalFile: DATASET.evalFile, elapsedMs: null, fresh: false, error: null, outputPreview: '' },
  commands: []
};

function ensureDirs() {
  for (const dir of [CACHE_DIR, ANSERINI_DIR, RUNS_DIR, LOGS_DIR, PYSERINI_CACHE]) fs.mkdirSync(dir, { recursive: true });
}

function shellQuote(s) {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(String(s))) return String(s);
  return `'${String(s).replace(/'/g, `'"'"'`)}'`;
}

function commandLine(cmd, args) {
  return [cmd, ...args].map(shellQuote).join(' ');
}

function preview(text, limit = 5000) {
  const t = String(text || '');
  return t.length > limit ? `${t.slice(0, limit)}\n… [truncated ${t.length - limit} chars]` : t;
}

function writeLog(base, stdout, stderr) {
  const safe = base.replace(/[^A-Za-z0-9_.-]+/g, '-');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const out = path.join(LOGS_DIR, `${safe}.${stamp}.stdout.log`);
  const err = path.join(LOGS_DIR, `${safe}.${stamp}.stderr.log`);
  fs.writeFileSync(out, stdout || '');
  fs.writeFileSync(err, stderr || '');
  return { stdoutLog: out, stderrLog: err };
}

function runLogged(name, cmd, args, opts = {}) {
  const startedAt = new Date();
  const entry = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name,
    command: commandLine(cmd, args),
    cwd: opts.cwd || ROOT,
    startedAt: startedAt.toISOString(),
    status: 'running',
    exitCode: null,
    elapsedMs: null,
    stdoutPreview: '',
    stderrPreview: '',
    artifacts: opts.artifacts || []
  };
  state.commands.unshift(entry);
  state.commands = state.commands.slice(0, 60);
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: opts.cwd || ROOT,
      env: { ...process.env, PYSERINI_CACHE, JAVA_TOOL_OPTIONS: process.env.JAVA_TOOL_OPTIONS || '' },
      shell: false
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('error', (err) => {
      stderr += `\n${err.stack || err.message}`;
    });
    child.on('close', (code) => {
      const elapsedMs = Date.now() - startedAt.getTime();
      const logs = writeLog(name, stdout, stderr);
      Object.assign(entry, {
        status: code === 0 ? 'ok' : 'failed',
        exitCode: code,
        elapsedMs,
        stdoutPreview: preview(stdout),
        stderrPreview: preview(stderr),
        artifacts: [...(opts.artifacts || []), logs.stdoutLog, logs.stderrLog]
      });
      resolve({ code, stdout, stderr, entry });
    });
  });
}

function javaArgs(mainClass, args = []) {
  return ['-cp', state.anserini.jar, mainClass, ...args];
}

async function fetchText(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        reject(new Error(`HTTP ${res.statusCode} for ${url}`));
        res.resume();
        return;
      }
      let body = '';
      res.on('data', (d) => { body += d.toString(); });
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

async function resolveAnseriniVersion() {
  if (process.env.ANSERINI_VERSION) return process.env.ANSERINI_VERSION;
  const metadataUrl = 'https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml';
  const body = await fetchText(metadataUrl);
  const m = body.match(/<release>([^<]+)<\/release>/);
  if (!m) throw new Error('Unable to discover latest Anserini release from Maven metadata');
  return m[1];
}

async function downloadJar(version) {
  const envJar = process.env.ANSERINI_JAR && path.resolve(process.env.ANSERINI_JAR);
  if (envJar && fs.existsSync(envJar)) return envJar;
  const jar = path.join(ANSERINI_DIR, `anserini-${version}-fatjar.jar`);
  if (fs.existsSync(jar)) return jar;
  const url = `https://repo1.maven.org/maven2/io/anserini/anserini/${version}/anserini-${version}-fatjar.jar`;
  const res = await runLogged('download Anserini fatjar', 'curl', ['-fL', '-o', jar, url], { artifacts: [jar] });
  if (res.code !== 0 || !fs.existsSync(jar)) throw new Error(`Failed to download Anserini fatjar ${version}: ${res.stderr || res.stdout}`);
  return jar;
}

function parseNfcorpusReproduction(showText) {
  const expected = {};
  const metricDefinitions = {};
  let commandTemplate = null;
  const lines = showText.split(/\r?\n/);
  let inFlat = false;
  let inNf = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*- name:\s*flat\s*$/.test(line)) inFlat = true;
    else if (/^\s*- name:\s*/.test(line) && !/^\s*- name:\s*flat\s*$/.test(line) && inFlat && !inNf) inFlat = false;
    if (inFlat && /command:\s*(.+)$/.test(line)) commandTemplate = line.match(/command:\s*(.+)$/)[1].trim();
    if (inFlat && /topic_key:\s*nfcorpus\s*$/.test(line)) inNf = true;
    if (inNf && /eval_key:\s*(\S+)/.test(line)) state.reproduction.evalKey = line.match(/eval_key:\s*(\S+)/)[1];
    if (inNf && /nDCG@10:\s*([0-9.]+)/.test(line)) expected['nDCG@10'] = Number(line.match(/nDCG@10:\s*([0-9.]+)/)[1]);
    if (inNf && /nDCG@10:\s*"([^"]+)"/.test(line)) metricDefinitions['nDCG@10'] = line.match(/nDCG@10:\s*"([^"]+)"/)[1];
    if (inNf && /^\s*- topic_key:\s*/.test(line) && !/nfcorpus/.test(line)) inNf = false;
  }
  return { expected, metricDefinitions, commandTemplate };
}

function parseEvalOutput(text) {
  const observed = {};
  for (const line of text.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 3 && /^[-+]?\d*\.?\d+$/.test(parts[2])) {
      const metric = parts[0].replace('ndcg_cut_10', 'nDCG@10').replace('P_30', 'P@30');
      observed[metric] = Number(parts[2]);
    }
  }
  return observed;
}

function buildComparisons(observed, expected) {
  return Object.keys(observed).map((metric) => {
    const exp = expected[metric];
    const delta = typeof exp === 'number' ? Number((observed[metric] - exp).toFixed(6)) : null;
    const abs = delta === null ? null : Math.abs(delta);
    return { metric, observed: observed[metric], expected: exp ?? null, delta, status: exp == null ? 'expected-unavailable' : abs <= 0.0001 ? 'pass' : abs <= 0.001 ? 'close' : 'fail' };
  });
}

async function runSmoke() {
  const smokeRun = path.join(RUNS_DIR, 'run.cacm.bm25.txt');
  const smokeEval = path.join(RUNS_DIR, 'eval.cacm.bm25.txt');
  const search = await runLogged('fatjar verification: CACM SearchCollection smoke test', 'java', javaArgs('io.anserini.search.SearchCollection', ['-threads', '1', '-index', 'cacm', '-topics', 'cacm', '-output', smokeRun, '-hits', '1000', '-bm25']), { artifacts: [smokeRun] });
  if (search.code !== 0 || !fs.existsSync(smokeRun)) throw new Error('CACM SearchCollection smoke test failed');
  const evalRes = await runLogged('fatjar verification: CACM TrecEval smoke test', 'java', javaArgs('io.anserini.eval.TrecEval', ['-c', '-m', 'map', '-m', 'P.30', 'cacm', smokeRun]), { artifacts: [smokeRun, smokeEval] });
  fs.writeFileSync(smokeEval, evalRes.stdout);
  if (evalRes.code !== 0 || !/map\s+all\s+0\.3123/.test(evalRes.stdout) || !/P_30\s+all\s+0\.1942/.test(evalRes.stdout)) throw new Error('CACM TrecEval smoke metrics did not match expected MAP 0.3123 / P30 0.1942');
  state.anserini.smoke = { status: 'ok', runFile: smokeRun, evalFile: smokeEval, expected: { map: 0.3123, P_30: 0.1942 }, outputPreview: preview(evalRes.stdout) };
}

async function discoverReproduction() {
  state.reproduction.status = 'running';
  const list = await runLogged('reproduction discovery: list prebuilt configs', 'java', javaArgs('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--list']));
  if (list.code !== 0) throw new Error('Unable to list Anserini prebuilt reproduction configs');
  const show = await runLogged('reproduction discovery: show BEIR core config', 'java', javaArgs('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--config', DATASET.reproductionConfig, '--show']));
  if (show.code !== 0) throw new Error('Unable to show beir.core reproduction config');
  const dry = await runLogged('reproduction discovery: dry-run BEIR core config', 'java', javaArgs('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--config', DATASET.reproductionConfig, '--dry-run']));
  if (dry.code !== 0) throw new Error('Unable to dry-run beir.core reproduction config');
  const parsed = parseNfcorpusReproduction(show.stdout);
  state.reproduction.expected = parsed.expected;
  state.reproduction.metricDefinitions = parsed.metricDefinitions;
  state.reproduction.commandTemplate = parsed.commandTemplate;
  state.reproduction.showPreview = preview(show.stdout);
  state.reproduction.dryRunPreview = preview(dry.stdout);
  state.reproduction.status = Object.keys(parsed.expected).length ? 'ok' : 'ok-no-expected-metrics';
  state.evaluation.expected = parsed.expected;
}

async function runEvaluation(fresh = true) {
  state.evaluation.status = 'running';
  state.evaluation.error = null;
  const started = Date.now();
  fs.mkdirSync(RUNS_DIR, { recursive: true });
  const search = await runLogged('BM25 retrieval: NFCorpus SearchCollection', 'java', javaArgs('io.anserini.search.SearchCollection', ['-threads', '1', '-index', DATASET.index, '-topics', DATASET.topics, '-output', DATASET.runFile, '-bm25', '-removeQuery', '-hits', '1000']), { artifacts: [DATASET.runFile] });
  if (search.code !== 0 || !fs.existsSync(DATASET.runFile)) throw new Error('NFCorpus BM25 SearchCollection failed');
  state.nfcorpus.indexStatus = 'ready via prebuilt Anserini index';
  const evalArgs = ['-c', '-m', 'ndcg_cut.10', state.reproduction.evalKey || DATASET.evalKey, DATASET.runFile];
  const evalRes = await runLogged('evaluation: NFCorpus TrecEval nDCG@10', 'java', javaArgs('io.anserini.eval.TrecEval', evalArgs), { artifacts: [DATASET.runFile, DATASET.evalFile] });
  fs.writeFileSync(DATASET.evalFile, evalRes.stdout);
  if (evalRes.code !== 0) throw new Error('NFCorpus TrecEval failed');
  const observed = parseEvalOutput(evalRes.stdout);
  state.evaluation.observed = observed;
  state.evaluation.expected = state.reproduction.expected;
  state.evaluation.comparisons = buildComparisons(observed, state.reproduction.expected);
  state.evaluation.elapsedMs = Date.now() - started;
  state.evaluation.fresh = fresh;
  state.evaluation.status = Object.keys(observed).length ? 'ok' : 'failed';
  state.evaluation.outputPreview = preview(evalRes.stdout);
  if (!Object.keys(observed).length) throw new Error('No numeric metric parsed from TrecEval output');
  state.nfcorpus.evaluationAvailable = true;
}

async function verifyLiveSearchSetup() {
  const res = await runLogged('NFCorpus search setup: one-hit Anserini CLI Search', 'java', javaArgs('io.anserini.cli.Search', ['--index', DATASET.index, '--query', 'vitamin d cancer', '--hits', '1', '--json']));
  if (res.code !== 0) throw new Error('NFCorpus CLI Search setup failed');
  state.nfcorpus.searchAvailable = true;
}

async function initialize() {
  ensureDirs();
  try {
    state.anserini.status = 'checking-java';
    const java = await runLogged('fatjar verification: java -version', 'java', ['-version']);
    state.anserini.java = (java.stderr || java.stdout).trim().split(/\r?\n/)[0] || null;
    if (java.code !== 0 || !/version\s+"21\./.test(java.stderr || java.stdout)) throw new Error(`Java 21 is required. Observed: ${java.stderr || java.stdout}`);

    state.anserini.status = 'downloading-fatjar';
    const version = await resolveAnseriniVersion();
    state.anserini.version = version;
    state.anserini.jar = await downloadJar(version);

    state.anserini.status = 'verifying-fatjar';
    await runSmoke();
    state.anserini.available = true;
    state.anserini.status = 'ok';

    await discoverReproduction();
    await runEvaluation(true);
    await verifyLiveSearchSetup();

    state.nfcorpus.status = 'ready';
    state.nfcorpus.ready = true;
    state.app.status = 'ready';
  } catch (err) {
    state.app.status = 'error';
    state.app.errors.push(err.stack || err.message);
    state.anserini.error = err.message;
    state.nfcorpus.status = state.nfcorpus.ready ? state.nfcorpus.status : 'error';
    state.reproduction.error = state.reproduction.error || err.message;
    state.evaluation.error = state.evaluation.error || err.message;
    console.error(err);
  }
}

function extractJson(stdout, stderr) {
  const combined = `${stdout || ''}\n${stderr || ''}`;
  const start = combined.indexOf('{');
  const end = combined.lastIndexOf('}');
  if (start === -1 || end === -1 || end < start) throw new Error('Anserini Search did not emit JSON');
  return JSON.parse(combined.slice(start, end + 1));
}

async function search(query, hits) {
  if (!state.anserini.available || !state.nfcorpus.searchAvailable) throw new Error('NFCorpus search is not ready yet');
  const safeHits = String(Math.max(1, Math.min(Number(hits || 5), 20)));
  const res = await runLogged('live search: NFCorpus Anserini CLI Search', 'java', javaArgs('io.anserini.cli.Search', ['--index', DATASET.index, '--query', query, '--hits', safeHits, '--json']));
  if (res.code !== 0) throw new Error(res.stderr || res.stdout || 'Search failed');
  const json = extractJson(res.stdout, res.stderr);
  const results = (json.candidates || []).map((c, i) => {
    const doc = c.doc || {};
    const text = doc.text || doc.contents || doc.raw || '';
    const title = doc.title || '';
    return { rank: i + 1, docid: c.docid, score: c.score, title, snippet: preview(`${title ? title + ' — ' : ''}${text}`.replace(/\s+/g, ' '), 500), url: doc.metadata && doc.metadata.url, content: preview(text, 1200) };
  });
  return { query, index: DATASET.index, command: res.entry.command, commandId: res.entry.id, backedBy: 'Anserini io.anserini.cli.Search --json', results };
}

function statusPayload() {
  return {
    app: state.app,
    anserini: state.anserini,
    nfcorpus: state.nfcorpus,
    dataset: state.dataset,
    reproduction: state.reproduction,
    evaluation: state.evaluation,
    commands: state.commands
  };
}

function healthPayload() {
  return {
    status: state.app.status,
    anseriniAvailable: state.anserini.available,
    nfcorpusReady: state.nfcorpus.ready,
    searchAvailable: state.nfcorpus.searchAvailable,
    evaluationAvailable: state.nfcorpus.evaluationAvailable,
    dataset: state.dataset.name,
    activeIndex: state.dataset.index,
    portBinding: `0.0.0.0:${PORT}`
  };
}

function sendJson(res, code, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  res.end(body);
}

function serveStatic(req, res, pathname) {
  let file = pathname === '/' ? path.join(ROOT, 'public', 'index.html') : path.join(ROOT, 'public', pathname.replace(/^\/+/, ''));
  if (!file.startsWith(path.join(ROOT, 'public'))) {
    res.writeHead(403); res.end('forbidden'); return;
  }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    const ext = path.extname(file);
    const type = ext === '.html' ? 'text/html' : ext === '.css' ? 'text/css' : ext === '.js' ? 'application/javascript' : 'text/plain';
    res.writeHead(200, { 'content-type': `${type}; charset=utf-8` });
    res.end(data);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  try {
    if (url.pathname === '/health') return sendJson(res, 200, healthPayload());
    if (url.pathname === '/api/status') return sendJson(res, 200, statusPayload());
    if (url.pathname === '/api/commands') return sendJson(res, 200, { commands: state.commands });
    if (url.pathname === '/api/search') {
      const q = (url.searchParams.get('q') || '').trim();
      if (!q) return sendJson(res, 400, { error: 'query parameter q is required' });
      const result = await search(q, url.searchParams.get('hits'));
      return sendJson(res, 200, result);
    }
    if (url.pathname === '/api/evaluate' && req.method === 'POST') {
      await runEvaluation(true);
      return sendJson(res, 200, state.evaluation);
    }
    return serveStatic(req, res, url.pathname);
  } catch (err) {
    return sendJson(res, 500, { error: err.message, stack: process.env.NODE_ENV === 'production' ? undefined : err.stack });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`NFCorpus diagnostics workbench listening on http://${HOST}:${PORT}`);
  initialize();
});
