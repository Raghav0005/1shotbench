# NFCorpus Live Retrieval Diagnostics Workbench

A Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini.

## Features

- **Live Search**: Query NFCorpus through Anserini's CLI search (`io.anserini.cli.Search`)
- **BM25 Evaluation**: Runs `SearchCollection` + `TrecEval` against NFCorpus with real artifacts
- **Metric Verification**: Compares observed nDCG@10 against the `beir.core` reproduction expected value (0.3218)
- **Command Transparency**: All Anserini commands and artifact paths are visible in the UI
- **Reproduction Discovery**: Uses `ReproduceFromPrebuiltIndexes --dry-run` to discover expected metrics
- **Readiness Dashboard**: Shows Java, fatjar, index, topics, evaluation status in real time

## Architecture

- **Backend**: Python Flask server that shells out to Anserini fatjar CLI commands
- **Frontend**: Single-page HTML dashboard with vanilla JS
- **Dataset**: BEIR v1.0.0 NFCorpus via Anserini prebuilt index (`beir-v1.0.0-nfcorpus.flat`)
- **No mocking**: All search results, evaluation metrics, and commands are real Anserini outputs

## Quick Start (Local)

```bash
# Prerequisites: Java 21, Python 3.10+
cd app

# Install dependencies
pip install -r requirements.txt

# Set environment
export ANSERINI_JAR=/path/to/anserini-2.1.1-fatjar.jar
export DATA_DIR=$(pwd)/data
export PORT=10000

# Run
python server.py
```

Open http://localhost:10000

## Docker

```bash
# Build
docker build -t nfcorpus-workbench .

# Run
docker run -e PORT=10000 -p 10000:10000 nfcorpus-workbench
```

## Render Deployment

1. Create a new **Web Service** on Render
2. Connect the repository
3. Set **Docker** as the environment
4. The `Dockerfile` handles everything:
   - Downloads Anserini fatjar at startup
   - Downloads NFCorpus prebuilt index on first search/eval
   - Binds HTTP to `0.0.0.0:$PORT`
5. Set `PORT` environment variable if needed (defaults to `10000`)

### Port Binding

The container binds to `0.0.0.0` and reads `PORT` from the environment (default: `10000`).

### Persistent Storage

If persistent storage is needed on Render, mount a disk at `/app/data`. This preserves:
- Anserini fatjar (`/app/data/anserini-*.jar`)
- NFCorpus prebuilt index cache (downloaded by Anserini to `~/.cache/pyserini/`)
- Run files and evaluation output (`/app/data/runs/`)

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | JSON health status |
| `/api/status` | GET | Detailed setup/readiness status |
| `/api/search` | POST | Live search (`{"query": "...", "hits": 10}`) |
| `/api/evaluation` | GET | BM25 evaluation results and comparison |
| `/api/commands` | GET | All Anserini commands used |
| `/api/sample-queries` | GET | NFCorpus sample queries |
| `/api/setup-log` | GET | Setup command log |
| `/api/rerun-evaluation` | POST | Re-run BM25 evaluation from scratch |
| `/api/artifact-preview` | GET | Preview a generated artifact file |

## Browser Test

```bash
pip install playwright
playwright install chromium
python tests/test_browser.py --url http://localhost:10000 --timeout 300
```

The test verifies:
- Health/readiness panel
- NFCorpus dataset identification
- Anserini setup status
- Live search with ranked results (docids, scores, snippets)
- Evaluation metrics (observed nDCG@10 close to expected 0.3218)
- Expected-vs-observed comparison with delta and pass/close/fail status
- Exact command text and artifact paths
- **Fails if results are mocked** (checks observed nDCG@10 is within tolerance of expected value)

## NFCorpus Configuration

| Item | Value |
|---|---|
| Prebuilt Index | `beir-v1.0.0-nfcorpus.flat` |
| Topics | `beir-nfcorpus` |
| Qrels/Eval | `beir-v1.0.0-nfcorpus.test` |
| Expected nDCG@10 | 0.3218 (from `beir.core` reproduction YAML) |
| Metric Flag | `-c -m ndcg_cut.10` |
| Documents | 3,633 |
| Index Size | ~6.2 MB |
