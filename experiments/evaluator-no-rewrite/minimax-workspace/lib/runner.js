// Runs Anserini retrieval and evaluation against a downloaded fatjar.
//
// The flow is:
//   1. Run `io.anserini.search.SearchCollection` to produce a TREC run file.
//   2. Run `io.anserini.eval.TrecEval` against that run file with the
//      qrels and metric the user selected.
//   3. Return enough metadata for the UI to display what happened.

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { runJava, jarPath } = require('./registry');
const { metricFlag } = require('./metrics');

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function timestamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() +
    pad(d.getUTCMonth() + 1) +
    pad(d.getUTCDate()) +
    '-' +
    pad(d.getUTCHours()) +
    pad(d.getUTCMinutes()) +
    pad(d.getUTCSeconds())
  );
}

function streamToString(stream) {
  return new Promise((resolve, reject) => {
    let buf = '';
    stream.on('data', (chunk) => (buf += chunk.toString()));
    stream.on('end', () => resolve(buf));
    stream.on('error', reject);
  });
}

async function runChild(command, args, { cwd, env } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, ...(env || {}) },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d.toString()));
    child.stderr.on('data', (d) => (stderr += d.toString()));
    child.on('error', reject);
    child.on('close', (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

function runJavaStreamed(args, onLog) {
  // Stream stderr from SearchCollection to the caller so the UI can
  // surface progress, but resolve only on close.
  return new Promise((resolve, reject) => {
    const child = spawn('java', ['-cp', jarPath(), ...args], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => {
      const s = d.toString();
      stdout += s;
      if (onLog) onLog('stdout', s);
    });
    child.stderr.on('data', (d) => {
      const s = d.toString();
      stderr += s;
      if (onLog) onLog('stderr', s);
    });
    child.on('error', reject);
    child.on('close', (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

async function retrieve({ index, topics, runFile, onLog }) {
  // `-threads 1` keeps runs deterministic and avoids surprising the
  // smoke test; `-bm25` is the standard CACM default and matches the
  // reproduction guide. `-hits 1000` matches the nDCG@10 / Recall@1000
  // expectations.
  const args = [
    'io.anserini.search.SearchCollection',
    '-threads',
    '1',
    '-index',
    index,
    '-topics',
    topics,
    '-output',
    runFile,
    '-hits',
    '1000',
    '-bm25',
  ];
  const started = Date.now();
  const result = await runJavaStreamed(args, onLog);
  const elapsedMs = Date.now() - started;
  return { ...result, elapsedMs, args };
}

async function evaluate({ qrels, metric, runFile, evalFile, onLog }) {
  const flag = metricFlag(metric);
  const args = [
    'io.anserini.eval.TrecEval',
    '-c',
    '-m',
    flag,
    qrels,
    runFile,
  ];
  const started = Date.now();
  const { code, stdout, stderr } = await runJavaStreamed(args, onLog);
  const elapsedMs = Date.now() - started;
  if (code !== 0) {
    throw new Error(
      `TrecEval exited with code ${code}: ${stderr.trim() || stdout.trim()}`
    );
  }
  fs.writeFileSync(evalFile, stdout);
  return { code, stdout, stderr, elapsedMs, args, evalFile };
}

function parseEvalOutput(text, flag) {
  // TrecEval output looks like:
  //   map                   	all	0.3123
  //   ndcg_cut_10           	all	0.4543
  // Split on whitespace, find rows whose second column is `all` and whose
  // first column starts with the same identifier we requested (modulo
  // the dot-to-underscore rewrite TrecEval performs).
  const expected = flag.replace(/\./g, '_');
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3 && parts[0] === expected && parts[1] === 'all') {
      const v = Number(parts[2]);
      if (!Number.isNaN(v)) {
        return { value: v, measure: parts[0] };
      }
    }
  }
  // Fallback: return the first numeric `all` row we can find.
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3 && parts[1] === 'all') {
      const v = Number(parts[2]);
      if (!Number.isNaN(v)) {
        return { value: v, measure: parts[0] };
      }
    }
  }
  return null;
}

async function runEvaluation({ index, topics, qrels, metric, runsDir, evalsDir, onLog }) {
  ensureDir(runsDir);
  ensureDir(evalsDir);
  const stamp = timestamp();
  const runFile = path.join(runsDir, `run.${index}.${topics}.${stamp}.txt`);
  const evalFile = path.join(
    evalsDir,
    `eval.${index}.${topics}.${metric.replace(/[^A-Za-z0-9@]/g, '_')}.${stamp}.txt`
  );

  const retrieval = await retrieve({
    index,
    topics,
    runFile,
    onLog,
  });
  if (retrieval.code !== 0) {
    const err = new Error(
      `SearchCollection exited with code ${retrieval.code}: ${retrieval.stderr.trim()}`
    );
    err.phase = 'retrieval';
    err.stdout = retrieval.stdout;
    err.stderr = retrieval.stderr;
    throw err;
  }
  if (!fs.existsSync(runFile)) {
    const err = new Error(
      `SearchCollection exited 0 but did not produce ${runFile}`
    );
    err.phase = 'retrieval';
    err.stdout = retrieval.stdout;
    err.stderr = retrieval.stderr;
    throw err;
  }
  const runStat = fs.statSync(runFile);
  const runPreview = headLines(runFile, 5);

  const ev = await evaluate({ qrels, metric, runFile, evalFile, onLog });
  const parsed = parseEvalOutput(ev.stdout, metricFlag(metric));
  return {
    score: parsed ? parsed.value : null,
    scoreMeasure: parsed ? parsed.measure : null,
    runFile,
    runFileBytes: runStat.size,
    runPreview,
    evalFile,
    evalOutput: ev.stdout,
    metrics: {
      retrievalMs: retrieval.elapsedMs,
      evaluationMs: ev.elapsedMs,
    },
    commands: {
      retrieval: ['java', '-cp', jarPath(), ...retrieval.args],
      evaluation: ['java', '-cp', jarPath(), ...ev.args],
    },
  };
}

function headLines(file, n) {
  const data = fs.readFileSync(file, 'utf8');
  return data.split(/\r?\n/).slice(0, n).join('\n');
}

module.exports = {
  runEvaluation,
  parseEvalOutput,
};
