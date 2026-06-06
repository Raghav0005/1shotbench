// Wraps Anserini CLI commands that inspect the prebuilt-index and topics
// registries. No catalog data is hardcoded here; we always ask the Anserini
// fatjar for the truth.

const { spawn } = require('child_process');
const path = require('path');

const FATJAR_ENV = 'ANSERINI_JAR';

function jarPath() {
  const p = process.env[FATJAR_ENV];
  if (!p) {
    throw new Error(
      `${FATJAR_ENV} is not set. Point it at the downloaded anserini-*-fatjar.jar.`
    );
  }
  return p;
}

function runJava(args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn('java', ['-cp', jarPath(), ...args], {
      stdio: ['ignore', 'pipe', 'pipe'],
      ...opts,
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

// Returns the parsed list of prebuilt indexes. Filters to type === 'inverted'
// because those are the ones that can be evaluated with trec_eval in this
// app. Other types (flat, hnsw, impact) are vector indexes and would need
// dense retrieval machinery that Anserini does not exercise via TrecEval.
async function listInvertedIndexes() {
  const { code, stdout, stderr } = await runJava([
    'io.anserini.cli.PrebuiltIndexRegistry',
    '--list',
  ]);
  if (code !== 0) {
    throw new Error(
      `PrebuiltIndexRegistry --list failed (exit ${code}): ${stderr.trim()}`
    );
  }
  let all;
  try {
    all = JSON.parse(stdout);
  } catch (err) {
    throw new Error(
      `PrebuiltIndexRegistry --list did not return valid JSON: ${err.message}\nFirst 200 chars: ${stdout.slice(
        0,
        200
      )}`
    );
  }
  return all.filter((e) => e && e.type === 'inverted');
}

// Returns the parsed list of all topics known to Anserini.
async function listTopics() {
  const { code, stdout, stderr } = await runJava([
    'io.anserini.cli.TopicsRegistry',
    '--list',
  ]);
  if (code !== 0) {
    throw new Error(
      `TopicsRegistry --list failed (exit ${code}): ${stderr.trim()}`
    );
  }
  let topics;
  try {
    topics = JSON.parse(stdout);
  } catch (err) {
    throw new Error(
      `TopicsRegistry --list did not return valid JSON: ${err.message}\nFirst 200 chars: ${stdout.slice(
        0,
        200
      )}`
    );
  }
  // TopicsRegistry --list emits a flat array of strings, but defensively
  // tolerate objects with a `name` field too.
  return topics.map((t) => (typeof t === 'string' ? t : t.name)).filter(Boolean);
}

module.exports = {
  jarPath,
  runJava,
  listInvertedIndexes,
  listTopics,
};
