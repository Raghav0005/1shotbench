# MS MARCO Passage Search App

A local Next.js frontend for the Anserini REST API server over the `msmarco-v1-passage` prebuilt index. The app shows random MS MARCO passage dev queries on page load, lets users click one, and displays ranked passage results.

## Anserini setup

The Anserini fatjar was installed from Maven Central as `anserini-2.1.1-fatjar.jar` and smoke-tested with CACM. The smoke test produced MAP `0.3123` and P@30 `0.1942`.

To verify the jar is present and the MS MARCO passage index is registered:

```bash
npm run check:anserini
```

## Run locally

```bash
npm install
npm run dev
```

Defaults:

- Backend: `http://localhost:8080`
- Frontend: `http://localhost:3000`
- Anserini index: `msmarco-v1-passage`

The first MS MARCO search may trigger Anserini/Pyserini to download the prebuilt `msmarco-v1-passage` index into the local cache.

## Configuration

Copy `.env.example` to `.env.local` and adjust values as needed:

```bash
cp .env.example .env.local
```

Supported environment variables:

- `ANSERINI_JAR` — path to the fatjar, default `./anserini-2.1.1-fatjar.jar`
- `ANSERINI_BACKEND_PORT` — backend port, default `8080`
- `ANSERINI_BACKEND_URL` — full backend URL override, default `http://localhost:$ANSERINI_BACKEND_PORT`
- `FRONTEND_PORT` — frontend port, default `3000`
- `ANSERINI_INDEX` — Anserini REST index, default `msmarco-v1-passage`

You can also run the processes separately:

```bash
npm run backend
npm run dev:frontend
```

## REST API contract used

Per the repo-local Anserini CLI skill and a local REST check, the frontend proxies search requests to:

```text
GET /v1/msmarco-v1-passage/search?query=<query>&hits=<n>
```

The Anserini response includes `candidates`, each with `docid`, `score`, `rank`, and `doc`. The Next.js API normalizes those candidates before sending them to the browser.
