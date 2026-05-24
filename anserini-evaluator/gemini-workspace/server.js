const express = require('express');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const util = require('util');

const execAsync = util.promisify(exec);
const app = express();

app.use(express.json());
app.use(express.static('public'));

const ANSERINI_JAR = fs.readdirSync(__dirname).find(f => f.startsWith('anserini') && f.endsWith('fatjar.jar')) 
    ? path.join(__dirname, fs.readdirSync(__dirname).find(f => f.startsWith('anserini') && f.endsWith('fatjar.jar'))) 
    : path.join(__dirname, 'anserini-2.1.1-fatjar.jar');

// We cache these since they're static and take a moment to generate
let indexesCache = null;
let topicsCache = null;

app.get('/api/indexes', async (req, res) => {
    if (indexesCache) return res.json(indexesCache);
    try {
        const { stdout } = await execAsync(`java -cp "${ANSERINI_JAR}" io.anserini.cli.PrebuiltIndexRegistry --list`);
        indexesCache = JSON.parse(stdout);
        res.json(indexesCache);
    } catch (e) {
        console.error(e);
        res.status(500).json({ error: 'Failed to fetch indexes' });
    }
});

app.get('/api/topics', async (req, res) => {
    if (topicsCache) return res.json(topicsCache);
    try {
        const { stdout } = await execAsync(`java -cp "${ANSERINI_JAR}" io.anserini.cli.TopicsRegistry --list`);
        topicsCache = JSON.parse(stdout);
        res.json(topicsCache);
    } catch (e) {
        console.error(e);
        res.status(500).json({ error: 'Failed to fetch topics' });
    }
});

app.post('/api/evaluate', async (req, res) => {
    const { index, topic, metric } = req.body;
    if (!index || !topic || !metric) return res.status(400).json({ error: 'Missing parameters' });

    const runFile = path.join(__dirname, `run.${index}.${topic}.txt`);
    const evalFile = path.join(__dirname, `eval.${index}.${topic}.txt`);

    const metricFlag = metric.replace('@', '_cut.').replace('nDCG', 'ndcg').replace('Recall', 'recall').toLowerCase();
    
    // Some metric transformations based on trec_eval standard parameters
    let tEvalMetric = metric;
    if (metric === 'nDCG@10') tEvalMetric = 'ndcg_cut.10';
    else if (metric === 'Recall@1000') tEvalMetric = 'recall.1000';
    else if (metric === 'MAP') tEvalMetric = 'map';
    
    try {
        const start = Date.now();
        // Run search
        await execAsync(`java -cp "${ANSERINI_JAR}" io.anserini.search.SearchCollection -threads 1 -index ${index} -topics ${topic} -output "${runFile}" -hits 1000 -bm25`);
        
        // Run eval
        // qrels source is typically the topic name for prebuilt evaluation resources when available. 
        // e.g. Anserini maps cacm to cacm qrels automatically.
        const evalCmd = `java -cp "${ANSERINI_JAR}" io.anserini.eval.TrecEval -c -m ${tEvalMetric} ${topic} "${runFile}"`;
        const { stdout } = await execAsync(evalCmd);
        
        // Write eval output
        fs.writeFileSync(evalFile, stdout);

        const elapsed = Date.now() - start;

        // Parse score
        // Output looks like: ndcg_cut_10       all     0.4543
        const lines = stdout.trim().split('\n');
        const scoreLine = lines.find(l => l.includes('all'));
        let score = null;
        if (scoreLine) {
            const parts = scoreLine.trim().split(/\s+/);
            score = parts[2];
        }

        res.json({
            index,
            topic,
            metric,
            score,
            status: 'Success',
            elapsedMs: elapsed,
            runFile: runFile,
            evalOutput: stdout,
        });

    } catch (e) {
        console.error(e);
        res.status(500).json({ error: 'Evaluation failed', details: e.message || String(e) });
    }
});

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`Server listening on port ${PORT}`);
});
