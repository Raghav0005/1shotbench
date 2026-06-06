# MS MARCO Passage Search App

A local search application with a **Next.js frontend** and an **Anserini REST API backend** that searches over the MS MARCO passage corpus.

## Quick Start

```bash
# 1. Install the Anserini fatjar (one-time setup)
ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
  | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Start both servers
./start.sh
```

Then open **http://localhost:3000** in your browser.

## Configuration

| Variable              | Default                | Description                        |
| --------------------- | ---------------------- | ---------------------------------- |
| `BACKEND_PORT`        | `8080`                 | Port for the Anserini REST server  |
| `FRONTEND_PORT`       | `3000`                 | Port for the Next.js dev server    |
| `ANSERINI_BACKEND_URL`| `http://localhost:8080`| Backend URL (used by API route)    |

Example with custom ports:

```bash
BACKEND_PORT=9090 FRONTEND_PORT=4000 ./start.sh
```

## Architecture

- **Backend**: Anserini REST API server (`io.anserini.api.RestServer`) serves search over the `msmarco-v1-passage` prebuilt index.
- **Frontend**: Next.js app at `/src/app/page.tsx` with an API proxy route at `/src/app/api/search/route.ts`.
- **Sample Queries**: 50 randomly selected queries from the MS MARCO passage dev set are embedded in the frontend. On each page load, 8 are randomly chosen as clickable suggestions.

## Features

- Search the MS MARCO passage corpus through Anserini BM25
- Random sample queries from the MS MARCO dev set shown on each page load
- Click a sample query to run it immediately
- Ranked results with docid, score, and passage text
- Handles empty queries, no-results states, and backend errors
- Configurable ports via environment variables
