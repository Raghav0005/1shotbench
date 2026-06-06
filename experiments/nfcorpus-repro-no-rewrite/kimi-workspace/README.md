# NFCorpus Live Retrieval Diagnostics Workbench

A Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini.

## Overview

This app demonstrates a real IR workflow using Anserini over the BEIR NFCorpus dataset:

- **Live search** over NFCorpus via Anserini CLI-backed queries
- **BM25 evaluation** with observed vs. expected metrics (nDCG@10)
- **Transparent commands & artifacts** showing exact Anserini command lines and generated run/eval files
- **Readiness dashboard** reporting Java, fatjar, index, and evaluation status

## Quick Start (Local)

### Requirements
- Python 3.9+
- Java 21
- `curl`

### Install & Run
```bash
pip install -r requirements.txt
export ANSERINI_JAR="$(pwd)/cache/anserini-2.1.1-fatjar.jar"
export CACHE_DIR="$(pwd)/cache"
export PORT=10000
python app.py
```

Then open http://localhost:10000.

### Run Browser Tests
```bash
pip install -r requirements.txt
# Start the app in one terminal
python app.py

# In another terminal
pytest test_app.py -v
```

## Docker

### Build
```bash
docker build -t nfcorpus-workbench .
```

### Run
```bash
docker run -p 10000:10000 nfcorpus-workbench
```

### Deploy to Render
1. Push this repo to GitHub/GitLab.
2. In Render, create a new **Web Service**.
3. Select **Docker** runtime.
4. Set `PORT` to `10000` (or use the default).
5. Deploy.

The container binds HTTP to `0.0.0.0` and uses the `PORT` environment variable, defaulting to `10000`.

## Endpoints

- `GET /` — Diagnostics dashboard
- `GET /health` — JSON health status (`status`, `anserini_available`, `nfcorpus_ready`, `search_available`, `evaluation_available`)
- `GET /api/status` — Full readiness, evaluation, commands, and artifacts
- `GET /api/search?q=...&hits=...` — Live Anserini-backed NFCorpus search (JSON)
- `POST /api/evaluate` — Rerun BM25 evaluation and return metrics
- `GET /api/commands` — Exact Anserini commands used
- `GET /api/artifacts` — Paths to generated run files, eval output, etc.

## How It Works

1. **Startup**: The app verifies Java 21, locates/downloads the Anserini fatjar, runs a CACM smoke test, discovers the NFCorpus reproduction config, and verifies the NFCorpus prebuilt index.
2. **Evaluation**: On first startup, it runs `SearchCollection` over the `beir-nfcorpus` topics against the `beir-v1.0.0-nfcorpus.flat` prebuilt index with BM25, then evaluates with `trec_eval`.
3. **Live Search**: Each `/api/search` call invokes `io.anserini.cli.Search` against the same index and returns ranked results with docid, score, title, and text snippet.
4. **Transparency**: All exact commands and artifact paths are exposed in the UI and via API.

## Dataset Scope

This demo is intentionally scoped to **NFCorpus only**. It does not download the full BEIR corpus, MS MARCO, or any other large collection. The NFCorpus prebuilt index is ~6.5 MB.

## Cache Directory

Runtime artifacts are stored under `./cache` by default (or `$CACHE_DIR`):
- `cache/anserini-2.1.1-fatjar.jar` — Anserini fatjar
- `cache/runs/run.nfcorpus.bm25.txt` — TREC-format retrieval run
- `cache/runs/eval.nfcorpus.bm25.txt` — Evaluation output
- `~/.cache/pyserini/indexes/...` — Downloaded prebuilt index (managed by Anserini)

## License

MIT
