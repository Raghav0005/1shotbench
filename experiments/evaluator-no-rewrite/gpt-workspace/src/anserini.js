import { spawn } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');
export const ARTIFACT_ROOT = path.join(ROOT, 'runs', 'evaluations');

const CACM_PAIRING = {
  index: 'cacm',
  topics: 'cacm',
  qrels: 'cacm',
  qrelsLabel: 'Anserini built-in CACM qrels key: cacm',
  source: 'Repo-local Anserini skills: install-anserini-fatjar and anserini-cli CACM SearchCollection/TrecEval workflow',
  retrieval: {
    model: 'BM25',
    args: ['-bm25', '-hits', '1000', '-threads', '1']
  },
  metrics: [
    { label: 'nDCG@10', id: 'ndcg_cut.10', outputName: 'ndcg_cut_10' },
    { label: 'Recall@1000', id: 'recall.1000', outputName: 'recall_1000' },
    { label: 'MAP', id: 'map', outputName: 'map' },
    { label: 'P@30', id: 'P.30', outputName: 'P_30' }
  ]
};

let catalogCache;
let catalogCacheAt = 0;
const CATALOG_TTL_MS = 5 * 60 * 1000;

export function findAnseriniJar() {
  if (process.env.ANSERINI_JAR) {
    return path.resolve(process.env.ANSERINI_JAR);
  }
  return null;
}

export async function locateAnseriniJar() {
  const envJar = findAnseriniJar();
  if (envJar) {
    await assertFile(envJar, `ANSERINI_JAR points to missing file: ${envJar}`);
    return envJar;
  }

  const toolsDir = path.join(ROOT, 'tools');
  let entries = [];
  try {
    entries = await fs.readdir(toolsDir);
  } catch {
    // handled below
  }
  const jars = entries
    .filter((name) => /^anserini-.*-fatjar\.jar$/.test(name))
    .sort()
    .reverse();
  if (jars.length > 0) {
    return path.join(toolsDir, jars[0]);
  }

  throw new Error('No Anserini fatjar found. Set ANSERINI_JAR or run `npm run anserini:setup`.');
}

async function assertFile(filePath, message) {
  try {
    const stat = await fs.stat(filePath);
    if (!stat.isFile()) throw new Error(message);
  } catch {
    throw new Error(message);
  }
}

export async function runCommand(args, options = {}) {
  const cwd = options.cwd || ROOT;
  const timeoutMs = options.timeoutMs ?? 120_000;
  return await new Promise((resolve, reject) => {
    const child = spawn(args[0], args.slice(1), { cwd, env: process.env });
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    }, timeoutMs);

    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const result = { args, code, stdout, stderr, timedOut };
      if (timedOut) {
        reject(Object.assign(new Error(`Command timed out after ${timeoutMs}ms: ${args.join(' ')}`), { result }));
      } else if (code !== 0) {
        reject(Object.assign(new Error(`Command failed (${code}): ${args.join(' ')}`), { result }));
      } else {
        resolve(result);
      }
    });
  });
}

export async function javaVersion() {
  try {
    const result = await runCommand(['java', '-version'], { timeoutMs: 15_000 });
    return (result.stderr || result.stdout).trim();
  } catch (error) {
    throw new Error(`Java is unavailable or not runnable: ${error.message}`);
  }
}

export async function anseriniCommand(mainClass, classArgs, options = {}) {
  const jar = options.jar || await locateAnseriniJar();
  return await runCommand(['java', '-cp', jar, mainClass, ...classArgs], options);
}

function parseJsonCommand(result, label) {
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`${label} did not return parseable JSON. stdout preview: ${result.stdout.slice(0, 500)}`);
  }
}

export async function loadCatalog({ force = false } = {}) {
  const now = Date.now();
  if (!force && catalogCache && now - catalogCacheAt < CATALOG_TTL_MS) {
    return catalogCache;
  }

  const jar = await locateAnseriniJar();
  const java = await javaVersion();
  const [indexResult, topicResult] = await Promise.all([
    anseriniCommand('io.anserini.cli.PrebuiltIndexRegistry', ['--list', '--type', 'inverted'], { jar, timeoutMs: 120_000 }),
    anseriniCommand('io.anserini.cli.TopicsRegistry', ['--list'], { jar, timeoutMs: 120_000 })
  ]);

  const registryIndexes = parseJsonCommand(indexResult, 'PrebuiltIndexRegistry --list --type inverted');
  const topics = parseJsonCommand(topicResult, 'TopicsRegistry --list');
  const topicsSet = new Set(topics);

  const indexes = registryIndexes.map((item) => {
    const isCacm = item.name === CACM_PAIRING.index;
    const pairing = isCacm && topicsSet.has(CACM_PAIRING.topics) ? CACM_PAIRING : null;
    return {
      name: item.name,
      type: item.type,
      corpusIndex: item.corpus_index,
      description: item.description || '',
      filename: item.filename || '',
      readme: item.readme || '',
      size: item.size ?? null,
      documents: item.documents ?? null,
      uniqueTerms: item.unique_terms ?? null,
      totalTerms: item.total_terms ?? null,
      evaluable: Boolean(pairing),
      status: pairing ? 'Ready for evaluation' : 'Catalog only',
      catalogOnlyReason: pairing ? '' : 'No automatic topics/qrels pairing is configured for this local app.',
      pairing
    };
  }).sort((a, b) => {
    if (a.name === 'cacm') return -1;
    if (b.name === 'cacm') return 1;
    return a.name.localeCompare(b.name);
  });

  if (!indexes.some((item) => item.name === CACM_PAIRING.index)) {
    throw new Error('The Anserini prebuilt-index registry did not expose the required CACM prebuilt inverted index.');
  }

  catalogCache = {
    generatedAt: new Date().toISOString(),
    java,
    fatjar: jar,
    indexRegistryCommand: ['java', '-cp', jar, 'io.anserini.cli.PrebuiltIndexRegistry', '--list', '--type', 'inverted'],
    topicsRegistryCommand: ['java', '-cp', jar, 'io.anserini.cli.TopicsRegistry', '--list'],
    defaultIndex: 'cacm',
    topicsCount: topics.length,
    topicsPreview: topics.slice(0, 50),
    indexes
  };
  catalogCacheAt = now;
  return catalogCache;
}

export function getMetric(pairing, metricId) {
  return pairing.metrics.find((metric) => metric.id === metricId || metric.label === metricId);
}

function parseMetricScore(evalOutput, metric) {
  const lines = evalOutput.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const wanted = new Set([metric.outputName, metric.id.replaceAll('.', '_')]);
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3 && wanted.has(parts[0])) {
      const score = Number(parts[2]);
      if (Number.isFinite(score)) return { score, line };
    }
  }
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3) {
      const score = Number(parts[2]);
      if (Number.isFinite(score)) return { score, line };
    }
  }
  throw new Error(`Unable to parse a numeric ${metric.label} score from evaluator output: ${evalOutput}`);
}

function commandString(args) {
  return args.map((arg) => /\s/.test(arg) ? JSON.stringify(arg) : arg).join(' ');
}

export async function runEvaluation({ indexName, metricId }) {
  const catalog = await loadCatalog();
  const selected = catalog.indexes.find((item) => item.name === indexName);
  if (!selected) throw new Error(`Unknown index: ${indexName}`);
  if (!selected.evaluable || !selected.pairing) {
    throw new Error(`${indexName} is catalog-only in this app: ${selected.catalogOnlyReason}`);
  }
  const metric = getMetric(selected.pairing, metricId);
  if (!metric) throw new Error(`Metric ${metricId} is unavailable for ${indexName}.`);

  const jar = await locateAnseriniJar();
  await fs.mkdir(ARTIFACT_ROOT, { recursive: true });
  const runId = `${new Date().toISOString().replace(/[:.]/g, '-')}-${crypto.randomBytes(4).toString('hex')}`;
  const artifactDir = path.join(ARTIFACT_ROOT, runId);
  await fs.mkdir(artifactDir, { recursive: true });
  const runPath = path.join(artifactDir, `run.${indexName}.bm25.txt`);
  const evalPath = path.join(artifactDir, `eval.${indexName}.${metric.outputName}.txt`);
  const searchLogPath = path.join(artifactDir, 'search.log');

  const searchArgs = [
    'java', '-cp', jar, 'io.anserini.search.SearchCollection',
    '-threads', '1',
    '-index', selected.pairing.index,
    '-topics', selected.pairing.topics,
    '-output', runPath,
    '-hits', '1000',
    '-bm25'
  ];
  const evalArgs = [
    'java', '-cp', jar, 'io.anserini.eval.TrecEval',
    '-c',
    '-m', metric.id,
    selected.pairing.qrels,
    runPath
  ];

  const started = Date.now();
  let searchResult;
  let evalResult;
  try {
    searchResult = await runCommand(searchArgs, { timeoutMs: 10 * 60 * 1000 });
    await fs.writeFile(searchLogPath, `${searchResult.stdout}\n${searchResult.stderr}`.trim() + '\n');
    evalResult = await runCommand(evalArgs, { timeoutMs: 2 * 60 * 1000 });
    await fs.writeFile(evalPath, evalResult.stdout.trim() + '\n');
  } catch (error) {
    if (error.result) {
      const failurePath = path.join(artifactDir, 'failure.log');
      await fs.writeFile(failurePath, `${error.message}\n\nSTDOUT\n${error.result.stdout}\n\nSTDERR\n${error.result.stderr}`);
      error.artifactDir = artifactDir;
      error.failurePath = failurePath;
    }
    throw error;
  }

  const elapsedMs = Date.now() - started;
  const evalText = await fs.readFile(evalPath, 'utf8');
  const parsed = parseMetricScore(evalText, metric);
  const runStat = await fs.stat(runPath);

  return {
    status: 'completed',
    runId,
    score: parsed.score,
    scoreLine: parsed.line,
    elapsedMs,
    selectedIndex: selected.name,
    topics: selected.pairing.topics,
    qrels: selected.pairing.qrels,
    qrelsLabel: selected.pairing.qrelsLabel,
    metric: { label: metric.label, id: metric.id, outputName: metric.outputName },
    retrievalModel: selected.pairing.retrieval.model,
    runPath,
    evalPath,
    searchLogPath,
    artifactDir,
    runBytes: runStat.size,
    evalPreview: evalText.trim().split(/\r?\n/).slice(0, 20),
    commands: {
      search: commandString(searchArgs),
      evaluate: commandString(evalArgs)
    }
  };
}
