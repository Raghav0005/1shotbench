# NFCorpus Live Retrieval Diagnostics Workbench

A small, dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini.

## Setup & Running Locally
1. Install dependencies: `npm install`
2. Download Anserini fatjar: `./download_fatjar.sh`
3. Prepare NFCorpus prebuilt index: `./setup_nfcorpus.sh`
4. Start the server: `npm start`
5. Visit `http://localhost:10000`

## Deployment (Render & Docker)
This project is designed to be deployed as a Docker web service. 
- It binds to `0.0.0.0`.
- It uses the `PORT` environment variable (defaults to `10000` if unset).
- The `Dockerfile` includes all necessary steps to install Java 21, download the Anserini fatjar, pre-cache the NFCorpus dataset, and run the server.

To run with Docker:
```bash
docker build -t nfcorpus-diagnostics .
docker run -p 10000:10000 -e PORT=10000 nfcorpus-diagnostics
```

## Storage & Caches
- **Anserini/Pyserini cache**: Prebuilt indexes are downloaded to `~/.cache/pyserini/indexes/`. In the Docker image, this is cached at build time. If you need a persistent cache on Render, you can mount a persistent disk to `/root/.cache/` (or the equivalent home dir).
- **Run Files**: Temporary runs and evaluation output are generated in the `runs/` directory in the app's root.

## Available Endpoints
- `/health`: JSON readiness check for App, Anserini, and NFCorpus.
- `/api/search?q=...`: Live query search using Anserini's CLI search.
- `/api/eval`: Returns cached evaluation results (BM25 vs NFCorpus).
- `/api/eval/rerun`: Re-runs the evaluation using `trec_eval` and Anserini `SearchCollection`.
