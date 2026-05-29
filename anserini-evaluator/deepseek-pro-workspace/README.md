# Anserini Prebuilt Index Evaluator

A local web application for browsing Anserini's prebuilt Lucene inverted indexes and running reproducible retrieval evaluations.

## Overview

- **Browse indexes**: Discover available prebuilt Lucene inverted indexes from Anserini's registry
- **Identify evaluable indexes**: See which indexes have compatible topics and qrels
- **Run evaluations**: Execute retrieval (SearchCollection) and evaluation (TrecEval) through a browser UI
- **Inspect results**: View evaluation scores, run metadata, and artifact paths

## Quick Start

### 1. Prerequisites

- **JDK 21+** (required by Anserini)
- **Python 3.8+** (for the Flask backend)
- **Node.js** (optional, for Playwright e2e tests)

### 2. Setup

```bash
# Run the automated setup script
bash setup.sh
```

This will:
- Check Java version
- Download the latest Anserini fatjar from Maven Central
- Run a CACM smoke test to verify the setup
- Install Python dependencies (Flask)
- Set up Playwright (if Node.js is available)

### 3. Start the Server

```bash
# If ANSERINI_JAR is not auto-detected, export it:
export ANSERINI_JAR="/path/to/anserini-X.Y.Z-fatjar.jar"

# Start the evaluator
python3 server.py
```

The app will be available at **http://localhost:8089**.

### 4. Run the E2E Test

```bash
# In another terminal, while the server is running:
npm install
npx playwright install chromium
node test_e2e.mjs
```

## Architecture

```
anserini-evaluator/
├── server.py          # Flask backend – wraps Anserini CLI
├── static/
│   └── index.html     # Browser frontend (SPA)
├── test_e2e.mjs       # Playwright end-to-end test
├── setup.sh           # Automated setup script
├── requirements.txt   # Python dependencies
└── package.json       # Node.js dependencies (Playwright)
```

### Backend API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Check Java + fatjar availability |
| `/api/indexes` | GET | List prebuilt indexes with evaluable status |
| `/api/topics` | GET | List available topic sets |
| `/api/metrics` | GET | List available evaluation metrics |
| `/api/pairings/<name>` | GET | Get topic/qrels pairing for an index |
| `/api/evaluate` | POST | Run retrieval + evaluation |
| `/api/run-file/<path>` | GET | Serve generated run/eval files |

### Index-Topic-Qrels Pairing

The app automatically discovers evaluable pairings by:
1. Querying the prebuilt index registry for all Lucene inverted indexes
2. Querying the topics registry for available topic sets
3. Matching indexes to topics/qrels by name (e.g., `cacm` → `cacm` / `cacm`)

CACM is supported as the default evaluation target with its prebuilt index, topics, and qrels all sharing the `cacm` symbol.

## Metrics

Available evaluation metrics (mapped to Anserini `trec_eval` arguments):

| UI Label | trec_eval Argument |
|----------|-------------------|
| nDCG@10 | ndcg_cut.10 |
| Recall@1000 | recall.1000 |
| MAP | map |
| P@10 | P.10 |
| P@30 | P.30 |
| Rprec | Rprec |
| MRR | recip_rank |

## Limitations

- Only Lucene inverted indexes are evaluable (flat, impact, and HNSW indexes are catalog-only)
- Index-topic pairings are based on naming conventions; some valid pairings may not be auto-discovered
- The app uses the fatjar CLI, not the REST API or source checkout
- Single-metric evaluation per run (not batch multi-metric)

## Related Skills

- `install-anserini-fatjar` — Download and verify the Anserini fatjar
- `anserini-cli` — Anserini command-line usage reference
- `anserini-reproduction` — Reproduce published Anserini results
