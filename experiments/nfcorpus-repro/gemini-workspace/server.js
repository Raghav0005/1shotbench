import express from 'express';
import cors from 'cors';
import { exec, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const execAsync = promisify(exec);

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'frontend', 'dist')));

const PORT = process.env.PORT || 10000;
const ANSERINI_JAR = process.env.ANSERINI_JAR || path.join(__dirname, 'backend', 'anserini', 'anserini-2.1.1-fatjar.jar');

let appStatus = {
  overall: 'initializing',
  java: false,
  fatjar: false,
  nfcorpus_ready: false,
  search_available: false,
  evaluation_available: false,
  evaluation_metrics: null,
  evaluation_time: null,
  evaluation_commands: [],
  evaluation_artifacts: [],
  setup_commands: [],
};

// Check prerequisites on startup
async function initialize() {
  const setupCmds = [];
  try {
    // 1. Check Java
    const javaCmd = 'java -version';
    setupCmds.push(javaCmd);
    const { stdout: javaOut, stderr: javaErr } = await execAsync(javaCmd);
    appStatus.java = true;

    // 2. Check Fatjar
    const checkJarCmd = `test -f ${ANSERINI_JAR} || echo "Fatjar missing"`;
    setupCmds.push(checkJarCmd);
    if (fs.existsSync(ANSERINI_JAR)) {
       appStatus.fatjar = true;
    } else {
       console.error("Fatjar not found at", ANSERINI_JAR);
       appStatus.overall = 'error';
       appStatus.setup_commands = setupCmds;
       return;
    }

    // 3. Dry-run to setup cache and verify NFCorpus readiness
    console.log("Checking NFCorpus readiness...");
    const cmd = `java -cp ${ANSERINI_JAR} io.anserini.search.SearchCollection -threads 1 -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -output /dev/null -bm25 -removeQuery -hits 1`;
    setupCmds.push(cmd);
    await execAsync(cmd);
    
    // Extract expected metric
    const reproCmd = `java -cp ${ANSERINI_JAR} io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show`;
    setupCmds.push(reproCmd);
    const { stdout: reproOut } = await execAsync(reproCmd);
    
    // Parse YAML-like output
    const lines = reproOut.split('\\n');
    let inNfCorpus = false;
    let expectedNdcg = 0.3218; // fallback
    for (const line of lines) {
       if (line.includes('eval_key: beir-v1.0.0-nfcorpus.test')) {
          inNfCorpus = true;
       } else if (inNfCorpus && line.includes('nDCG@10:')) {
          const match = line.match(/nDCG@10:\\s+([0-9.]+)/);
          if (match) {
             expectedNdcg = parseFloat(match[1]);
             break;
          }
       } else if (inNfCorpus && line.includes('- topic_key:')) {
          // Moved to another dataset
          break;
       }
    }
    appStatus.expectedNdcg = expectedNdcg;
    
    appStatus.nfcorpus_ready = true;
    appStatus.search_available = true;
    appStatus.evaluation_available = true;
    appStatus.setup_commands = setupCmds;
    appStatus.overall = 'ready';
    console.log("Initialization complete. App ready.");

    // Perform initial evaluation to cache results for the UI
    await performEvaluation();
  } catch (error) {
    console.error("Initialization failed:", error);
    appStatus.overall = 'error';
  }
}

async function performEvaluation() {
  const startTime = Date.now();
  const runFile = path.join(__dirname, 'run.beir.core.flat.nfcorpus.txt');
  const commands = [];
  const artifacts = [];
  try {
    // 1. Search Collection
    const searchCmd = `java -cp ${ANSERINI_JAR} io.anserini.search.SearchCollection -threads 1 -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -output ${runFile} -bm25 -removeQuery`;
    commands.push(searchCmd);
    await execAsync(searchCmd);
    artifacts.push(runFile);

    // 2. Evaluate
    const evalCmd = `java -cp ${ANSERINI_JAR} io.anserini.eval.TrecEval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test ${runFile}`;
    commands.push(evalCmd);
    const { stdout } = await execAsync(evalCmd);
    
    // Parse output
    // ndcg_cut_10           	all	0.3218
    const match = stdout.match(/ndcg_cut_10\s+all\s+([0-9.]+)/);
    let observed = null;
    if (match) {
       observed = parseFloat(match[1]);
    }

    appStatus.evaluation_metrics = {
      expected: appStatus.expectedNdcg || 0.3218,
      observed: observed,
      metric: 'nDCG@10'
    };
    appStatus.evaluation_time = Date.now() - startTime;
    appStatus.evaluation_commands = commands;
    appStatus.evaluation_artifacts = artifacts;
    if (appStatus.eval_cached === undefined) {
      appStatus.eval_cached = true;
    }

  } catch (err) {
    console.error("Evaluation failed", err);
  }
}

initialize();

app.get('/health', (req, res) => {
  res.json({
    status: appStatus.overall,
    java: appStatus.java,
    fatjar: appStatus.fatjar,
    nfcorpus_ready: appStatus.nfcorpus_ready,
    search_available: appStatus.search_available,
    evaluation_available: appStatus.evaluation_available,
    setup_commands: appStatus.setup_commands
  });
});

app.get('/api/evalStatus', (req, res) => {
  res.json({
    metrics: appStatus.evaluation_metrics,
    time: appStatus.evaluation_time,
    commands: appStatus.evaluation_commands,
    artifacts: appStatus.evaluation_artifacts,
    isCached: appStatus.eval_cached
  });
});

app.post('/api/rerunEval', async (req, res) => {
  appStatus.evaluation_metrics = null;
  appStatus.eval_cached = false;
  await performEvaluation();
  res.json({ success: true });
});

app.get('/api/search', async (req, res) => {
  const { q } = req.query;
  if (!q) {
    return res.status(400).json({ error: 'Query required' });
  }
  
  try {
     const searchCmd = `java -cp ${ANSERINI_JAR} io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat --query "${q.replace(/"/g, '\\"')}" --hits 10 --json`;
     const { stdout } = await execAsync(searchCmd);
     
     // The stdout contains the json response, but it also has SLF4J logs at the start.
     // We should extract the JSON part. It should start with {
     const jsonStr = stdout.substring(stdout.indexOf('{'));
     const data = JSON.parse(jsonStr);
     res.json({ hits: data.candidates || [], command: searchCmd });
  } catch (error) {
     res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server listening on port ${PORT}`);
});
