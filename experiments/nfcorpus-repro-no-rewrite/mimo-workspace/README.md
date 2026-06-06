# NFCorpus Retrieval Diagnostics Workbench

A Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini.

## Features

- **Live Search**: Run queries against the NFCorpus medical literature collection via Anserini's prebuilt index
- **BM25 Evaluation**: Automated evaluation with expected vs. observed nDCG@10 metrics
- **Command Transparency**: Every Anserini command, output, and artifact path is inspectable
- **Readiness Dashboard**: Real-time status of Java, Anserini fatjar, NFCorpus index, and evaluation

## Architecture

- **Backend**: Python/Flask serving API endpoints backed by real Anserini CLI commands
- **Index**: BEIR NFCorpus prebuilt inverted index (`beir-v1.0.0-nfcorpus.flat`)
- **Evaluation**: `SearchCollection` → TREC run file → `TrecEval` → nDCG@10 comparison
- **Frontend**: Single-page dashboard with live search, status panels, evaluation metrics, and command drawer

## Quick Start (Local)

```bash
# Install deps
pip install -r requirements.txt

# Set environment (defaults work for local dev)
export ANSERINI_JAR=./anserini-2.1.1-fatjar.jar
export DATA_DIR=./data
export PORT=10000

# Run
python run.py
```

Open http://localhost:10000

## Docker

```bash
docker build -t nfcorpus-workbench .
docker run -p 10000:10000 nfcorpus-workbench
```

## Render Deployment

1. Connect this repository to Render
2. Create a new **Web Service**
3. Select **Docker** as the environment
4. Set the port to `10000`
5. Render will build the Dockerfile automatically

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `10000` | HTTP port (Render sets this automatically) |
| `HOST` | `0.0.0.0` | Bind address |
| `ANSERINI_JAR` | `./anserini-2.1.1-fatjar.jar` | Path to Anserini fatjar |
| `DATA_DIR` | `./data` | Directory for run files, eval output, and logs |

### PORT Binding Contract

The app binds to `0.0.0.0:${PORT}` where `PORT` defaults to `10000` when unset.
Render automatically sets the `PORT` environment variable. The app reads it at startup.

### Health Endpoint

```
GET /health
```

Returns JSON:
```json
{
  "status": "ok",
  "anserini_available": true,
  "nfcorpus_ready": true,
  "search_available": true,
  "evaluation_available": true,
  "java_version": "openjdk version \"21.0.11\"",
  "error": null
}
```

### Persistent Storage

If you need persistent storage for the NFCorpus index cache on Render, mount a disk at `/app/data`.

## Testing

### End-to-End Browser Test (Playwright)

```bash
pip install playwright pytest
playwright install chromium
pytest tests/test_e2e.py -v
```

The test verifies:
- Health/readiness panel appears
- NFCorpus is identified as the active dataset
- Anserini setup status is visible
- Live search returns ranked results with docids, ranks, scores, and text
- Evaluation panel shows numeric observed metrics
- Expected metric information appears
- Observed-vs-expected comparison status/delta appears
- Command text and artifact paths are visible
- The app uses real Anserini commands (not mocked)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/health` | GET | Health/readiness JSON |
| `/api/status` | GET | Detailed status JSON |
| `/api/search` | POST | Live NFCorpus search `{"query": "..."}` |
| `/api/evaluation` | GET | BM25 evaluation results |
| `/api/evaluation/rerun` | POST | Trigger evaluation rerun |
| `/api/commands` | GET | Command execution log |

## Expected Metrics

| Metric | Expected | Source |
|--------|----------|--------|
| nDCG@10 | 0.3218 | Anserini `beir.core` reproduction config |

## Data Artifacts

Generated at runtime in `DATA_DIR`:

- `run.nfcorpus.bm25.txt` — TREC-format BM25 run file
- `eval.nfcorpus.bm25.txt` — TrecEval output with nDCG@10
