# NFCorpus Live Retrieval Diagnostics Workbench

A Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini.

## Overview

This app demonstrates a real Anserini-backed IR workflow for the small NFCorpus (BEIR v1.0.0) dataset:

- Downloads and verifies an Anserini fatjar from Maven Central.
- Downloads the NFCorpus dataset (~2.4 MB).
- Builds a local Lucene inverted index using `BeirFlatCollection`.
- Runs BM25 batch retrieval with `SearchCollection` over NFCorpus test topics.
- Evaluates the run with Anserini's Java `TrecEval` wrapper.
- Compares observed metrics against the expected reproduction targets.
- Exposes live query search via the `io.anserini.cli.Search` CLI.
- Shows exact commands, artifact paths, and output previews in the browser.

## Tech Stack

- **Backend**: Python 3.11 + Flask
- **Frontend**: Vanilla HTML/JS
- **Search Engine**: Anserini (Java 21, fatjar from Maven Central)
- **Dataset**: NFCorpus (BEIR v1.0.0) — 3,633 documents, 323 test queries
- **Deployment**: Docker / Render web service

## Running Locally

### Prerequisites

- Python 3.11+
- Java 21 (OpenJDK)

### Install Python dependencies

```bash
pip install -r requirements.txt
```

### Run the app

```bash
python app.py
```

The app will:
1. Download the Anserini fatjar if not already cached.
2. Download and extract NFCorpus.
3. Build the Lucene index.
4. Run BM25 evaluation.
5. Start the web server on `http://localhost:10000`.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `10000` | HTTP server port |
| `ANSERINI_VERSION` | `2.1.1` | Anserini release to download |
| `CACHE_DIR` | `.cache` | Directory for the fatjar |
| `DATA_DIR` | `data` | Directory for corpus and qrels |
| `INDEX_DIR` | `indexes` | Directory for the Lucene index |
| `RUNS_DIR` | `runs` | Directory for run files and eval output |

## Running in Docker

```bash
docker build -t nfcorpus-workbench .
docker run -p 10000:10000 nfcorpus-workbench
```

The container binds to `0.0.0.0` and respects the `PORT` environment variable.

## Deploying to Render

1. Push this directory to a Git repository.
2. In Render, create a new **Web Service** and choose the repository.
3. Select **Docker** as the runtime.
4. Render will use the included `Dockerfile`.
5. The service will start on the port assigned by Render's `PORT` environment variable.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | JSON health check with Java, NFCorpus, search, and evaluation readiness |
| `/api/status` | GET | Detailed setup status, logs, commands, artifacts, and sample queries |
| `/api/search` | POST | Live BM25 search over NFCorpus; body `{"query": "...", "hits": 10}` |
| `/api/evaluation` | GET | BM25 evaluation results with observed, expected, deltas, and status |
| `/api/evaluation/rerun` | POST | Re-run SearchCollection + TrecEval and return fresh results |
| `/api/commands` | GET | Exact commands and artifact paths used during setup |

## Browser Tests

Install test dependencies (Playwright browsers):

```bash
playwright install chromium
```

Run the end-to-end verification:

```bash
pytest tests/test_app.py -v
```

The browser test proves the app exercises real Anserini commands and does not mock search or evaluation results.

## Design Notes

- **NFCorpus-specific**: The app only downloads and indexes NFCorpus. It does not fetch other BEIR corpora.
- **Real commands only**: Search and evaluation results come from actual `java -cp anserini-*.jar ...` subprocess invocations.
- **No mocked data**: Expected metrics are sourced from Anserini's bundled reproduction config (`beir-v1.0.0-nfcorpus.flat`).
- **Transparency**: Every step records the exact shell command and output file paths for inspection in the UI.
