# MS MARCO Passage Search App

A local search application with a Next.js frontend and an Anserini REST API backend for searching the MS MARCO passage corpus.

## Architecture

- **Backend**: Anserini REST API server (`io.anserini.api.RestServer`) serving the `msmarco-v1-passage` prebuilt index
- **Frontend**: Next.js app with search interface, sample queries, and ranked results

## Setup

### 1. Install Anserini

The Anserini fatjar (`anserini-2.1.1-fatjar.jar`) is already downloaded and verified in this directory.

Smoke test verification:
```bash
ANSERINI_JAR="anserini-2.1.1-fatjar.jar"
java -cp "$ANSERINI_JAR" io.anserini.search.SearchCollection \
  -threads 1 -index cacm -topics cacm \
  -output run.cacm.bm25.txt -hits 1000 -bm25
```

### 2. Start the Backend

```bash
ANSERINI_JAR="anserini-2.1.1-fatjar.jar"
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```

Override the port via the `--port` flag.

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to port `3000`. Override it with the `PORT` environment variable:

```bash
PORT=3001 npm run dev
```

If the backend is on a non-default port, set `BACKEND_PORT` when starting the frontend:

```bash
BACKEND_PORT=8081 npm run dev
```

## Usage

Open http://localhost:3000 in your browser.

- Type a query into the search box and press **Search**
- Or click any of the randomly displayed **sample queries** to run it immediately
- Ranked passage results are shown with rank, docid, score, and passage text

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3000` | Frontend port |
| `BACKEND_PORT` | `8080` | Backend Anserini REST API port |
