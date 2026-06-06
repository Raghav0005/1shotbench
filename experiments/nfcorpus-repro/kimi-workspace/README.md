# NFCorpus Live Retrieval Diagnostics Workbench

A containerized web application that delivers live NFCorpus retrieval diagnostics powered by [Anserini](https://github.com/castorini/anserini). Deployable as a Docker web service on Render.

## What it does

- **Installs & verifies Anserini** using the published Maven Central fatjar.
- **Discovers expected metrics** via Anserini’s reproduction workflow (`ReproduceFromPrebuiltIndexes`).
- **Downloads & caches** the small NFCorpus prebuilt index (~6.5 MB) — no full-BEIR download required.
- **Runs live BM25 search** against NFCorpus through Anserini’s `Search` CLI.
- **Executes & verifies** a BM25 evaluation (`SearchCollection` + `TrecEval`) and compares observed vs. expected nDCG@10.
- **Surfaces everything** in the browser: exact commands, artifact paths, observed/expected metrics, deltas, and pass/close/fail status.

## Stack

- **Backend**: Python 3.11 + Flask + Gunicorn
- **Frontend**: Vanilla HTML/JS (single page)
- **IR Engine**: Anserini 2.1.1 fatjar + Java 21
- **Test**: pytest-playwright (browser end-to-end validation)

## Local development

### Requirements

- Python 3.11+
- Java 21
- curl

### Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:10000.

### Run with Docker

```bash
docker build -t nfcorpus-diagnostics .
docker run -p 10000:10000 nfcorpus-diagnostics
```

Open http://localhost:10000.

## End-to-end test

The test suite launches the application in a browser and validates the primary workflow. It will **fail** if search results or evaluation output are mocked rather than produced by genuine Anserini commands.

```bash
# Install test dependencies
pip install -r requirements.txt

# Start the app in the background
python app.py &

# Run tests (pytest-playwright)
pytest tests/test_e2e.py --headed

# Or use the standalone script if pytest has environment issues:
python tests/test_e2e_standalone.py
```

## Deployment on Render

1. Create a new **Web Service** on Render.
2. Choose **Deploy from existing image** or connect this repo and let Render build the Dockerfile.
3. Set the environment variable `PORT` to `10000` (or leave unset; the app defaults to `10000`).
4. Render will bind HTTP to `0.0.0.0:PORT` automatically.

The container is self-contained: it downloads the Anserini fatjar on first startup and caches artifacts under `/app/cache`.

### Persistent disk on Render (optional)
If you want the Anserini fatjar and NFCorpus index to survive container restarts without re-downloading, mount a Render **Disk** to `/app/cache`.

## Health endpoint

`GET /health` returns:

```json
{
  "status": "healthy",
  "anserini_available": true,
  "nfcorpus_ready": true,
  "search_available": true,
  "evaluation_available": true
}
```

## API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard UI |
| `/health` | GET | Readiness JSON |
| `/api/status` | GET | Detailed status, commands, artifacts |
| `/api/topics` | GET | Sample NFCorpus topics |
| `/api/search?q=...&hits=N` | GET | Live Anserini search (JSON) |
| `/api/evaluate` | GET | Current evaluation state |
| `/api/evaluate` | POST | Trigger a fresh evaluation run |

## Cache & artifacts

Runtime caches and generated files are stored under `./cache` (or `/app/cache` in Docker):

- `anserini-2.1.1-fatjar.jar`
- `run.nfcorpus.bm25.txt`
- `eval.nfcorpus.bm25.txt`
- `setup.log`, `eval.log`, `discovery.log`

The NFCorpus Lucene index is cached by Anserini itself under `~/.cache/pyserini/indexes/` (or `/root/.cache/pyserini/indexes/` inside the Docker container).

## Notes

- This demonstration is intentionally confined to **NFCorpus only**.
- No full-BEIR download, no MS MARCO, no dense retrieval, and no user accounts.
- All search and evaluation results are produced by real Anserini CLI invocations; nothing is hardcoded or mocked.
