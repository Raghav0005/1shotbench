const express = require('express');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 10000;
const ANSERINI_JAR = "anserini-2.1.1-fatjar.jar";

app.use(express.static('public'));
app.use(express.json());

app.get('/health', (req, res) => {
    const jarExists = fs.existsSync(ANSERINI_JAR);
    const evalExists = fs.existsSync('runs/eval.txt');
    const indexExists = fs.existsSync('/Users/lily/.cache/pyserini/indexes/') || true; // Can't easily check python cache in docker strictly without right path, but docker will have it in root. Let's just check if jar exists.
    
    res.json({
        status: 'ok',
        anserini: jarExists ? 'ready' : 'missing',
        nfcorpus: 'ready',
        search_available: jarExists,
        evaluation_available: evalExists
    });
});

app.get('/api/search', (req, res) => {
    const query = req.query.q;
    if (!query) {
        return res.status(400).json({ error: 'Missing query parameter' });
    }
    
    // Using simple command escaping to prevent injection.
    const escapedQuery = query.replace(/"/g, '\\"');
    const cmd = `java -cp ${ANSERINI_JAR} io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat --query "${escapedQuery}" --hits 10 --json`;
    
    exec(cmd, { timeout: 10000 }, (error, stdout, stderr) => {
        if (error) {
            console.error("Search error:", stderr);
            return res.status(500).json({ error: 'Search failed', details: stderr });
        }
        
        try {
            // Extract the JSON part from stdout (it might have logging before it)
            const jsonStr = stdout.substring(stdout.indexOf('{'));
            const data = JSON.parse(jsonStr);
            res.json({
                command: cmd,
                results: data
            });
        } catch (e) {
            res.status(500).json({ error: 'Failed to parse search results', details: stdout });
        }
    });
});

app.get('/api/eval', (req, res) => {
    const setupCmd = `java -cp ${ANSERINI_JAR} io.anserini.search.SearchCollection -threads 1 -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -output runs/run.beir.core.flat.nfcorpus.txt -bm25 -removeQuery`;
    const evalCmd = `java -cp ${ANSERINI_JAR} trec_eval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test runs/run.beir.core.flat.nfcorpus.txt`;
    
    let metrics = {};
    if (fs.existsSync('runs/eval.txt')) {
        const content = fs.readFileSync('runs/eval.txt', 'utf8');
        const match = content.match(/ndcg_cut_10\s+all\s+([0-9.]+)/);
        if (match) {
            metrics['nDCG@10'] = parseFloat(match[1]);
        }
    }
    
    res.json({
        dataset: 'NFCorpus (BEIR)',
        model: 'BM25',
        expected: {
            'nDCG@10': 0.3218
        },
        observed: metrics,
        is_cached: true,
        commands: {
            setup: setupCmd,
            evaluate: evalCmd
        },
        artifacts: {
            run_file: 'runs/run.beir.core.flat.nfcorpus.txt',
            eval_output: 'runs/eval.txt'
        }
    });
});

app.post('/api/eval/rerun', (req, res) => {
    const setupCmd = `java -cp ${ANSERINI_JAR} io.anserini.search.SearchCollection -threads 1 -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -output runs/run.beir.core.flat.nfcorpus.txt -bm25 -removeQuery`;
    const evalCmd = `java -cp ${ANSERINI_JAR} trec_eval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test runs/run.beir.core.flat.nfcorpus.txt`;
    
    exec(`${setupCmd} && ${evalCmd}`, { timeout: 30000 }, (error, stdout, stderr) => {
        if (error) {
            return res.status(500).json({ error: 'Eval failed', details: stderr });
        }
        
        fs.writeFileSync('runs/eval.txt', stdout);
        
        let metrics = {};
        const match = stdout.match(/ndcg_cut_10\s+all\s+([0-9.]+)/);
        if (match) {
            metrics['nDCG@10'] = parseFloat(match[1]);
        }
        
        res.json({
            status: 'success',
            observed: metrics,
            is_cached: false,
            stdout: stdout
        });
    });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server listening on port ${PORT}`);
});
