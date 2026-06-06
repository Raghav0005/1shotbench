# MS MARCO Passage Search

A local Next.js web app that searches the MS MARCO V1 passage corpus via the
Anserini REST API backend.

## Architecture

```
Browser  →  Next.js (port 3000)  →  /api/search  →  Anserini REST (port 8080)
                                                         ↕
                                               msmarco-v1-passage index
```

- **Frontend**: Next.js 15 on port 3000 (configurable via `PORT`)
- **Backend**: Anserini `RestServer` on port 8080 (configurable via `ANSERINI_BACKEND_PORT` or `ANSERINI_BACKEND_URL`)

## Prerequisites

- Java 21
- Node.js 18+
- Anserini fatjar (see below)

## 1 — Install the Anserini fatjar

```bash
# From the workspace root (parent of this directory)
ANSERINI_VERSION=$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
  | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')

curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

export ANSERINI_JAR="anserini-${ANSERINI_VERSION}-fatjar.jar"
```

## 2 — Start the Anserini REST server

```bash
# This will automatically download the msmarco-v1-passage prebuilt index on first use (~3 GB)
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```

Wait until you see the server ready message before opening the frontend.

### Custom backend port

```bash
ANSERINI_BACKEND_PORT=9090 java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 9090
```

Then start the frontend with the matching variable (see below).

## 3 — Start the Next.js frontend

```bash
cd msmarco-search
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Custom ports

```bash
# Frontend on port 4000, backend on port 9090
PORT=4000 ANSERINI_BACKEND_PORT=9090 npm run dev

# Or provide a full backend URL
ANSERINI_BACKEND_URL=http://my-host:8080 npm run dev
```

## REST API used

The Next.js API route `/api/search` proxies to:

```
GET http://localhost:8080/v1/msmarco-v1-passage/search?query=<query>&hits=10
```

Response shape (from Anserini):
```json
{
  "api": "v1",
  "index": "msmarco-v1-passage",
  "query": { "text": "..." },
  "candidates": [
    { "docid": "...", "score": 12.34, "rank": 1, "doc": "passage text" }
  ]
}
```

## Sample queries

On each page load the app randomly selects 8 queries from the 6 980-query
MS MARCO passage dev set (`msmarco-v1-passage.dev`), embedded in
`public/msmarco-queries.json`. Click any chip to run that query instantly, or
press **↺ Refresh** to draw a new set.
