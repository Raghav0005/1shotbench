# NFCorpus Live Retrieval Diagnostics Workbench

A containerized web application providing a live, interactive interface for NFCorpus retrieval diagnostics powered by [Anserini](https://github.com/castorini/anserini).

## Features

- **Live NFCorpus Search**: Type queries and get real-time ranked results from Anserini's prebuilt NFCorpus index
- **BM25 Evaluation**: Run and verify BM25 evaluation metrics against expected reproduction targets
- **Readiness Dashboard**: Monitor Java, Anserini fatjar, NFCorpus index, and reproduction discovery status
- **Command Transparency**: Inspect exact Anserini commands, output, and generated artifact paths
- **Verification**: Browser-driven confirmation that results come from real Anserini — no mocks

## Quick Start

### Docker (Recommended)

```bash
docker build -t nfcorpus-workbench .
docker run -p 10000:10000 nfcorpus-workbench
```

The app will be available at `http://localhost:10000`.

### Local Development

```bash
# Prerequisites: Java 21+, Python 3.10+
pip install -r requirements.txt
cd app
python run.py
```

## Architecture

```
├── app/
│   ├── backend/
│   │   ├── app.py          # Flask application & API routes
│   │   ├── anserini.py     # Anserini CLI integration (real commands)
│   │   └── config.py       # Configuration
│   ├── frontend/
│   │   ├── index.html      # Dashboard UI
│   │   ├── style.css       # Dark theme styles
│   │   └── app.js          # Frontend JavaScript
│   ├── run.py              # Local entry point
│   └── wsgi.py             # Gunicorn entry point
├── tests/
│   └── test_browser.py     # Playwright end-to-end tests
├── Dockerfile              # Render-compatible Docker config
├── requirements.txt        # Python dependencies
└── README.md
```

## Deployment to Render

1. Push this repository to GitHub/GitLab
2. Create a new **Web Service** on [Render](https://render.com)
3. Select **Docker** as the environment
4. Set the port to `10000`
5. Render will build and deploy automatically

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `10000` | HTTP port (Render sets this automatically) |
| `ANSERINI_JAR` | `""` | Path to Anserini fatjar (auto-downloaded if empty) |
| `ANSERINI_VERSION` | `""` | Specific Anserini version (auto-discovered if empty) |
| `CACHE_DIR` | `./data` | Directory for downloaded artifacts |

### Render Service Configuration

- **Runtime**: Docker
- **Port**: `10000`
- **Health Check Path**: `/health`
- **Instance Type**: Starter or higher (needs Java + ~2GB for NFCorpus index)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/health` | GET | Health/readiness JSON |
| `/api/status` | GET | Full component status |
| `/api/search` | POST | Live search (`{"query": "...", "hits": 10}`) |
| `/api/evaluation` | GET | BM25 evaluation results |
| `/api/evaluation/rerun` | POST | Force re-run evaluation |
| `/api/commands` | GET | Command log & artifacts |

## How It Works

1. **Startup**: Downloads the Anserini fatjar from Maven Central
2. **Smoke Test**: Runs CACM retrieval to verify the fatjar works
3. **Reproduction Discovery**: Uses Anserini's `ReproduceFromPrebuiltIndexes` to find NFCorpus configs and expected metrics
4. **Index Setup**: Downloads the NFCorpus prebuilt index via a test retrieval
5. **BM25 Evaluation**: Runs `SearchCollection` + `TrecEval` and compares against expected metrics
6. **Live Search**: Accepts user queries and runs them via Anserini's `cli.Search`

All commands are real Anserini invocations — no mocked results.

## Running Tests

```bash
# Install test dependencies
pip install playwright pytest
playwright install chromium

# Start the app (in another terminal)
cd app && python run.py

# Run tests
APP_URL=http://localhost:10000 pytest tests/test_browser.py -v
```

## Dataset Scope

This workbench is limited to **NFCorpus only** (a subset of BEIR). It does not download all BEIR corpora, MS MARCO, or any large datasets. The NFCorpus prebuilt index is approximately 50MB.

## License

This project uses Anserini, which is licensed under the Apache License 2.0.
