# NFCorpus Live Retrieval Diagnostics Workbench

A Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics powered by Anserini.

## Features

- **Live NFCorpus Search**: Query the INEX SciMaze scientific document collection in real-time
- **BM25 Evaluation**: Run and verify BM25 retrieval metrics against NFCorpus qrels
- **Reproduction Discovery**: Uses Anserini's reproduction workflow to discover expected metrics
- **Full Transparency**: Shows exact Anserini commands, run files, and evaluation output
- **End-to-End Verification**: Playwright test proves real Anserini workflows are exercised

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run setup (downloads Anserini fatjar)
bash setup.sh

# Start the server
python3 server.py

# Open http://localhost:10000
```

### Docker

```bash
# Build image
docker build -t nfcorpus-diagnostics .

# Run container
docker run -p 10000:10000 \
    -e ANSERINI_JAR=/app/anserini-fatjar.jar \
    nfcorpus-diagnostics

# Or use docker-compose
docker-compose up
```

## Deployment to Render

This app is designed for Render Docker deployment:

1. Create a new Render Web Service
2. Connect your Git repository
3. Set the following:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python3 server.py`
4. Set environment variable `ANSERINI_JAR` pointing to your fatjar (or use the setup.sh during build)

## Docker/Render Readiness

- Container binds HTTP to `0.0.0.0`
- Uses `PORT` from environment (default: `10000`)
- No interactive setup required after container starts
- Health endpoint at `/health` returns JSON status

## Health Endpoint

```bash
curl http://localhost:10000/health
```

Response:
```json
{
  "status": "ok",
  "app": "NFCorpus Live Retrieval Diagnostics Workbench",
  "anserini_available": true,
  "nfcorpus_ready": true,
  "search_available": true,
  "evaluation_available": true,
  "port": 10000
}
```

## Architecture

- **Backend**: Flask (Python 3.11)
- **Frontend**: Vanilla JS + CSS (no framework dependencies)
- **Search**: Anserini CLI Search or REST API
- **Evaluation**: Anserini `SearchCollection` + `TrecEval`
- **Cache**: `./cache/` for NFCorpus index
- **Runs**: `./runs/` for TREC run files

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `10000` | HTTP server port |
| `ANSERINI_JAR` | `./anserini-fatjar.jar` | Path to Anserini fatjar |
| `ANSERINI_REST_PORT` | `8080` | Anserini REST server port |

## API Endpoints

- `GET /health` - Health check with system status
- `GET /api/status` - Detailed status including sample queries
- `GET /api/search?q=<query>&hits=10` - Live search
- `POST /api/evaluate` - Run BM25 evaluation
- `POST /api/evaluate/rerun` - Rerun evaluation (uses cached index)
- `GET /api/commands` - List Anserini commands used
- `GET /api/artifacts` - List generated artifact paths

## End-to-End Test

```bash
# Install Playwright
pip install playwright
playwright install chromium

# Run tests
pytest tests/test_e2e.py -v
```

## License

Apache 2.0 - See Anserini project