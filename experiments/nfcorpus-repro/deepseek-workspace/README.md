# NFCorpus Live Retrieval Diagnostics Workbench

A Docker-based web application for live retrieval diagnostics on the NFCorpus benchmark using Anserini BM25. Deployable as a Render Docker web service.

## Architecture

- **Backend**: Python Flask + Gunicorn
- **Search engine**: Anserini 2.x fatjar (downloaded from Maven Central at build time)
- **Dataset**: NFCorpus (BEIR subset), prebuilt inverted index auto-downloaded on first use
- **Reproduction config**: `beir.core` from Anserini's `ReproduceFromPrebuiltIndexes`

### Key Commands Used

| Stage | Anserini Command |
|-------|-----------------|
| Smoke test | `io.anserini.search.SearchCollection -index cacm -topics cacm -bm25` |
| Smoke eval | `io.anserini.eval.TrecEval -m map -m P.30 cacm run.cacm.bm25.txt` |
| NFCorpus search | `io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat --query "..." --hits 10 --json` |
| NFCorpus batch | `io.anserini.search.SearchCollection -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -bm25 -removeQuery` |
| NFCorpus eval | `io.anserini.eval.TrecEval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test run.nfcorpus.bm25.flat.txt` |

### Expected Metric

| Metric | Expected Value | Source |
|--------|---------------|--------|
| nDCG@10 | 0.3218 | `beir.core` reproduction config (flat BM25) |

## Docker Deployment (Render)

### Environment Variables

- `PORT` - HTTP port (default: `10000`)

### Build & Run Locally

```bash
# Build
docker build -t nfcorpus-diagnostics .

# Run
docker run -p 10000:10000 -e PORT=10000 nfcorpus-diagnostics
```

### Docker Compose

```bash
docker compose up --build
```

Open http://localhost:10000

### Render Deployment

1. Create a new **Web Service** on Render
2. Set:
   - **Runtime**: Docker
   - **Dockerfile path**: `./Dockerfile`
   - **Port**: `10000` (or set `PORT` env var)
   - **Health Check Path**: `/health`
3. Optional: mount a persistent disk at `/home/anserini/.cache/anserini` to persist the downloaded NFCorpus index across deploys (recommended size: 5 GB)

### Render Docker Commands (for reference)

```dockerfile
# The Dockerfile handles:
# - Java 21 through eclipse-temurin:21-jre
# - Fatjar download from Maven Central at build time
# - pip install of Flask + Gunicorn
# - Binding to 0.0.0.0:$PORT
```

### Service Readiness Contract

The container:
- Binds HTTP to `0.0.0.0`
- Reads the `PORT` environment variable, defaulting to `10000`
- Exposes a `/health` endpoint returning JSON with `app_status`, `anserini_available`, `nfcorpus_ready`, `search_available`, `evaluation_available`

## Endpoints

| Endpoint | Description |
|----------|------------|
| `GET /` | Diagnostics dashboard |
| `GET /health` | Health check JSON |
| `GET /api/status` | Full readiness status |
| `GET /api/search?query=...` | Live Anserini search over NFCorpus |
| `GET /api/evaluate[?force=1]` | Run or retrieve BM25 evaluation |
| `GET /api/commands` | Command execution history |
| `GET /api/artifacts` | Generated artifact paths and previews |

## E2E Verification Test

```bash
# Start the app
python app.py

# In another terminal
pip install playwright
python tests/test_e2e.py
```

The test verifies:
- Health/readiness panel with Anserini + NFCorpus status
- NFCorpus identified as active dataset
- Live search returns real ranked results with ids, scores, text
- BM25 evaluation produces numeric observed metrics
- Expected metrics from reproduction config are displayed
- Observed-vs-expected comparison with pass/close/fail status
- Command history with SearchCollection, TrecEval, NFCorpus references
- Artifact paths with NFCorpus run files
- Docker/Render PORT binding contract

## Cache & Data Directories

- `/app/cache/` - Application cache (run files, eval output)
- `~/.cache/anserini/indexes/beir-v1.0.0-nfcorpus.flat/` - Downloaded NFCorpus prebuilt index

On Render, mount a persistent disk at `/home/anserini/.cache/anserini` to preserve the index.
