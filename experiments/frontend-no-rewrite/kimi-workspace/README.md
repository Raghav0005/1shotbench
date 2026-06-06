# MS MARCO Passage Search App

A local search application with a Next.js frontend and an Anserini REST API backend. Search the MS MARCO passage corpus and explore randomly selected sample queries from the MS MARCO passage dev query set.

## Prerequisites

- Java 21
- Node.js (v20+) and npm

## Project Structure

```
.
├── anserini-2.1.1-fatjar.jar   # Anserini fatjar (auto-downloaded during setup)
├── start-backend.sh            # Script to start the Anserini REST server
├── frontend/                   # Next.js frontend application
│   ├── src/app/page.tsx        # Main search page
│   ├── src/app/api/search/     # Next.js API route (proxies to Anserini)
│   └── public/queries.json     # MS MARCO passage dev queries
└── README.md
```

## Quick Start

### 1. Start the Backend

The backend uses the Anserini REST API server. It defaults to port `8080`.

```bash
./start-backend.sh
```

To use a different port:

```bash
BACKEND_PORT=8081 ./start-backend.sh
```

### 2. Start the Frontend

In a new terminal:

```bash
cd frontend
npm install   # if not already installed
npm run dev
```

The frontend defaults to port `3000`. To use a different port:

```bash
PORT=3001 npm run dev
```

If you changed the backend port, update `frontend/.env.local`:

```
API_URL=http://localhost:8081
```

Then restart the frontend dev server.

### 3. Open the App

Navigate to [http://localhost:3000](http://localhost:3000).

## Features

- **Search**: Type a query and press Enter or click the Search button.
- **Sample Queries**: On each page load, several random sample queries from the MS MARCO passage dev set are displayed. Click any sample query to run it.
- **Ranked Results**: Results show rank, document ID, BM25 score, and passage text.
- **Error Handling**: Empty queries, backend errors, and no-results states are handled with clear messages.

## API

The frontend proxies search requests to the Anserini REST server via a Next.js API route:

```
GET /api/search?query=<text>&hits=<number>
```

The Anserini REST server is available directly at:

```
GET http://localhost:8080/v1/msmarco-v1-passage/search?query=<text>&hits=<number>
GET http://localhost:8080/v1/msmarco-v1-passage/doc/<docid>
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3000` | Frontend Next.js dev server port |
| `BACKEND_PORT` | `8080` | Anserini REST server port |
| `API_URL` | `http://localhost:8080` | Backend URL used by the frontend API route |
| `ANSERINI_JAR` | `anserini-2.1.1-fatjar.jar` | Path to the Anserini fatjar |

## How It Was Built

1. Downloaded the Anserini fatjar from Maven Central (`install-anserini-fatjar` skill).
2. Verified the fatjar with the CACM smoke test.
3. Started `io.anserini.api.RestServer` on port 8080.
4. Exported MS MARCO passage dev queries via `io.anserini.cli.TopicsRegistry` and saved them to `frontend/public/queries.json`.
5. Built a Next.js app with a search UI, sample query chips, and ranked result cards.
6. Added a Next.js API route to proxy search requests and avoid CORS issues.
