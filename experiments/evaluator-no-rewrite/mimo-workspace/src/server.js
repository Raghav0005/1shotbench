const express = require('express');
const { execSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3456;

// Anserini jar path - resolve from workspace root
const WORKSPACE = path.resolve(__dirname, '..');
const ANSERINI_JAR = path.join(WORKSPACE, 'anserini-2.1.1-fatjar.jar');
const RUNS_DIR = path.join(WORKSPACE, 'runs');

// Ensure runs directory exists
if (!fs.existsSync(RUNS_DIR)) {
  fs.mkdirSync(RUNS_DIR, { recursive: true });
}

app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));

// Known evaluable index -> topics/qrels mappings
// These are discovered from Anserini registries and reproduction docs
const EVALUABLE_MAPPINGS = {
  'cacm': {
    topics: 'cacm',
    qrels: 'cacm',
    description: 'CACM test collection - classic IR benchmark',
    type: 'inverted'
  }
};

// Helper: run Anserini CLI command
function runAnserini(args, timeout = 120000) {
  const cmd = `java -cp "${ANSERINI_JAR}" ${args}`;
  try {
    const result = execSync(cmd, { 
      encoding: 'utf8', 
      timeout,
      maxBuffer: 50 * 1024 * 1024,
      stdio: ['pipe', 'pipe', 'pipe']
    });
    return { success: true, output: result.trim() };
  } catch (err) {
    // If there's stdout, the command may have succeeded but returned non-zero
    if (err.stdout && err.stdout.trim()) {
      return { success: true, output: err.stdout.trim() };
    }
    return { 
      success: false, 
      error: err.stderr || err.message,
      stdout: err.stdout || ''
    };
  }
}

// Health check
app.get('/api/health', (req, res) => {
  const jarExists = fs.existsSync(ANSERINI_JAR);
  let javaOk = false;
  try {
    execSync('java -version', { encoding: 'utf8', stdio: 'pipe' });
    javaOk = true;
  } catch (e) {}
  
  res.json({
    healthy: jarExists && javaOk,
    java: javaOk,
    fatjar: jarExists,
    jarPath: ANSERINI_JAR
  });
});

// Extract JSON from Anserini output (may contain log lines)
function extractJSON(output) {
  // Find the first [ or { that starts a JSON array/object
  const jsonStart = output.search(/[[{]/);
  if (jsonStart === -1) return null;
  
  // Find the matching closing bracket
  let depth = 0;
  let inString = false;
  let escape = false;
  let endPos = output.length - 1;
  
  for (let i = jsonStart; i < output.length; i++) {
    const c = output[i];
    if (escape) { escape = false; continue; }
    if (c === '\\') { escape = true; continue; }
    if (c === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (c === '[' || c === '{') depth++;
    if (c === ']' || c === '}') {
      depth--;
      if (depth === 0) {
        endPos = i;
        break;
      }
    }
  }
  
  return output.substring(jsonStart, endPos + 1);
}

// List all prebuilt indexes
app.get('/api/indexes', (req, res) => {
  const filter = req.query.filter || '';
  const type = req.query.type || 'inverted';
  
  let args = `io.anserini.cli.PrebuiltIndexRegistry --list --type ${type}`;
  if (filter) {
    args += ` --filter '${filter}'`;
  }
  
  const result = runAnserini(args, 180000);
  if (!result.success) {
    return res.status(500).json({ error: 'Failed to list indexes', details: result.error });
  }
  
  try {
    const jsonStr = extractJSON(result.output);
    if (!jsonStr) {
      return res.status(500).json({ error: 'No JSON found in output', raw: result.output.substring(0, 500) });
    }
    const indexes = JSON.parse(jsonStr);
    // Enrich with evaluable status
    const enriched = indexes.map(idx => ({
      ...idx,
      evaluable: !!EVALUABLE_MAPPINGS[idx.name],
      evalConfig: EVALUABLE_MAPPINGS[idx.name] || null
    }));
    res.json(enriched);
  } catch (e) {
    res.status(500).json({ error: 'Failed to parse index list', details: e.message, raw: result.output.substring(0, 500) });
  }
});

// List topics
app.get('/api/topics', (req, res) => {
  const filter = req.query.filter || '';
  
  let args = 'io.anserini.cli.TopicsRegistry --list';
  if (filter) {
    args += ` --filter '${filter}'`;
  }
  
  const result = runAnserini(args);
  if (!result.success) {
    return res.status(500).json({ error: 'Failed to list topics', details: result.error });
  }
  
  try {
    const jsonStr = extractJSON(result.output);
    if (!jsonStr) {
      return res.status(500).json({ error: 'No JSON found in topics output' });
    }
    const topics = JSON.parse(jsonStr);
    res.json(topics);
  } catch (e) {
    res.status(500).json({ error: 'Failed to parse topics list', details: e.message });
  }
});

// Get index details
app.get('/api/indexes/:name', (req, res) => {
  const name = req.params.name;
  
  const result = runAnserini(
    `io.anserini.cli.PrebuiltIndexRegistry --list --filter '^${name}$'`
  );
  
  if (!result.success) {
    return res.status(500).json({ error: 'Failed to get index details', details: result.error });
  }
  
  try {
    const jsonStr = extractJSON(result.output);
    if (!jsonStr) {
      return res.status(404).json({ error: 'Index not found' });
    }
    const indexes = JSON.parse(jsonStr);
    if (indexes.length === 0) {
      return res.status(404).json({ error: 'Index not found' });
    }
    const idx = indexes[0];
    idx.evaluable = !!EVALUABLE_MAPPINGS[idx.name];
    idx.evalConfig = EVALUABLE_MAPPINGS[idx.name] || null;
    res.json(idx);
  } catch (e) {
    res.status(500).json({ error: 'Failed to parse index details', details: e.message });
  }
});

// Run evaluation
app.post('/api/evaluate', async (req, res) => {
  const { indexName, topicsName, metric } = req.body;
  
  if (!indexName || !topicsName || !metric) {
    return res.status(400).json({ error: 'Missing required fields: indexName, topicsName, metric' });
  }
  
  // Validate metric format
  const validMetrics = ['map', 'P.30', 'ndcg_cut.10', 'recall.1000', 'P.10', 'P.20', 'P.100', 'recall.10', 'recall.50', 'recall.100', 'recall.200', 'recall.500', 'ndcg_cut.5', 'ndcg_cut.20'];
  if (!validMetrics.includes(metric)) {
    return res.status(400).json({ error: `Invalid metric. Supported: ${validMetrics.join(', ')}` });
  }
  
  const runId = `${indexName}-${Date.now()}`;
  const runFile = path.join(RUNS_DIR, `${runId}.txt`);
  const evalFile = path.join(RUNS_DIR, `${runId}.eval.txt`);
  
  const startTime = Date.now();
  
  // Step 1: Run retrieval
  const searchArgs = `io.anserini.search.SearchCollection -threads 1 -index ${indexName} -topics ${topicsName} -output "${runFile}" -hits 1000 -bm25`;
  
  const searchResult = runAnserini(searchArgs, 300000);
  
  if (!searchResult.success) {
    return res.status(500).json({
      error: 'Retrieval failed',
      details: searchResult.error,
      stdout: searchResult.stdout,
      runId,
      elapsed: Date.now() - startTime
    });
  }
  
  // Verify run file exists
  if (!fs.existsSync(runFile)) {
    return res.status(500).json({
      error: 'Run file was not generated',
      runFile,
      runId,
      elapsed: Date.now() - startTime
    });
  }
  
  // Step 2: Run evaluation
  const evalArgs = `io.anserini.eval.TrecEval -c -m ${metric} ${indexName} "${runFile}"`;
  const evalResult = runAnserini(evalArgs);
  
  const elapsed = Date.now() - startTime;
  
  if (!evalResult.success) {
    return res.status(500).json({
      error: 'Evaluation failed',
      details: evalResult.error,
      stdout: evalResult.output || '',
      runId,
      runFile,
      elapsed
    });
  }
  
  // Parse evaluation output
  const evalOutput = evalResult.output || '';
  const lines = evalOutput.split('\n').filter(l => l.trim());
  const scores = {};
  
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 3) {
      scores[parts[0]] = parseFloat(parts[2]);
    }
  }
  
  // Write eval output to file
  fs.writeFileSync(evalFile, evalOutput);
  
  // Read a preview of the run file (first 20 lines)
  let runPreview = '';
  try {
    const runContent = fs.readFileSync(runFile, 'utf8');
    runPreview = runContent.split('\n').slice(0, 20).join('\n');
  } catch (e) {}
  
  res.json({
    success: true,
    runId,
    indexName,
    topicsName,
    metric,
    scores,
    evalOutput: evalOutput.trim(),
    runFile,
    evalFile,
    runPreview,
    elapsed,
    runFileSize: fs.statSync(runFile).size
  });
});

// Get run file contents
app.get('/api/runs/:runId', (req, res) => {
  const runFile = path.join(RUNS_DIR, `${req.params.runId}.txt`);
  const evalFile = path.join(RUNS_DIR, `${req.params.runId}.eval.txt`);
  
  const response = {};
  
  if (fs.existsSync(runFile)) {
    response.runFile = runFile;
    response.runContent = fs.readFileSync(runFile, 'utf8').split('\n').slice(0, 100).join('\n');
  }
  
  if (fs.existsSync(evalFile)) {
    response.evalFile = evalFile;
    response.evalContent = fs.readFileSync(evalFile, 'utf8');
  }
  
  if (!response.runFile && !response.evalFile) {
    return res.status(404).json({ error: 'Run not found' });
  }
  
  res.json(response);
});

app.listen(PORT, () => {
  console.log(`Anserini Prebuilt Index Evaluator running on http://localhost:${PORT}`);
  console.log(`Anserini JAR: ${ANSERINI_JAR}`);
  console.log(`Runs directory: ${RUNS_DIR}`);
});
