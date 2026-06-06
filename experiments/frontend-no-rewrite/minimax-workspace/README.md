# MS MARCO Passage Search App

A small end-to-end search app for the MS MARCO V1 passage corpus. The Next.js
frontend talks to the Anserini REST server (the `io.anserini.api.RestServer`
fatjar class from `$anserini-cli`) and shows random sample queries from the
MS MARCO V1 passage dev topic set on every page load.

## Architecture

```
+----------------+    /api/search, /api/sample-queries    +-----------------+
|  Next.js app   |  ---------------------------------->  |  Anserini REST  |
|   (port 3000)  |  <----------------------------------   |  (port 8080)    |
+----------------+        JSON { candidates, ... }        +-----------------+
```

- **Backend**: Anserini REST server. Started via `scripts/start-backend.sh`,
  which runs `io.anserini.api.RestServer --host $BACKEND_HOST --port $BACKEND_PORT`
  against the prebuilt `msmarco-v1-passage` index.
- **Frontend**: Next.js 15 (App Router, TypeScript) on port 3000 by default.
  Two API routes proxy to the backend so the browser never talks to Anserini
  directly:
  - `GET /api/sample-queries?count=N` — returns `N` random MS MARCO V1 passage
    dev queries (sourced from `data/msmarco-v1-passage.dev.json`).
  - `GET /api/search?query=...&hits=N` — calls Anserini's
    `GET /v1/msmarco-v1-passage/search?query=...&hits=N` and returns the JSON
    response (`{ api, index, query, candidates: [{ docid, score, rank, doc }] }`).

## Prerequisites

- **Java 21** on `PATH` (`java -version` should report 21.x).
- **Node.js 20+** and **npm 10+** (`node -v`, `npm -v`).
- The Anserini fatjar downloaded into the repo root. The `install-anserini-fatjar`
  skill's workflow already produces `anserini-2.1.1-fatjar.jar` here; if that
  file is missing, re-run it:
  ```bash
  curl -fL -o anserini-2.1.1-fatjar.jar \
    "https://repo1.maven.org/maven2/io/anserini/anserini/2.1.1/anserini-2.1.1-fatjar.jar"
  ```
- The MS MARCO V1 passage dev topics saved as
  `data/msmarco-v1-passage.dev.json` (already checked in alongside this README;
  regenerate with the `TopicsRegistry` CLI from `$anserini-cli` if needed).

## Configuration

All ports are configurable via env vars; the defaults match the PRD.

| Variable        | Default     | Used by                                    |
| --------------- | ----------- | ------------------------------------------ |
| `BACKEND_HOST`  | `localhost` | `scripts/start-backend.sh`, `lib/queries.ts` |
| `BACKEND_PORT`  | `8080`      | `scripts/start-backend.sh`, `lib/queries.ts` |
| `FRONTEND_PORT` | `3000`      | `scripts/start-frontend.sh`                |

A starter `.env` file is provided as `.env.example`:
```bash
cp .env.example .env
# edit .env if you need to change ports
```

## Run locally

```bash
# Install JS dependencies the first time.
npm install

# Start the Anserini backend and the Next.js frontend together.
# (Press Ctrl-C to stop both.)
npm run dev
```

The first time the backend starts, Anserini downloads the
`msmarco-v1-passage` prebuilt index (~2.1 GB) into `~/.cache/pyserini/indexes/`
and may take several minutes. The frontend will then be reachable at
`http://localhost:3000` and will talk to the backend at
`http://localhost:8080`.

You can also start the two processes separately:
```bash
npm run start:backend   # Anserini REST server on $BACKEND_PORT
npm run start:frontend  # Next.js dev server on $FRONTEND_PORT
```

## Using the app

- The home page shows a search input and five random MS MARCO V1 passage dev
  queries ("sample queries"). Each sample is tagged with its `qid` and clicking
  one runs it through the Anserini backend.
- Use **Shuffle** to draw a new batch of sample queries.
- Type your own query and press **Search** (or Enter). Empty submissions show
  a friendly error; backend errors and zero-result searches are surfaced
  inline.
- Recent queries are kept in `localStorage` for quick re-runs in the same
  browser.
- Each result shows the rank, docid, BM25 score, and the raw passage text
  returned by the Anserini REST server.

## Smoke test (Anserini)

To re-verify the Anserini fatjar after a fresh install, the
`install-anserini-fatjar` skill recommends running:

```bash
ANSERINI_JAR="$(pwd)/anserini-2.1.1-fatjar.jar"
java -cp "$ANSERINI_JAR" io.anserini.search.SearchCollection \
  -threads 1 -index cacm -topics cacm \
  -output run.cacm.bm25.txt -hits 1000 -bm25
java -cp "$ANSERINI_JAR" io.anserini.eval.TrecEval \
  -c -m map -m P.30 cacm run.cacm.bm25.txt
```

Expected metrics: MAP `0.3123`, P30 `0.1942`.

## Files of interest

```
app/
  layout.tsx                    root layout + metadata
  page.tsx                      home page (server component)
  globals.css                   dark theme styles
  components/
    SearchApp.tsx               client-side search UI
    SearchApp.module.css
  api/
    sample-queries/route.ts     GET /api/sample-queries
    search/route.ts             GET /api/search
lib/
  queries.ts                    dev query loader + backend URL helper
data/
  msmarco-v1-passage.dev.json   6980 dev queries from $anserini-cli TopicsRegistry
scripts/
  start-backend.sh              Anserini REST launcher
  start-frontend.sh             Next.js launcher
anserini-2.1.1-fatjar.jar       Anserini REST/CLI server (downloaded by install-anserini-fatjar)
```
