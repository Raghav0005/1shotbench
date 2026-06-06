const express = require('express');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const app = express();
const PORT = 3456;

// Resolve ANSERINI_JAR
function getAnseriniJar() {
  if (process.env.ANSERINI_JAR && fs.existsSync(process.env.ANSERINI_JAR)) {
    return process.env.ANSERINI_JAR;
  }
  const dir = __dirname;
  const files = fs.readdirSync(dir);
  const fatjar = files.find(f => f.match(/anserini-.*-fatjar\.jar$/));
  if (fatjar) return path.join(dir, fatjar);
  return null;
}

const JAR = getAnseriniJar();

function runJava(args, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    if (!JAR) return reject(new Error('Anserini fatjar not found. Set ANSERINI_JAR or place fatjar in workspace.'));
    const allArgs = ['-cp', JAR, ...args];
    execFile('java', allArgs, { timeout: timeoutMs, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) return reject({ error: err, stdout, stderr });
      resolve({ stdout, stderr });
    });
  });
}

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// Health check
app.get('/api/health', (req, res) => {
  res.json({ ok: true, jar: JAR, jarExists: JAR ? fs.existsSync(JAR) : false });
});

// GET /api/catalog - list inverted indexes from PrebuiltIndexRegistry
app.get('/api/catalog', async (req, res) => {
  try {
    const { stdout } = await runJava(['io.anserini.cli.PrebuiltIndexRegistry', '--type', 'inverted', '--list']);
    res.json(JSON.parse(stdout));
  } catch (e) {
    res.status(500).json({ error: 'Failed to list prebuilt indexes', detail: e.stderr || e.error?.message || String(e) });
  }
});

// GET /api/pairings - derive evaluable pairings from reproduction configs
app.get('/api/pairings', async (req, res) => {
  try {
    const { stdout: configListStr } = await runJava(['io.anserini.reproduce.ReproduceFromPrebuiltIndexes', '--list']);
    const configList = JSON.parse(configListStr);

    const pairings = {};
    for (const configName of configList) {
      try {
        const { stdout: yamlStr } = await runJava([
          'io.anserini.reproduce.ReproduceFromPrebuiltIndexes',
          '--config', configName, '--show'
        ], 30000);
        const parsed = parseReproConfig(yamlStr);
        for (const p of parsed) {
          // Skip placeholder indexes (contain $variables)
          if (p.index.includes('$')) continue;
          // Only include BM25 conditions (our server runs BM25)
          if (p.condition !== 'bm25' && !p.condition.startsWith('bm25')) continue;
          // Deduplicate by (index, topic_key, eval_key)
          const key = p.index;
          if (!pairings[key]) pairings[key] = [];
          const exists = pairings[key].some(ep => ep.topic_key === p.topic_key && ep.eval_key === p.eval_key);
          if (!exists) {
            pairings[key].push(p);
          }
        }
      } catch (e) {
        // Skip configs that fail
      }
    }

    // Add extra commonly-supported metrics for known datasets
    for (const indexName of Object.keys(pairings)) {
      for (const pairing of pairings[indexName]) {
        // Add nDCG@10 and Recall@1000 if not already present
        const m = pairing.metrics;
        if (!m['nDCG@10']) m['nDCG@10'] = '-c -m ndcg_cut.10';
        if (!m['Recall@1000']) m['Recall@1000'] = '-c -m recall.1000';
      }
    }

    res.json(pairings);
  } catch (e) {
    res.status(500).json({ error: 'Failed to derive pairings', detail: e.stderr || e.error?.message || String(e) });
  }
});

function parseReproConfig(yamlStr) {
  const results = [];
  const lines = yamlStr.split('\n');
  let currentCondition = null;
  let currentTopic = null;
  let inMetricDefs = false;
  let inExpectedScores = false;

  function pushTopic() {
    if (currentTopic && currentCondition && currentTopic.topic_key && currentTopic.eval_key && Object.keys(currentTopic.metrics).length > 0) {
      results.push({
        index: currentCondition.index,
        condition: currentCondition.name,
        topic_key: currentTopic.topic_key,
        eval_key: currentTopic.eval_key,
        metrics: { ...currentTopic.metrics }
      });
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const condMatch = trimmed.match(/^-\s*name:\s+(\S+)/);
    if (condMatch) {
      pushTopic();
      currentCondition = condMatch[1];
      currentTopic = null;
      inMetricDefs = false;
      inExpectedScores = false;
      continue;
    }

    const cmdMatch = trimmed.match(/^command:\s+(.*)/);
    if (cmdMatch) {
      const idxMatch = cmdMatch[1].match(/-index\s+(\S+)/);
      if (idxMatch && currentCondition) {
        currentCondition = {
          name: typeof currentCondition === 'object' ? currentCondition.name : currentCondition,
          index: idxMatch[1]
        };
      }
      continue;
    }

    const topicMatch = trimmed.match(/^-?\s*topic_key:\s+(\S+)/);
    if (topicMatch) {
      pushTopic();
      currentTopic = { topic_key: topicMatch[1], metrics: {}, eval_key: null };
      inMetricDefs = false;
      inExpectedScores = false;
      continue;
    }

    const evalMatch = trimmed.match(/^eval_key:\s+(\S+)/);
    if (evalMatch && currentTopic) {
      currentTopic.eval_key = evalMatch[1];
      continue;
    }

    if (trimmed === 'metric_definitions:') {
      inMetricDefs = true;
      inExpectedScores = false;
      continue;
    }

    if (trimmed === 'expected_scores:') {
      inExpectedScores = true;
      inMetricDefs = false;
      continue;
    }

    if (trimmed === 'conditions:' || trimmed === 'topics:') {
      if (trimmed === 'conditions:') { pushTopic(); currentCondition = null; currentTopic = null; }
      if (trimmed === 'topics:') { pushTopic(); currentTopic = null; }
      inMetricDefs = false;
      inExpectedScores = false;
      continue;
    }

    if (inMetricDefs && currentTopic) {
      const metricDef = trimmed.match(/^(\S+):\s+"([^"]*)"/);
      if (metricDef) {
        currentTopic.metrics[metricDef[1]] = metricDef[2];
      }
    }
  }

  pushTopic();
  return results;
}

// POST /api/evaluate - run retrieval + evaluation
app.post('/api/evaluate', async (req, res) => {
  const { indexName, topicKey, evalKey, metricFlag, metricLabel } = req.body;

  if (!indexName || !topicKey || !evalKey || !metricFlag) {
    return res.status(400).json({ error: 'Missing required fields: indexName, topicKey, evalKey, metricFlag' });
  }

  const workDir = path.join(os.tmpdir(), 'anserini-eval', `${indexName}-${Date.now()}`);
  fs.mkdirSync(workDir, { recursive: true });

  const runFile = path.join(workDir, 'run.txt');
  const startTime = Date.now();

  try {
    // Step 1: Run retrieval
    const searchArgs = [
      'io.anserini.search.SearchCollection',
      '-threads', '1',
      '-index', indexName,
      '-topics', topicKey,
      '-output', runFile,
      '-hits', '1000',
      '-bm25'
    ];

    let searchStderr = '';
    try {
      const result = await runJava(searchArgs, 300000);
      searchStderr = result.stderr || '';
    } catch (e) {
      const detail = (e.stderr || '') + '\n' + (e.stdout || '');
      return res.status(500).json({
        error: 'Retrieval failed',
        detail,
        indexName, topicKey, evalKey, metricFlag, metricLabel
      });
    }

    const retrievalTime = Date.now() - startTime;

    // Step 2: Run evaluation
    const evalArgs = [
      'io.anserini.eval.TrecEval',
      ...metricFlag.split(/\s+/).filter(Boolean),
      evalKey,
      runFile
    ];

    let evalStdout = '';
    let evalStderr = '';
    try {
      const result = await runJava(evalArgs, 60000);
      evalStdout = (result.stdout || '').trim();
      evalStderr = result.stderr || '';
    } catch (e) {
      evalStdout = (e.stdout || '').trim();
      evalStderr = (e.stderr || '').trim();
    }

    const totalTime = Date.now() - startTime;

    // Parse evaluation output: "metric\tall\tscore"
    let score = null;
    const evalLines = evalStdout.split('\n').filter(l => l.trim());
    for (const line of evalLines) {
      const parts = line.split('\t');
      if (parts.length >= 3) {
        score = parseFloat(parts[2]);
        break;
      }
    }

    res.json({
      success: true,
      indexName,
      topicKey,
      evalKey,
      metricFlag,
      metricLabel: metricLabel || metricFlag,
      score,
      evalOutput: evalStdout,
      searchLog: searchStderr,
      evalLog: evalStderr,
      runFile,
      workDir,
      retrievalTimeMs: retrievalTime,
      totalTimeMs: totalTime
    });
  } catch (e) {
    res.status(500).json({ error: 'Unexpected error', detail: String(e) });
  }
});

app.listen(PORT, () => {
  console.log(`Anserini Evaluator running at http://localhost:${PORT}`);
  console.log(`JAR: ${JAR}`);
});
