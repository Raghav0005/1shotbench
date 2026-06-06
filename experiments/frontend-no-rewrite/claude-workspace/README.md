# MS MARCO Passage Search App

Local search application backed by the [Anserini](https://github.com/castorini/anserini)
REST API and a [Next.js](https://nextjs.org/) frontend. Queries the
`msmarco-v1-passage` prebuilt index and shows random sample queries drawn from
the MS MARCO passage dev set on each page load.

## Layout

```
.
├── anserini-2.1.1-fatjar.jar     # downloaded from Maven Central
├── topics.dev.tsv                # raw msmarco-v1-passage.dev topics (from Anserini)
├── queries.json                  # flattened list of dev query strings
├── frontend/                     # Next.js app
│   ├── data/msmarco-dev-queries.json   # copied from ../queries.json
│   ├── pages/index.js
│   ├── pages/api/search.js       # proxy → Anserini REST /v1/{index}/search
│   └── pages/api/sample-queries.js
└── rest.log                      # Anserini REST server log (when running)
```

## Prerequisites

- Java 21 (`java -version`)
- Node.js 18+ and npm
- `jq` (used during setup only)

## 1. Backend: Anserini REST API

The fatjar is already downloaded as `anserini-2.1.1-fatjar.jar`. Start the REST
server on port `8080` (override with `ANSERINI_PORT` if you like):

```bash
export ANSERINI_JAR="$(pwd)/anserini-2.1.1-fatjar.jar"
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "${ANSERINI_PORT:-8080}"
```

On first request against `msmarco-v1-passage`, Anserini will download the
prebuilt MS MARCO V1 passage index (~2 GB). After that it stays cached under
`~/.cache/pyserini/indexes` (or Anserini's equivalent local cache).

Verify the backend:

```bash
curl "http://localhost:8080/v1/msmarco-v1-passage/search?query=what%20is%20a%20lobster%20roll&hits=3" | jq '.candidates[0]'
```

You should see a JSON object with `docid`, `score`, `rank`, and `doc` fields.

## 2. Frontend: Next.js

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

### Environment variables

All optional. Defaults match the PRD.

| Variable           | Default                  | Purpose                              |
| ------------------ | ------------------------ | ------------------------------------ |
| `ANSERINI_BASE_URL`| `http://localhost:8080`  | Anserini REST server URL             |
| `ANSERINI_INDEX`   | `msmarco-v1-passage`     | Prebuilt index to search             |
| `ANSERINI_HITS`    | `10`                     | Default hits per query               |
| `FRONTEND_PORT`    | `3000`                   | Next.js dev/start port               |

Example:

```bash
ANSERINI_BASE_URL=http://localhost:9999 FRONTEND_PORT=4000 npm run dev
```

## UX

- Page load shows the search bar plus 6 random sample queries pulled from the
  6,980 MS MARCO passage dev queries (`msmarco-v1-passage.dev` via
  `io.anserini.cli.TopicsRegistry`).
- Click a sample chip to run that query immediately. Click **shuffle** to
  re-sample.
- Empty queries, no-results states, and backend errors are all surfaced inline.

## How the queries were generated

```bash
java -cp "$ANSERINI_JAR" io.anserini.cli.TopicsRegistry \
  --get msmarco-v1-passage.dev > topics.dev.tsv
jq '[to_entries[] | .value.title]' topics.dev.tsv > queries.json
cp queries.json frontend/data/msmarco-dev-queries.json
```

`queries.json` is a JSON array of 6,980 dev query strings. The API route
`/api/sample-queries` and the page's `getServerSideProps` sample uniformly at
random from that array.

## REST API contract used

Documented in the repo-local `anserini-cli` skill:

```
GET /v1/{index}/search?query=...&hits=N
→ { api, index, query: { text }, candidates: [ { docid, score, rank, doc } ] }
```

The Next.js API route `/api/search` simply proxies this and surfaces backend
failures (non-2xx, connection refused) as JSON errors that the page renders.
