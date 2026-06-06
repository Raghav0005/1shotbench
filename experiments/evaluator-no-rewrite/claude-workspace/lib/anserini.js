/**
 * Thin wrapper around the Anserini fatjar CLI.
 *
 * This module never mocks Anserini output. Every function in this file
 * shells out to `java -cp $ANSERINI_JAR <main-class>` and returns the
 * raw stdout/stderr so callers can verify they are using real Anserini.
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const DEFAULT_JAR_DIR = path.join(__dirname, '..', 'anserini');

/**
 * Resolve the Anserini fatjar location.
 *
 * Order of resolution:
 *   1. ANSERINI_JAR env var, if set and points to an existing file.
 *   2. The single anserini-*-fatjar.jar file under ./anserini/.
 */
function resolveAnseriniJar() {
  const fromEnv = process.env.ANSERINI_JAR;
  if (fromEnv && fs.existsSync(fromEnv)) {
    return fromEnv;
  }
  if (fs.existsSync(DEFAULT_JAR_DIR)) {
    const matches = fs
      .readdirSync(DEFAULT_JAR_DIR)
      .filter((f) => /^anserini-.*-fatjar\.jar$/.test(f));
    if (matches.length > 0) {
      return path.join(DEFAULT_JAR_DIR, matches[0]);
    }
  }
  throw new Error(
    'Could not locate the Anserini fatjar. Set ANSERINI_JAR or place an ' +
      'anserini-*-fatjar.jar file under ./anserini/.'
  );
}

/**
 * Run a Java main class against the Anserini fatjar.
 *
 * @param {string} mainClass  Fully-qualified main class name.
 * @param {string[]} args     CLI args passed after the main class.
 * @param {object} [options]
 * @param {string} [options.cwd]      Working directory for the spawned process.
 * @param {number} [options.timeoutMs] Hard timeout in ms (default: 30 min).
 * @returns {Promise<{stdout: string, stderr: string, code: number, command: string, durationMs: number}>}
 */
function runJava(mainClass, args, options = {}) {
  const jar = resolveAnseriniJar();
  const cwd = options.cwd || process.cwd();
  const timeoutMs = options.timeoutMs || 30 * 60 * 1000;
  const fullArgs = ['-cp', jar, mainClass, ...args];
  const commandStr = `java -cp ${jar} ${mainClass} ${args.join(' ')}`;
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const child = spawn('java', fullArgs, { cwd });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error(`Anserini command timed out after ${timeoutMs}ms: ${commandStr}`));
    }, timeoutMs);
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('error', (err) => {
      clearTimeout(timer);
      reject(new Error(`Failed to spawn java: ${err.message}`));
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({
        stdout,
        stderr,
        code: code == null ? -1 : code,
        command: commandStr,
        durationMs: Date.now() - start,
      });
    });
  });
}

async function runJavaJson(mainClass, args, options) {
  const res = await runJava(mainClass, args, options);
  if (res.code !== 0) {
    throw new Error(
      `${mainClass} exited with code ${res.code}\nstderr:\n${res.stderr}`
    );
  }
  try {
    return JSON.parse(res.stdout);
  } catch (err) {
    throw new Error(
      `${mainClass} did not return valid JSON: ${err.message}\nstdout:\n${res.stdout.slice(0, 2000)}`
    );
  }
}

async function verifyJava() {
  return new Promise((resolve) => {
    const child = spawn('java', ['-version']);
    let stderr = '';
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('error', () => resolve({ ok: false, version: null, message: 'java not found on PATH' }));
    child.on('close', (code) => {
      if (code !== 0) {
        resolve({ ok: false, version: null, message: stderr.trim() || 'java -version failed' });
        return;
      }
      const m = stderr.match(/version "(\d+)(?:\.(\d+))?(?:\.(\d+))?/);
      const major = m ? parseInt(m[1], 10) : null;
      resolve({
        ok: major != null && major >= 21,
        version: stderr.split('\n')[0].trim(),
        message: major != null && major < 21
          ? `Java ${major} detected; Anserini requires Java 21+`
          : null,
      });
    });
  });
}

function verifyAnseriniJar() {
  try {
    const jar = resolveAnseriniJar();
    return { ok: true, jar };
  } catch (err) {
    return { ok: false, jar: null, message: err.message };
  }
}

// ---------- Registry / reproduce helpers ----------

async function listPrebuiltIndexes(type = 'inverted') {
  return runJavaJson('io.anserini.cli.PrebuiltIndexRegistry', ['--type', type, '--list']);
}

async function listTopics() {
  return runJavaJson('io.anserini.cli.TopicsRegistry', ['--list']);
}

async function listReproduceConfigs() {
  return runJavaJson('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', ['--list']);
}

async function showReproduceConfig(name) {
  const res = await runJava('io.anserini.reproduce.ReproduceFromPrebuiltIndexes', [
    '--config', name, '--show',
  ]);
  if (res.code !== 0) {
    throw new Error(`Failed to show reproduce config ${name}: ${res.stderr}`);
  }
  return res.stdout;
}

// ---------- Retrieval / eval ----------

async function searchCollection({ index, topics, output, hits = 1000, threads = 1, bm25 = true }) {
  const args = [
    '-threads', String(threads),
    '-index', index,
    '-topics', topics,
    '-output', output,
    '-hits', String(hits),
  ];
  if (bm25) args.push('-bm25');
  return runJava('io.anserini.search.SearchCollection', args);
}

/**
 * Evaluate a TREC run using io.anserini.eval.TrecEval.
 *
 * @param {object} params
 * @param {string[]} params.metricArgs   The exact `-c -m ...` args from the
 *                                       reproduction config or user metric.
 * @param {string} params.qrels          The eval/qrels symbol (e.g. "cacm").
 * @param {string} params.runFile        Path to the TREC run file.
 */
async function trecEval({ metricArgs, qrels, runFile }) {
  const args = [...metricArgs, qrels, runFile];
  return runJava('io.anserini.eval.TrecEval', args);
}

module.exports = {
  resolveAnseriniJar,
  runJava,
  runJavaJson,
  verifyJava,
  verifyAnseriniJar,
  listPrebuiltIndexes,
  listTopics,
  listReproduceConfigs,
  showReproduceConfig,
  searchCollection,
  trecEval,
};
