# MS MARCO Passage Search App

A locally-runnable search app over the MS MARCO passage corpus, built with a
Next.js frontend talking to the Anserini REST API server.

The page shows a search box plus a fresh set of randomly chosen sample queries
drawn from the MS MARCO passage **dev** set on every page load. Clicking a
sample runs that query against the backend and renders the ranked passages.

## Layout

```
.
├── anserini-2.1.1-fatjar.jar       # Anserini fatjar (downloaded by install step)
├── frontend/                       # Next.js app
│   ├── app/                        # App Router pages + API routes
│   │   ├── api/sample-queries/     # GET random dev-set queries
│   │   ├── api/search/             # GET search results from Anserini
│   │   ├── page.tsx                # Home page (server component)
│   │   └── SearchClient.tsx        # Client UI (form, samples, results)
│   ├── data/msmarco-passage-dev-queries.json  # Dev queries (id, text)
│   ├── lib/                        # config, anserini client, sample loader
│   └── scripts/fetch-dev-queries.sh
├── scripts/start-backend.sh        # Convenience launcher for RestServer
├── topics.dev.raw.txt              # Raw TopicsRegistry JSON (regeneratable)
└── PRD.md
```

## Prerequisites

- Java 21 (`java -version` should report 21.x)
- Node.js 18+ and npm
- `jq` (used when regenerating the dev-queries file)

## 1. Install the Anserini fatjar

Already done in this checkout. The jar is at
`./anserini-2.1.1-fatjar.jar`. To install fresh:

```bash
ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
  | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
export ANSERINI_JAR="$(pwd)/anserini-${ANSERINI_VERSION}-fatjar.jar"
```

A successful CACM smoke test (per the `install-anserini-fatjar` skill)
reports `map all 0.3123` / `P_30 all 0.1942`.

## 2. Start the Anserini REST backend (port 8080 by default)

```bash
export ANSERINI_JAR="$(pwd)/anserini-2.1.1-fatjar.jar"
./scripts/start-backend.sh           # uses PORT or BACKEND_PORT, default 8080
```

or, directly:

```bash
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```

The first MS MARCO passage query will download the `msmarco-v1-passage`
prebuilt index (~2.5 GB). Subsequent queries are fast.

Verify:

```bash
curl "http://localhost:8080/v1/msmarco-v1-passage/search?query=what%20is%20a%20lobster%20roll&hits=3" | jq '.candidates[0]'
```

## 3. Run the Next.js frontend (port 3000 by default)

```bash
cd frontend
npm install
npm run dev                          # respects PORT, defaults to 3000
```

Open <http://localhost:3000>.

### Configuration

All settings are read from environment variables, with PRD defaults baked in.
Copy `frontend/.env.local.example` to `frontend/.env.local` to override:

| Variable               | Default                                          | Purpose                                          |
| ---------------------- | ------------------------------------------------ | ------------------------------------------------ |
| `PORT`                 | `3000`                                           | Frontend port (`next dev` / `next start`).       |
| `ANSERINI_BASE_URL`    | `http://localhost:8080`                          | Backend Anserini REST URL (server-side only).    |
| `ANSERINI_INDEX`       | `msmarco-v1-passage`                             | Prebuilt index queried by the backend.           |
| `SAMPLE_QUERIES_PATH`  | `frontend/data/msmarco-passage-dev-queries.json` | JSON `[{id,text}]` of dev queries.               |
| `SAMPLE_QUERIES_COUNT` | `6`                                              | Number of sample queries surfaced per load.      |
| `SEARCH_HITS`          | `10`                                             | Default `hits` per search.                       |

For the backend launcher, `BACKEND_PORT` (or `PORT`) controls the
`RestServer` port.

## Regenerating the sample-queries file

The dev queries are extracted from Anserini's `TopicsRegistry`:

```bash
export ANSERINI_JAR="$(pwd)/anserini-2.1.1-fatjar.jar"
./frontend/scripts/fetch-dev-queries.sh
```

This writes `frontend/data/msmarco-passage-dev-queries.json` (≈6,980 queries).

## How it works

- `frontend/app/page.tsx` is a server component that picks `SAMPLE_QUERIES_COUNT`
  random queries from `SAMPLE_QUERIES_PATH` and passes them to the client
  component. Because the route is `force-dynamic`, the page produces a fresh
  random sample on every load.
- `frontend/app/SearchClient.tsx` renders the search box and sample-query
  chips. Submitting the form or clicking a sample calls
  `GET /api/search?q=…`.
- `frontend/app/api/search/route.ts` forwards the query to
  `${ANSERINI_BASE_URL}/v1/${ANSERINI_INDEX}/search?query=…&hits=…`, the
  endpoint documented in the `anserini-cli` skill, and projects the
  `{ candidates: [{docid, score, rank, doc}] }` response into the row shape
  used by the UI.
- `frontend/app/api/sample-queries/route.ts` returns a fresh random sample
  on demand (used by the client as a recovery path if the server-side load
  fails).

## Error handling

- **Empty query** — the client rejects empty input before calling the API;
  the API also returns HTTP 400 if it ever receives one.
- **No results** — the UI shows a "No results found" notice.
- **Backend down / non-2xx** — the API route surfaces a clear error
  (HTTP 502/503) and the UI shows it in a red status banner.
- **Missing sample-queries file** — the page renders a banner explaining
  how to regenerate it with `scripts/fetch-dev-queries.sh`.
