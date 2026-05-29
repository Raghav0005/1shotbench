#!/usr/bin/env node

/**
 * Anserini Prebuilt Index Evaluator
 *
 * A local web application for browsing Anserini's prebuilt Lucene inverted
 * indexes and running reproducible retrieval evaluations.
 *
 * Uses the Anserini fatjar CLI for catalog discovery, retrieval, and evaluation.
 */

const express = require('express');
const path = require('path');
const fs = require('fs');
const { execSync, spawn } = require('child_process');
const crypto = require('crypto');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PORT = process.env.PORT || 3000;
const ANSERINI_JAR = process.env.ANSERINI_JAR || '';
const WORKSPACE_DIR = __dirname;
const RUNS_DIR = path.join(WORKSPACE_DIR, 'runs');
const EVALS_DIR = path.join(WORKSPACE_DIR, 'evals');

// Known evaluable index/topics/qrels pairings discovered from Anserini skills
// and reproduction docs. These may be extended by inspecting the topics registry.
const KNOWN_EVALUABLE_PAIRINGS = {
  // CACM: built-in prebuilt index, topics, and qrels
  cacm: {
    indexName: 'cacm',
    displayName: 'CACM (default)',
    description: 'CACM collection prebuilt index — small, fast, ideal for smoke tests',
    topics: 'cacm',
    qrelsId: 'cacm',
    defaultMetrics: ['nDCG@10', 'Recall@1000', 'MAP', 'P@30'],
  },
};

// Metric mapping: user-facing labels -> trec_eval metric flags
const METRIC_MAP = {
  'nDCG@10': '-m ndcg_cut.10',
  'Recall@1000': '-m recall.1000',
  MAP: '-m map',
  'P@30': '-m P.30',
  'P@10': '-m P.10',
  'Recall@100': '-m recall.100',
  'nDCG@20': '-m ndcg_cut.20',
};

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function getJavaVersion() {
  try {
    const out = execSync('java -version 2>&1', { encoding: 'utf8', timeout: 10000 });
    const match = out.match(/(\d+)\.?(\d+)?\.?(\d+)?/);
    if (match) return parseInt(match[1], 10);
    return 0;
  } catch {
    return 0;
  }
}

function isFatjarAvailable() {
  if (!ANSERINI_JAR || !fs.existsSync(ANSERINI_JAR)) {
    // Try to find a fatjar in the workspace
    const files = fs.readdirSync(WORKSPACE_DIR).filter((f) => f.endsWith('-fatjar.jar'));
    if (files.length > 0) {
      const found = path.join(WORKSPACE_DIR, files[0]);
      console.log(`Found fatjar: ${found}`);
      process.env.ANSERINI_JAR = found;
      return true;
    }
    // Try .env file
    const envPath = path.join(WORKSPACE_DIR, '.env');
    if (fs.existsSync(envPath)) {
      const envContent = fs.readFileSync(envPath, 'utf8');
      const match = envContent.match(/ANSERINI_JAR=(.+)/);
      if (match && fs.existsSync(match[1].trim())) {
        process.env.ANSERINI_JAR = match[1].trim();
        return true;
      }
    }
    return false;
  }
  return true;
}

function resolveFatjarPath() {
  if (ANSERINI_JAR && fs.existsSync(ANSERINI_JAR)) return ANSERINI_JAR;
  const envJar = process.env.ANSERINI_JAR;
  if (envJar && fs.existsSync(envJar)) return envJar;
  const files = fs.readdirSync(WORKSPACE_DIR).filter((f) => f.endsWith('-fatjar.jar'));
  if (files.length > 0) return path.join(WORKSPACE_DIR, files[0]);
  return null;
}

function runJavaCmd(mainClass, args, options = {}) {
  const jar = resolveFatjarPath();
  if (!jar) throw new Error('Anserini fatjar not found. Run setup/install-fatjar.js first.');
  const cmd = `java -cp "${jar}" ${mainClass} ${args.join(' ')}`;
  const opts = {
    cwd: options.cwd || WORKSPACE_DIR,
    encoding: 'utf8',
    timeout: options.timeout || 120000,
    maxBuffer: 10 * 1024 * 1024,
    ...options.execOptions,
  };
  try {
    const stdout = execSync(cmd, opts);
    return { stdout: stdout.toString(), stderr: '', exitCode: 0 };
  } catch (err) {
    return {
      stdout: err.stdout ? err.stdout.toString() : '',
      stderr: err.stderr ? err.stderr.toString() : err.message,
      exitCode: err.status || 1,
    };
  }
}

// ---------------------------------------------------------------------------
// Registry Discovery (real Anserini CLI calls)
// ---------------------------------------------------------------------------

function discoverPrebuiltIndexes() {
  const result = runJavaCmd('io.anserini.cli.PrebuiltIndexRegistry', [
    '--list',
    '--type',
    'inverted',
  ]);

  if (result.exitCode !== 0) {
    console.error('Failed to discover prebuilt indexes:', result.stderr);
    // Fallback: try without --type
    const result2 = runJavaCmd('io.anserini.cli.PrebuiltIndexRegistry', ['--list']);
    if (result2.exitCode !== 0) {
      throw new Error(
        `Cannot discover prebuilt indexes: ${result2.stderr || result2.stdout}`
      );
    }
    return parseRegistryJson(result2.stdout);
  }
  return parseRegistryJson(result.stdout);
}

function parseRegistryJson(stdout) {
  try {
    // Try to parse the entire output as JSON
    const trimmed = stdout.trim();
    // Find where JSON starts
    const jsonStart = trimmed.indexOf('[');
    if (jsonStart >= 0) {
      return JSON.parse(trimmed.substring(jsonStart));
    }
    // Try to find JSON object
    const objStart = trimmed.indexOf('{');
    if (objStart >= 0) {
      const parsed = JSON.parse(trimmed.substring(objStart));
      return Array.isArray(parsed) ? parsed : [parsed];
    }
  } catch (e) {
    console.error('Failed to parse registry JSON:', e.message);
    // Fallback: try line-by-line parsing
    console.log('Raw output:', stdout.substring(0, 2000));
  }
  return [];
}

function discoverTopics() {
  const result = runJavaCmd('io.anserini.cli.TopicsRegistry', ['--list']);
  if (result.exitCode !== 0) {
    console.error('Failed to discover topics:', result.stderr);
    return [];
  }
  return parseRegistryJson(result.stdout);
}

// ---------------------------------------------------------------------------
// Build the index catalog with evaluability info
// ---------------------------------------------------------------------------

function buildCatalog() {
  const indexes = discoverPrebuiltIndexes();
  const topics = discoverTopics();

  // Build lookup from topics
  const topicLookup = {};
  if (Array.isArray(topics)) {
    topics.forEach((t) => {
      if (t && t.id) topicLookup[t.id.toLowerCase()] = t;
    });
  }

  // Build lookup from index names
  const indexLookup = {};
  if (Array.isArray(indexes)) {
    indexes.forEach((idx) => {
      if (idx && idx.name) indexLookup[idx.name.toLowerCase()] = idx;
    });
  }

  // Build catalog, marking known evaluable pairings
  const catalog = [];
  const knownKeys = new Set(Object.keys(KNOWN_EVALUABLE_PAIRINGS).map((k) => k.toLowerCase()));

  if (Array.isArray(indexes)) {
    indexes.forEach((idx) => {
      if (!idx || !idx.name) return;
      const name = idx.name;
      const nameLower = name.toLowerCase();

      // Check if this is a known evaluable pairing
      const pairing = KNOWN_EVALUABLE_PAIRINGS[nameLower];
      if (pairing) {
        catalog.push({
          name: name,
          displayName: pairing.displayName,
          type: idx.type || 'inverted',
          description: idx.description || pairing.description || '',
          evaluable: true,
          topics: pairing.topics,
          qrelsId: pairing.qrelsId,
          availableMetrics: pairing.defaultMetrics,
          filename: idx.filename || '',
          size: idx.size || '',
        });
      } else {
        // Catalog-only index
        const desc = idx.description || '';
        const matchedTopic = topicLookup[nameLower] || topicLookup[nameLower.replace(/[.-]/g, '-')];
        catalog.push({
          name: name,
          displayName: name,
          type: idx.type || 'inverted',
          description: desc,
          evaluable: false,
          topics: null,
          qrelsId: null,
          availableMetrics: [],
          filename: idx.filename || '',
          size: idx.size || '',
          hint: matchedTopic
            ? `Topics available (${matchedTopic.id}) but evaluable pairing not yet mapped`
            : '',
        });
      }
    });
  }

  // Ensure CACM is always present even if registry fails
  if (!catalog.find((c) => c.name.toLowerCase() === 'cacm')) {
    catalog.unshift({
      name: 'cacm',
      displayName: 'CACM (default)',
      type: 'inverted',
      description: 'CACM collection prebuilt index',
      evaluable: true,
      topics: 'cacm',
      qrelsId: 'cacm',
      availableMetrics: ['nDCG@10', 'Recall@1000', 'MAP', 'P@30'],
      filename: '',
      size: '',
    });
  }

  return catalog;
}

// ---------------------------------------------------------------------------
// Run retrieval and evaluation
// ---------------------------------------------------------------------------

function runRetrieval(indexName, topicsId, outputPath) {
  const result = runJavaCmd('io.anserini.search.SearchCollection', [
    '-threads',
    '1',
    '-index',
    indexName,
    '-topics',
    topicsId,
    '-output',
    outputPath,
    '-hits',
    '1000',
    '-bm25',
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Retrieval failed: ${result.stderr || result.stdout}`);
  }

  return result;
}

function runEvaluation(qrelsId, runFilePath, metricFlags) {
  const args = ['-c'];
  metricFlags.forEach((mf) => args.push('-m', mf));
  args.push(qrelsId);
  args.push(runFilePath);

  const result = runJavaCmd('io.anserini.eval.TrecEval', args);

  if (result.exitCode !== 0) {
    throw new Error(`Evaluation failed: ${result.stderr || result.stdout}`);
  }

  return result;
}

function parseEvalScore(evalOutput, metricLabel) {
  // Parse trec_eval output for the named metric
  const lines = evalOutput.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split('\t');
    if (parts.length >= 3) {
      const metricName = parts[0].trim();
      const score = parseFloat(parts[2].trim());
      if (!isNaN(score)) {
        // Check if this metric name matches what we're looking for
        const userMetricLower = metricLabel.toLowerCase().replace(/[@_]/g, '');
        const metricNameLower = metricName.toLowerCase().replace(/[@_]/g, '');
        if (
          metricNameLower === userMetricLower ||
          metricNameLower.includes(userMetricLower) ||
          userMetricLower.includes(metricNameLower)
        ) {
          return score;
        }
        // Also try to find it by known aliases
        if (metricLabel === 'nDCG@10' && metricNameLower.startsWith('ndcg_cut')) {
          const cutMatch = metricName.match(/(\d+)$/);
          if (cutMatch && parseInt(cutMatch[1]) === 10) return score;
        }
        if (metricLabel === 'Recall@1000' && metricNameLower.startsWith('recall')) {
          const cutMatch = metricName.match(/(\d+)$/);
          if (cutMatch && parseInt(cutMatch[1]) === 1000) return score;
        }
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Express App
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Health / environment check
app.get('/api/status', (req, res) => {
  const javaVersion = getJavaVersion();
  const fatjar = resolveFatjarPath();
  res.json({
    javaAvailable: javaVersion >= 21,
    javaVersion: javaVersion,
    fatjarAvailable: !!fatjar,
    fatjarPath: fatjar || null,
    workspace: WORKSPACE_DIR,
  });
});

// Catalog: discover prebuilt inverted indexes
app.get('/api/catalog', (req, res) => {
  try {
    const catalog = buildCatalog();
    res.json({ success: true, catalog });
  } catch (err) {
    console.error('Catalog error:', err.message);
    // Fallback: at least return CACM as evaluable
    res.json({
      success: true,
      catalog: [
        {
          name: 'cacm',
          displayName: 'CACM (default)',
          type: 'inverted',
          description: 'CACM collection prebuilt index',
          evaluable: true,
          topics: 'cacm',
          qrelsId: 'cacm',
          availableMetrics: ['nDCG@10', 'Recall@1000', 'MAP', 'P@30'],
          filename: '',
          size: '',
        },
      ],
      warning: `Registry discovery failed: ${err.message}`,
    });
  }
});

// Topics: discover available topic sets
app.get('/api/topics', (req, res) => {
  try {
    const topics = discoverTopics();
    res.json({ success: true, topics: Array.isArray(topics) ? topics : [] });
  } catch (err) {
    res.json({ success: false, error: err.message, topics: [] });
  }
});

// Get pairing details for a specific index
app.get('/api/pairing/:indexName', (req, res) => {
  const indexName = req.params.indexName.toLowerCase();
  const pairing = KNOWN_EVALUABLE_PAIRINGS[indexName];
  if (pairing) {
    res.json({
      success: true,
      pairing: {
        indexName: pairing.indexName,
        displayName: pairing.displayName,
        topics: pairing.topics,
        qrelsId: pairing.qrelsId,
        availableMetrics: pairing.defaultMetrics,
      },
    });
  } else {
    res.json({
      success: false,
      error: `No known pairing for index "${req.params.indexName}"`,
    });
  }
});

// Run evaluation
app.post('/api/evaluate', (req, res) => {
  const { indexName, topicsId, qrelsId, metric: metricLabel } = req.body;

  // Validate inputs
  if (!indexName || !topicsId || !qrelsId || !metricLabel) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters: indexName, topicsId, qrelsId, metric',
    });
  }

  // Validate metric
  const metricFlag = METRIC_MAP[metricLabel];
  if (!metricFlag) {
    return res.status(400).json({
      success: false,
      error: `Unsupported metric: "${metricLabel}". Supported: ${Object.keys(METRIC_MAP).join(', ')}`,
    });
  }

  // Check fatjar
  const fatjar = resolveFatjarPath();
  if (!fatjar) {
    return res.status(500).json({
      success: false,
      error: 'Anserini fatjar not found. Please run: node setup/install-fatjar.js',
    });
  }

  // Ensure directories
  ensureDir(RUNS_DIR);
  ensureDir(EVALS_DIR);

  // Create unique run ID
  const runId = `run_${indexName}_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  const runFilePath = path.join(RUNS_DIR, `${runId}.txt`);
  const evalFilePath = path.join(EVALS_DIR, `${runId}.eval.txt`);

  const startTime = Date.now();

  // We'll send response with events as they happen
  // For simplicity with vanilla frontend, use a simple JSON response
  // with status information

  // Step 1: Run retrieval
  let retrievalResult, evalResult;
  let step = 'running_retrieval';
  let error = null;

  try {
    retrievalResult = runRetrieval(indexName, topicsId, runFilePath);

    // Verify run file was created
    if (!fs.existsSync(runFilePath) || fs.statSync(runFilePath).size === 0) {
      throw new Error('Retrieval produced no output or run file is empty');
    }

    // Step 2: Run evaluation
    step = 'running_evaluation';

    // Extract metric value from flag like '-m ndcg_cut.10' -> 'ndcg_cut.10'
    const metricParts = metricFlag.split(' ');
    const metricValues = [];
    for (let i = 0; i < metricParts.length; i++) {
      if (!metricParts[i].startsWith('-') && metricParts[i].length > 0) {
        metricValues.push(metricParts[i]);
      }
    }

    evalResult = runEvaluation(
      qrelsId,
      runFilePath,
      metricValues.length > 0 ? metricValues : [metricFlag.replace(/^-m\s+/, '')]
    );

    // Write eval output to file
    fs.writeFileSync(evalFilePath, evalResult.stdout);

    // Parse score
    const score = parseEvalScore(evalResult.stdout, metricLabel);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);

    // Read first few lines of run file for preview
    const runPreview = fs
      .readFileSync(runFilePath, 'utf8')
      .split('\n')
      .slice(0, 5)
      .join('\n');

    res.json({
      success: true,
      score: score !== null ? score : 'Could not parse score from evaluation output',
      rawScore: score,
      runId: runId,
      runFilePath: runFilePath,
      evalFilePath: evalFilePath,
      elapsedSeconds: elapsed,
      indexName: indexName,
      topicsId: topicsId,
      qrelsId: qrelsId,
      metric: metricLabel,
      runPreview: runPreview,
      evalOutput: evalResult.stdout,
    });
  } catch (err) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    res.json({
      success: false,
      error: err.message,
      step: step,
      elapsedSeconds: elapsed,
      indexName,
      topicsId,
      qrelsId,
      metric: metricLabel,
      runFilePath: fs.existsSync(runFilePath) ? runFilePath : null,
      evalFilePath: fs.existsSync(evalFilePath) ? evalFilePath : null,
    });
  }
});

// Serve the frontend
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

ensureDir(RUNS_DIR);
ensureDir(EVALS_DIR);

if (!module.parent) {
  app.listen(PORT, () => {
    console.log(`\n  Anserini Prebuilt Index Evaluator`);
    console.log(`  ─────────────────────────────────`);
    console.log(`  ➜  http://localhost:${PORT}`);
    console.log(`  ➜  Workspace: ${WORKSPACE_DIR}`);
    const fatjar = resolveFatjarPath();
    if (fatjar) {
      console.log(`  ➜  Fatjar: ${fatjar}`);
    } else {
      console.log(`  ⚠  Fatjar not found — run: node setup/install-fatjar.js`);
    }
    console.log(`\n`);
  });
}

module.exports = app;
