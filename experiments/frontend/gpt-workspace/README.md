# MS MARCO Passage Search App

A local Next.js frontend for searching the MS MARCO passage corpus through the Anserini REST API server.

## What is included

- Next.js app on frontend port `3000` by default.
- API proxy at `/api/search` that calls Anserini REST.
- Anserini REST backend script on port `8080` by default.
- Random clickable samples from the MS MARCO passage dev query set.
- Ranked result display with clear empty-query, no-results, and backend-error states.

## Anserini setup status

The repo-local `install-anserini-fatjar` workflow was used. Java 21 is available, Anserini `2.1.1` was downloaded as `anserini-2.1.1-fatjar.jar`, and the CACM smoke test produced the expected scores:

```text
map  all  0.3123
P_30 all  0.1942
```

## Run locally

Install frontend dependencies:

```bash
npm install
```

Start Anserini REST in one terminal:

```bash
export ANSERINI_JAR="$PWD/anserini-2.1.1-fatjar.jar"
npm run backend
```

Start Next.js in another terminal:

```bash
npm run dev
```

Open http://localhost:3000.

> The first search against `msmarco-v1-passage` can download the Anserini prebuilt MS MARCO passage index, which is about 2.1 GB.

## Configuration

Defaults are set for local demos, and can be overridden with environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FRONTEND_PORT` | `3000` | Next.js dev/start port |
| `ANSERINI_PORT` | `8080` | REST backend port |
| `ANSERINI_BIND_HOST` | `0.0.0.0` | REST backend bind host |
| `ANSERINI_HOST` | `localhost` | Host used by the Next.js API proxy |
| `ANSERINI_API_URL` | unset | Full backend base URL; overrides host/port |
| `ANSERINI_INDEX` | `msmarco-v1-passage` | Anserini index searched by the app |
| `ANSERINI_JAR` | auto-detected jar in repo root | Path to the Anserini fatjar |

## Backend endpoint used

The app calls the documented Anserini REST route:

```text
GET /v1/msmarco-v1-passage/search?query=<query>&hits=10
```

The observed response contains `candidates`, each with `docid`, `rank`, `score`, and `doc` fields.
