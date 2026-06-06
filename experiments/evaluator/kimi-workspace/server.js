const express = require('express');
const cors = require('cors');
const { execSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

const ANSERINI_JAR = path.resolve('anserini-2.1.1-fatjar.jar');
const RUNS_DIR = path.resolve('runs');
if (!fs.existsSync(RUNS_DIR)) fs.mkdirSync(RUNS_DIR, { recursive: true });

let cachedIndexes = null;
let cachedEvaluable = null;
let cachedTopics = null;

function anseriniExec(args, options = {}) {
  const cmd = `java -cp "${ANSERINI_JAR}" ${args}`;
  return execSync(cmd, { encoding: 'utf-8', stderr: 'pipe', ...options });
}

function getIndexes() {
  if (cachedIndexes) return cachedIndexes;
  const raw = anseriniExec('io.anserini.cli.PrebuiltIndexRegistry --list');
  cachedIndexes = JSON.parse(raw);
  return cachedIndexes;
}

function getTopics() {
  if (cachedTopics) return cachedTopics;
  const raw = anseriniExec('io.anserini.cli.TopicsRegistry --list');
  cachedTopics = JSON.parse(raw);
  return cachedTopics;
}

function getEvaluableConfigs() {
  if (cachedEvaluable) return cachedEvaluable;

  const configs = {};
  const raw = anseriniExec('io.anserini.reproduce.ReproduceFromPrebuiltIndexes --list');
  const configNames = JSON.parse(raw);

  for (const configName of configNames) {
    try {
      const yamlRaw = anseriniExec(`io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config ${configName} --show`);
      const lines = yamlRaw.split('\n');
      let currentCondition = null;
      let currentIndex = null;
      let inTopics = false;
      let topicIndent = null;
      let currentTopic = null;

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        // Match condition start: "  - name: ..."
        const condMatch = line.match(/^(\s*)-\s*name:\s*(.+)$/);
        if (condMatch) {
          currentCondition = condMatch[2].trim();
          currentIndex = null;
          inTopics = false;
          currentTopic = null;
          continue;
        }

        // Match command with index
        const cmdMatch = line.match(/^\s+command:\s*(.+)$/);
        if (cmdMatch && currentCondition) {
          const m = cmdMatch[1].match(/-index\s+(\S+)/);
          if (m) currentIndex = m[1];
          continue;
        }

        // Match start of topics array
        const topicsMatch = line.match(/^(\s+)topics:\s*$/);
        if (topicsMatch && currentCondition) {
          inTopics = true;
          topicIndent = topicsMatch[1].length;
          currentTopic = null;
          continue;
        }

        // Match topic item: "      - topic_key: ..."
        const topicItemMatch = line.match(/^(\s+)-\s+topic_key:\s*(.+)$/);
        if (topicItemMatch && currentIndex && inTopics) {
          // Finish previous topic if any
          if (currentTopic && currentTopic.evalKey) {
            if (!configs[currentIndex]) configs[currentIndex] = [];
            const existing = configs[currentIndex].find(x => x.topic === currentTopic.topic && x.eval === currentTopic.evalKey);
            if (!existing) {
              configs[currentIndex].push({ topic: currentTopic.topic, eval: currentTopic.evalKey, metrics: [...new Set(currentTopic.metrics)] });
            } else {
              existing.metrics = [...new Set([...existing.metrics, ...currentTopic.metrics])];
            }
          }
          currentTopic = { topic: topicItemMatch[2].trim(), evalKey: null, metrics: [] };
          continue;
        }

        // Match eval_key within a topic
        const evalMatch = line.match(/^(\s+)eval_key:\s*(.+)$/);
        if (evalMatch && currentTopic) {
          currentTopic.evalKey = evalMatch[2].trim();
          continue;
        }

        // Match metric_definitions start
        const metricDefMatch = line.match(/^(\s+)metric_definitions:\s*$/);
        if (metricDefMatch && currentTopic) {
          // metrics follow on subsequent lines at greater indent
          const defIndent = metricDefMatch[1].length;
          for (let j = i + 1; j < lines.length; j++) {
            if (lines[j].trim() === '') continue;
            const indent = lines[j].match(/^(\s*)/)[1].length;
            if (indent <= defIndent) break;
            const mname = lines[j].match(/^\s+(\S+):/);
            if (mname) currentTopic.metrics.push(mname[1]);
          }
          continue;
        }
      }

      // Finish last topic
      if (currentTopic && currentTopic.evalKey) {
        if (!configs[currentIndex]) configs[currentIndex] = [];
        const existing = configs[currentIndex].find(x => x.topic === currentTopic.topic && x.eval === currentTopic.evalKey);
        if (!existing) {
          configs[currentIndex].push({ topic: currentTopic.topic, eval: currentTopic.evalKey, metrics: [...new Set(currentTopic.metrics)] });
        } else {
          existing.metrics = [...new Set([...existing.metrics, ...currentTopic.metrics])];
        }
      }
    } catch (e) {
      // ignore malformed configs
    }
  }

  cachedEvaluable = configs;
  return cachedEvaluable;
}

app.get('/api/health', (req, res) => {
  try {
    const javaVersion = execSync('java -version 2>&1', { encoding: 'utf-8' });
    const jarExists = fs.existsSync(ANSERINI_JAR);
    res.json({ ok: jarExists, java: javaVersion.split('\n')[0], jar: ANSERINI_JAR });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

app.get('/api/indexes', (req, res) => {
  try {
    const indexes = getIndexes();
    const evaluable = getEvaluableConfigs();
    const result = indexes.map(idx => ({
      name: idx.name,
      type: idx.type,
      description: idx.description,
      size: idx.size,
      documents: idx.documents,
      uniqueTerms: idx.unique_terms,
      totalTerms: idx.total_terms,
      evaluable: !!evaluable[idx.name] && evaluable[idx.name].length > 0
    }));
    res.json(result);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/evaluable/:indexName', (req, res) => {
  try {
    const evaluable = getEvaluableConfigs();
    const data = evaluable[req.params.indexName];
    if (!data) return res.json({ topics: [] });
    res.json({ topics: data });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/topics', (req, res) => {
  try {
    res.json(getTopics());
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/evaluate', async (req, res) => {
  const { index, topic, evalKey, metricLabel, metricArgs } = req.body;
  if (!index || !topic || !evalKey || !metricArgs) {
    return res.status(400).json({ error: 'Missing required parameters' });
  }

  const timestamp = Date.now();
  const runFile = path.join(RUNS_DIR, `run.${index}.${topic}.${timestamp}.txt`);
  const evalFile = path.join(RUNS_DIR, `eval.${index}.${topic}.${metricLabel}.${timestamp}.txt`);

  const startTime = Date.now();

  try {
    // Run retrieval
    const searchArgs = [
      'io.anserini.search.SearchCollection',
      '-threads', '1',
      '-index', index,
      '-topics', topic,
      '-output', runFile,
      '-hits', '1000',
      '-bm25'
    ];

    await new Promise((resolve, reject) => {
      const proc = spawn('java', ['-cp', ANSERINI_JAR, ...searchArgs], {
        stdio: ['ignore', 'pipe', 'pipe']
      });
      let stdout = '';
      let stderr = '';
      proc.stdout.on('data', d => stdout += d);
      proc.stderr.on('data', d => stderr += d);
      proc.on('close', code => {
        if (code !== 0) reject(new Error(`SearchCollection exited ${code}: ${stderr}`));
        else resolve({ stdout, stderr });
      });
    });

    // Run evaluation
    const evalResult = await new Promise((resolve, reject) => {
      const proc = spawn('java', ['-cp', ANSERINI_JAR, 'io.anserini.eval.TrecEval', ...metricArgs.split(/\s+/).filter(Boolean), evalKey, runFile], {
        stdio: ['ignore', 'pipe', 'pipe']
      });
      let stdout = '';
      let stderr = '';
      proc.stdout.on('data', d => stdout += d);
      proc.stderr.on('data', d => stderr += d);
      proc.on('close', code => {
        if (code !== 0) reject(new Error(`TrecEval exited ${code}: ${stderr}`));
        else resolve(stdout);
      });
    });

    fs.writeFileSync(evalFile, evalResult);
    const elapsed = Date.now() - startTime;

    // Parse score
    const lines = evalResult.split('\n').filter(l => l.trim());
    const scoreLine = lines.find(l => l.includes('all'));
    const scoreMatch = scoreLine ? scoreLine.match(/all\s+([0-9.]+)/) : null;
    const score = scoreMatch ? parseFloat(scoreMatch[1]) : null;

    res.json({
      success: true,
      score,
      metric: metricLabel,
      index,
      topic,
      evalKey,
      runFile,
      evalFile,
      evalOutput: evalResult,
      elapsedMs: elapsed
    });
  } catch (e) {
    const elapsed = Date.now() - startTime;
    res.status(500).json({
      success: false,
      error: e.message,
      index,
      topic,
      evalKey,
      runFile,
      evalFile,
      elapsedMs: elapsed
    });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Anserini Prebuilt Index Evaluator listening on http://localhost:${PORT}`);
});

module.exports = { app };
