# NFCorpus Live Retrieval Diagnostics Workbench

A Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini.

## Features

- **Live Search**: Query NFCorpus through an Anserini-backed CLI in real time
- **BM25 Evaluation**: Automatic BM25 evaluation with observed-vs-expected metric comparison
- **Diagnostics Dashboard**: Readiness panel, command inspection, artifact paths
- **No Mocks**: All search and evaluation backed by real Anserini commands

## Quick Start

### Local (Python)

```bash
pip3 install flask
python3 app/server.py
# Open http://localhost:10000
```

### Docker

```bash
docker build -t nfcorpus-diagnostics .
docker run -p 10000:10000 nfcorpus-diagnostics
# Open http://localhost:10000
```

### Render Deployment

This app is designed as a **Docker web service** for Render:

1. Connect your repo to Render
2. Choose "Docker" as the environment
3. The Dockerfile handles everything — Java 21, Python, Flask, Anserini download
4. The container binds HTTP to `0.0.0.0` and reads `PORT` from the environment (default: `10000`)
5. No interactive setup required after container start

## Port Binding

- Binds to `0.0.0.0`
- Reads `PORT` from environment, defaults to `10000`
- Render's `PORT` env var is respected automatically

## Data Directory

Runtime caches and artifacts live under `DATA_DIR` (default: `./data`):

```
data/
  jar/          # Anserini fatjar
  cache/        # Prebuilt index cache (managed by Anserini)
  runs/         # TREC run files and evaluation output
  logs/         # Setup and command logs
```

For persistent storage on Render, mount a disk at `/app/data` and set `DATA_DIR=/app/data`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health/readiness JSON |
| `/api/status` | GET | Detailed system status |
| `/api/search` | POST | Live search (`{"query": "...", "hits": 10}`) |
| `/api/evaluation` | GET | BM25 evaluation results and comparison |
| `/api/commands` | GET | Exact commands used and artifact paths |
| `/api/rerun-evaluation` | POST | Trigger a fresh BM25 evaluation |
| `/api/sample-queries` | GET | NFCorpus sample queries |
| `/api/artifacts/<name>` | GET | Download artifact files |

## Browser Tests

```bash
npm install
npx playwright install chromium
APP_URL=http://localhost:10000 npx playwright test
```

The Playwright test verifies:
- Health/readiness panel appears
- NFCorpus is identified as the active dataset
- Anserini setup status is visible
- Live search returns ranked results with docids, scores, and text
- Evaluation panel shows numeric observed metrics
- Expected metric information and comparison status appear
- Exact command text and artifact paths are visible

## Architecture

- **Backend**: Python Flask (`app/server.py`)
- **Frontend**: Single-page HTML (`app/static/index.html`)
- **Search**: `io.anserini.cli.Search` with `--json` output against prebuilt `beir-v1.0.0-nfcorpus.flat` index
- **Evaluation**: `io.anserini.search.SearchCollection` + `io.anserini.eval.TrecEval`
- **Expected Metrics** (from Anserini reproduction config):
  - nDCG@10: 0.3218
  - R@100: 0.2457
  - R@1000: 0.3704
