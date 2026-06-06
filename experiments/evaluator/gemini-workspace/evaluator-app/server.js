const express = require('express');
const { exec, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const port = 3000;

app.use(express.json());
app.use(express.static('public'));

const ANSERINI_JAR = path.resolve(__dirname, '../anserini-2.1.1-fatjar.jar');

// Helper to run bash commands
function runBash(command) {
  return new Promise((resolve, reject) => {
    exec(command, { maxBuffer: 1024 * 1024 * 50 }, (error, stdout, stderr) => {
      if (error) {
        console.error(`Error: ${stderr}`);
        reject({ error, stderr, stdout });
      } else {
        resolve(stdout);
      }
    });
  });
}

const EVALUABLE_MAPPINGS = {
  'cacm': {
    topics: 'cacm',
    qrels: 'cacm'
  },
  'msmarco-v1-passage': {
    topics: 'msmarco-v1-passage.dev',
    qrels: 'msmarco-passage.dev-subset'
  }
};

app.get('/api/indexes', async (req, res) => {
  try {
    const cmdIndexes = `java -cp "${ANSERINI_JAR}" io.anserini.cli.PrebuiltIndexRegistry --type inverted --list`;
    const outputIndexes = await runBash(cmdIndexes);
    const indexes = JSON.parse(outputIndexes);

    const cmdTopics = `java -cp "${ANSERINI_JAR}" io.anserini.cli.TopicsRegistry --list`;
    const outputTopics = await runBash(cmdTopics);
    const availableTopics = JSON.parse(outputTopics);
    
    // Enhance with evaluability
    const enhanced = indexes.map(idx => {
      const isEvaluable = !!EVALUABLE_MAPPINGS[idx.name];
      // Optional check if topic exists in registry, but we know it does for cacm.
      return {
        ...idx,
        isEvaluable,
        evalPairing: isEvaluable ? EVALUABLE_MAPPINGS[idx.name] : null,
        availableTopicsCount: availableTopics.length
      };
    });
    
    res.json(enhanced);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch indexes', details: err.stderr });
  }
});

app.post('/api/evaluate', async (req, res) => {
  const { index, metric } = req.body;
  
  if (!EVALUABLE_MAPPINGS[index]) {
    return res.status(400).json({ error: 'Index is not evaluable' });
  }

  const { topics, qrels } = EVALUABLE_MAPPINGS[index];
  const runFile = `run.${index}.bm25.txt`;
  
  try {
    // 1. Run SearchCollection
    const searchCmd = `java -cp "${ANSERINI_JAR}" io.anserini.search.SearchCollection -threads 1 -index ${index} -topics ${topics} -output ${runFile} -hits 1000 -bm25`;
    const searchStart = Date.now();
    await runBash(searchCmd);
    const searchTime = Date.now() - searchStart;
    
    // 2. Run trec_eval
    const evalOutFile = `eval.${index}.${metric}.txt`;
    const evalCmd = `java -cp "${ANSERINI_JAR}" io.anserini.eval.TrecEval -c -m ${metric} ${qrels} ${runFile}`;
    const evalOutput = await runBash(evalCmd);
    
    // Save output
    fs.writeFileSync(evalOutFile, evalOutput);
    
    // Parse score from output
    // format is typically: measure \t all \t score
    const lines = evalOutput.split('\n');
    let score = null;
    for (const line of lines) {
      if (line.trim()) {
        const parts = line.split(/\s+/);
        if (parts.length >= 3) {
          score = parseFloat(parts[2]);
          break; // First match is our metric since we only requested one
        }
      }
    }
    
    res.json({
      score,
      metadata: {
        index,
        topics,
        metric,
        status: 'success',
        elapsedTimeMs: searchTime,
        runFilePath: path.resolve(runFile),
        evaluationOutputPath: path.resolve(evalOutFile),
        evaluationOutputPreview: evalOutput
      }
    });
    
  } catch (err) {
    res.status(500).json({ error: 'Evaluation failed', details: err.stderr || err.message });
  }
});

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});
