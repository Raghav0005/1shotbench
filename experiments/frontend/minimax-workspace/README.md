# MS MARCO Passage Search

A local web application for searching the MS MARCO passage corpus through the
[Anserini](https://github.com/castorini/anserini) REST API. The frontend is a
Next.js app that displays randomly selected sample queries from the MS MARCO
passage dev set on each page load and lets users run them (or type their own
queries) to retrieve ranked passages.

## Requirements

- Java 21 on `PATH` (Anserini's runtime requirement)
- Node.js 18+ and `npm`
- The Anserini fatjar (`anserini-*-fatjar.jar`). One is included at the repo
  root as `anserini-2.1.1-fatjar.jar`; replace it with a different version by
  pointing `ANSERINI_JAR` at the new file.

## Quick start

```bash
# from the repo root
./start.sh
```

The script:

1. Starts the Anserini REST server on port `8080` (override with
   `ANSERINI_PORT=9000 ./start.sh`).
2. Installs the Next.js dependencies on first run.
3. Starts the Next.js dev server on port `3000` (override with
   `PORT=4000 ./start.sh`).
4. Wires the frontend to the backend through `ANSERINI_URL` so the API
   routes know where to forward search requests.
5. Cleans up the backend on `Ctrl+C`.

Once both services are up, open <http://localhost:3000> in a browser. The
page will display five randomly chosen sample queries from the MS MARCO
passage dev set. Click any sample (or type your own query) to see ranked
passages returned by Anserini.

## Configuration

| Variable          | Default                          | Purpose                                              |
| ----------------- | -------------------------------- | ---------------------------------------------------- |
| `ANSERINI_PORT`   | `8080`                           | Port the Anserini REST server listens on.            |
| `ANSERINI_URL`    | `http://localhost:${ANSERINI_PORT}` | Base URL the frontend uses to reach the backend.   |
| `ANSERINI_JAR`    | `anserini-2.1.1-fatjar.jar`      | Path to the Anserini fatjar.                         |
| `ANSERINI_INDEX`  | `msmarco-v1-passage`             | Prebuilt index the backend serves.                   |
| `PORT`            | `3000`                           | Port the Next.js dev server listens on.              |

The application does not prompt for ports; set the environment variables
above before invoking `./start.sh` if you need non-default values.

## End-to-end layout

```
start.sh ──▶ java -cp anserini-2.1.1-fatjar.jar io.anserini.api.RestServer --port $ANSERINI_PORT
        └─▶ (cd frontend && npx next dev --port $PORT)
                    │
                    └─▶ /api/samples?count=N ──▶ reads msmarco-v1-passage.dev.queries.tsv
                    └─▶ /api/search?query=…   ──▶ http://localhost:$ANSERINI_PORT/v1/msmarco-v1-passage/search
```

The frontend never calls the Anserini backend directly from the browser; it
goes through its own `/api/*` routes so the search results and any error
messages can be normalized before being shown to the user.

## File layout

```
.
├── PRD.md                                    # Product requirements
├── README.md                                 # This file
├── anserini-2.1.1-fatjar.jar                 # Anserini fatjar (Java 21)
├── msmarco-v1-passage.dev.queries.tsv        # MS MARCO passage dev queries
├── start.sh                                  # Launches backend + frontend
└── frontend/                                 # Next.js app
    ├── msmarco-v1-passage.dev.queries.tsv    # copy used by the /api/samples route
    ├── next.config.js
    ├── package.json
    ├── tsconfig.json
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx                      # Search UI
        │   ├── globals.css
        │   └── api/
        │       ├── search/route.ts           # Proxies /v1/.../search
        │       └── samples/route.ts          # Random sample queries
        └── lib/
            ├── anserini.ts                   # Backend URL/index resolution
            └── queries.ts                    # Dev-queries TSV loader
```

## Refreshing the dev queries

If you want to pull a different set of queries (for example, `msmarco-v1-passage.dev`
via the `TopicsRegistry`):

```bash
java -cp anserini-2.1.1-fatjar.jar \
  io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev \
  > msmarco-v1-passage.dev.json

jq -r 'to_entries[] | [.key, .value.title] | @tsv' \
  msmarco-v1-passage.dev.json > frontend/msmarco-v1-passage.dev.queries.tsv
```

The TSV must remain two columns: `qid<TAB>query text`.

## Troubleshooting

- **"Could not reach the Anserini REST backend"** — the Next.js frontend
  couldn't connect to whatever `ANSERINI_URL` points to. Verify the backend
  is running (`curl http://localhost:8080/v1/msmarco-v1-passage/search?query=test&hits=1`)
  and that `ANSERINI_URL` matches.
- **"Parameter 'query' is required"** — the query string was empty when
  reaching the Anserini backend. The frontend already guards against empty
  queries, so this usually means a custom integration is calling the
  backend directly.
- **No results for a real query** — some queries legitimately have no exact
  matches in the corpus. The UI shows a clear no-results state.
- **Port already in use** — pick a free port via the environment variables
  above (e.g. `ANSERINI_PORT=8081 PORT=3001 ./start.sh`).
