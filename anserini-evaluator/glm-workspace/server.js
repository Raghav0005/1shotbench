const express = require('express');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const app = express();
const PORT = process.env.PORT || 3000;

// Resolve the Anserini fatjar
function resolveJar() {
  // Check ANSERINI_JAR env var first
  if (process.env.ANSERINI_JAR && fs.existsSync(process.env.ANSERINI_JAR)) {
    return process.env.ANSERINI_JAR;
  }
  // Look for fatjar in cwd
  const files = fs.readdirSync(__dirname);
  const jar = files.find(f => f.match(/^anserini-.*-fatjar\.jar$/));
  if (jar) return path.join(__dirname, jar);
  return null;
}

const ANSERINI_JAR = resolveJar();

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Helper to run Anserini commands
function runAnserini(args, timeout = 300000) {
  return new Promise((resolve, reject) => {
    if (!ANSERINI_JAR) {
      return reject(new Error('Anserini fatjar not found. Please download it or set ANSERINI_JAR.'));
    }
    const javaArgs = ['-cp', ANSERINI_JAR, ...args];
    const child = execFile('java', javaArgs, { 
      maxBuffer: 50 * 1024 * 1024,
      timeout,
      cwd: os.tmpdir()
    }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || error.message));
      } else {
        resolve(stdout);
      }
    });
  });
}

// API: Get prebuilt inverted indexes
app.get('/api/indexes', async (req, res) => {
  try {
    const stdout = await runAnserini(['io.anserini.cli.PrebuiltIndexRegistry', '--type', 'inverted', '--list']);
    const indexes = JSON.parse(stdout);
    res.json({ indexes, jar: path.basename(ANSERINI_JAR || '') });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// API: Get topics list
app.get('/api/topics', async (req, res) => {
  try {
    const filter = req.query.filter;
    const args = ['io.anserini.cli.TopicsRegistry', '--list'];
    if (filter) args.push('--filter', filter);
    const stdout = await runAnserini(args);
    const topics = JSON.parse(stdout);
    res.json({ topics });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Known evaluable index→topic→qrels pairings
const EVALUABLE_INDEXES = {
  'cacm': {
    topics: 'cacm',
    qrels: 'cacm',
    metrics: [
      { id: 'ndcg_cut.10', label: 'nDCG@10' },
      { id: 'recall.1000', label: 'Recall@1000' },
      { id: 'map', label: 'MAP' },
      { id: 'P.30', label: 'P@30' },
    ],
    searchArgs: { '-bm25': true, '-hits': '1000' },
    description: 'CACM collection - small test collection for IR evaluation'
  }
};

// API: Get evaluable configs
app.get('/api/evaluable', (req, res) => {
  res.json({ configs: EVALUABLE_INDEXES });
});

// API: Run evaluation
app.get('/api/evaluate', async (req, res) => {
  const { index, metric } = req.query;
  
  if (!index || !metric) {
    return res.status(400).json({ error: 'Missing index or metric parameter' });
  }
  
  const config = EVALUABLE_INDEXES[index];
  if (!config) {
    return res.status(400).json({ error: `Index "${index}" is not configured for evaluation. Only evaluable indexes can be evaluated.` });
  }
  
  const metricObj = config.metrics.find(m => m.id === metric);
  if (!metricObj) {
    return res.status(400).json({ error: `Unsupported metric "${metric}" for index "${index}"` });
  }
  
  const timestamp = Date.now();
  const runFile = path.join(os.tmpdir(), `run.${index}.${timestamp}.txt`);
  
  try {
    // Step 1: Run retrieval
    const searchStart = Date.now();
    const searchArgs = [
      'io.anserini.search.SearchCollection',
      '-threads', '1',
      '-index', index,
      '-topics', config.topics,
      '-output', runFile,
    ];
    // Add model-specific args
    for (const [key, val] of Object.entries(config.searchArgs)) {
      searchArgs.push(key);
      if (val !== true) searchArgs.push(String(val));
    }
    
    await runAnserini(searchArgs);
    const searchTime = Date.now() - searchStart;
    
    // Step 2: Read run file stats
    const runContent = fs.readFileSync(runFile, 'utf-8');
    const runLines = runContent.trim().split('\n');
    
    // Step 3: Run evaluation
    const evalStart = Date.now();
    const evalArgs = [
      'io.anserini.eval.TrecEval',
      '-c',
      '-m', metric,
      config.qrels,
      runFile
    ];
    
    const evalOutput = await runAnserini(evalArgs);
    const evalTime = Date.now() - evalStart;
    
    // Parse eval output
    const evalLines = evalOutput.trim().split('\n');
    const scoreMatch = evalLines[evalLines.length - 1].match(/^(\S+)\s+(\S+)\s+([\d.]+)$/);
    const score = scoreMatch ? parseFloat(scoreMatch[3]) : null;
    const metricId = scoreMatch ? scoreMatch[1] : metric;
    
    res.json({
      success: true,
      index,
      topics: config.topics,
      qrels: config.qrels,
      metric: metricId,
      metricLabel: metricObj.label,
      score,
      searchTimeMs: searchTime,
      evalTimeMs: evalTime,
      runFile,
      runLines: runLines.length,
      evalOutput: evalOutput.trim(),
      runPreview: runLines.slice(0, 10).join('\n')
    });
  } catch (err) {
    res.status(500).json({
      success: false,
      index,
      topics: config.topics,
      qrels: config.qrels,
      metric,
      metricLabel: metricObj.label,
      error: err.message,
      runFile: fs.existsSync(runFile) ? runFile : null
    });
  }
});

app.listen(PORT, () => {
  console.log(`Anserini Evaluator running at http://localhost:${PORT}`);
  if (ANSERINI_JAR) {
    console.log(`Using Anserini jar: ${ANSERINI_JAR}`);
  } else {
    console.warn('WARNING: No Anserini fatjar found. Set ANSERINI_JAR or place fatjar in project directory.');
  }
});

module.exports = app;
