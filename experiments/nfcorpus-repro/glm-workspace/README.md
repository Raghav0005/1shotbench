# NFCorpus Live Retrieval Diagnostics Workbench

A Docker-packaged web application providing live NFCorpus retrieval diagnostics powered by Anserini.

## Quick Start (Local)

```bash
# Option 1: Run directly with Python
pip install -r requirements.txt
export ANSERINI_VERSION=2.1.1
python3 app/server.py

# Option 2: Docker
docker build -t nfcorpus-workbench .
docker run -p 10000:10000 nfcorpus-workbench
```

Then open http://localhost:10000

## Render Deployment

This application is designed as a **Render Docker web service**:

1. Connect your repository to Render
2. Select **Docker** as the environment
3. The container:
   - Binds HTTP to `0.0.0.0`
   - Reads `PORT` from environment variable (default: `10000`)
   - Downloads Anserini fatjar and NFCorpus artifacts on startup
   - Runs BM25 evaluation during startup
   - Requires no interactive setup after container start

### Render Configuration
- **Environment**: Docker
- **Dockerfile Path**: `./Dockerfile`
- **Instance Type**: Starter (512MB RAM is sufficient)
- **Port**: Render auto-assigns `PORT` env var

### Health Endpoint
`GET /health` returns JSON:
```json
{
  "status": "ok",
  "anserini_available": true,
  "nfcorpus_ready": true,
  "search_available": true,
  "evaluation_available": true,
  "setup_status": "done",
  "setup_error": null
}
```

## Runtime Cache

All downloaded and generated files reside under:
- `WORKBENCH_HOME` (default: `/opt/workbench`)
- Data directory: `$WORKBENCH_HOME/data/`

If persistent storage is needed on Render, mount a disk at `/opt/workbench/data`.

## Browser Test

Run the Playwright end-to-end test:

```bash
npm install
npx playwright install chromium
npx playwright test
```

## Architecture

- **Backend**: Python/Flask serving a single-page HTML dashboard
- **Search**: Uses `io.anserini.cli.Search` CLI against the `beir-v1.0.0-nfcorpus.flat` prebuilt index
- **Evaluation**: Uses `io.anserini.search.SearchCollection` + `io.anserini.eval.TrecEval`
- **Reproduction**: Uses `beir.core` config from `ReproduceFromPrebuiltIndexes` for expected metrics
- **Expected nDCG@10**: 0.3218 (from Anserini's `beir.core` reproduction config)
