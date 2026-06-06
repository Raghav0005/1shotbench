const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

const port = process.env.PORT || 10000;
const anseriniJar = process.env.ANSERINI_JAR || path.resolve(__dirname, '../anserini-2.1.1-fatjar.jar'); // fallback for local dev

let status = {
    app: 'starting',
    java: false,
    anserini: false,
    reproductionDiscovery: false,
    nfcorpusIndex: false,
    evaluation: false,
    search: false,
    commands: {},
    evaluationMetrics: null
};

// Async exec wrapper
function runCommand(command) {
    return new Promise((resolve, reject) => {
        const start = Date.now();
        exec(command, { maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
            const time = Date.now() - start;
            resolve({ error, stdout, stderr, time, command });
        });
    });
}

// 1. Verify Java & Fatjar
async function verifySetup() {
    console.log("Verifying setup...");
    let cmd = `java -version`;
    let res = await runCommand(cmd);
    status.commands.javaVerify = { command: cmd, output: res.stderr }; // java -version outputs to stderr
    status.java = res.error ? false : true;

    cmd = `test -f "${anseriniJar}" && ls -l "${anseriniJar}"`;
    res = await runCommand(cmd);
    status.commands.fatjarVerify = { command: cmd, output: res.stdout || res.stderr };
    status.anserini = res.error ? false : true;

    if (!status.anserini) {
        status.app = 'error';
        return;
    }

    // 2. Discover NFCorpus reproduction
    cmd = `java -cp "${anseriniJar}" io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show`;
    res = await runCommand(cmd);
    status.commands.reproDiscover = { command: cmd, output: res.stdout.substring(0, 500) + '...' }; // truncate
    
    let expectedMetric = null;
    if (!res.error) {
        status.reproductionDiscovery = true;
        // simplistic YAML parsing
        try {
            const nfcorpusBlock = res.stdout.split('topic_key: nfcorpus')[1].split('topic_key:')[0];
            const ndcgMatch = nfcorpusBlock.match(/nDCG@10:\s*([0-9.]+)/);
            if (ndcgMatch) {
                expectedMetric = parseFloat(ndcgMatch[1]);
            }
        } catch (e) {
            console.error("Failed to parse expected metrics");
        }
    }

    status.expectedMetrics = { 'nDCG@10': expectedMetric };

    // Initialize search backend by just checking PrebuiltIndexRegistry
    cmd = `java -cp "${anseriniJar}" io.anserini.cli.PrebuiltIndexRegistry --list | grep beir-v1.0.0-nfcorpus.flat`;
    res = await runCommand(cmd);
    status.commands.indexDiscover = { command: cmd, output: res.stdout };
    if (!res.error) {
        status.nfcorpusIndex = true;
        status.search = true;
        status.evaluation = true;
    }

    status.app = 'ready';
    console.log("Setup complete");
}

verifySetup();

app.get('/health', (req, res) => {
    res.json(status);
});

// Search API
app.post('/api/search', async (req, res) => {
    const { query } = req.body;
    if (!query) return res.status(400).json({ error: "Missing query" });

    // Use Search CLI or RestServer? Let's use Search CLI with JSON output for single query ad hoc search.
    // wait, io.anserini.cli.Search --json gives us parsed JSON!
    const cmd = `java -cp "${anseriniJar}" io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat --query "${query}" --hits 10 --json`;
    const result = await runCommand(cmd);

    let hits = [];
    if (!result.error) {
        try {
            // Output might have logs, so find the first { or [ that parses as JSON
            const outputStr = result.stdout;
            // The JSON from Search CLI starts with {"query"
            const jsonStart = outputStr.indexOf('{"query"');
            if (jsonStart !== -1) {
                const parsed = JSON.parse(outputStr.substring(jsonStart));
                hits = parsed.candidates || [];
            } else {
                console.error("JSON start not found in output");
            }
        } catch(e) {
            console.error("Parse error", e);
        }
    }

    res.json({
        hits,
        command: result.command,
        error: result.error ? result.stderr : null,
        time: result.time
    });
});

// Evaluate API
app.post('/api/evaluate', async (req, res) => {
    // 1. SearchCollection
    const searchCmd = `java -cp "${anseriniJar}" io.anserini.search.SearchCollection -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -output run.beir.nfcorpus.txt -bm25 -removeQuery -hits 1000`;
    const searchRes = await runCommand(searchCmd);

    if (searchRes.error) {
        return res.status(500).json({ error: "SearchCollection failed", details: searchRes.stderr, command: searchCmd });
    }

    // 2. TrecEval
    const evalCmd = `java -cp "${anseriniJar}" io.anserini.eval.TrecEval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test run.beir.nfcorpus.txt`;
    const evalRes = await runCommand(evalCmd);

    if (evalRes.error) {
        return res.status(500).json({ error: "TrecEval failed", details: evalRes.stderr, command: evalCmd });
    }

    // parse eval
    // output format: ndcg_cut_10             all     0.3218
    let observedMetric = null;
    const match = evalRes.stdout.match(/ndcg_cut_10\s+all\s+([0-9.]+)/);
    if (match) {
        observedMetric = parseFloat(match[1]);
    }

    const report = {
        observedMetric,
        expectedMetric: status.expectedMetrics['nDCG@10'],
        delta: observedMetric && status.expectedMetrics['nDCG@10'] ? (observedMetric - status.expectedMetrics['nDCG@10']) : null,
        commands: {
            search: searchCmd,
            eval: evalCmd
        },
        time: searchRes.time + evalRes.time,
        artifact: 'run.beir.nfcorpus.txt',
        evalOutput: evalRes.stdout
    };

    status.evaluationMetrics = report;

    res.json(report);
});

app.listen(port, '0.0.0.0', () => {
    console.log(`Server listening on port ${port}`);
});
