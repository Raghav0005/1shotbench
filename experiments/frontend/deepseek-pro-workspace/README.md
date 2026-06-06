# MS MARCO Passage Search App

A local search application with a **Next.js frontend** and an **Anserini REST API backend** for searching the MS MARCO passage corpus.

## Architecture

```
┌─────────────────────┐        HTTP/REST         ┌─────────────────────┐
│   Next.js Frontend  │ ────────────────────────> │  Anserini REST API  │
│   (port 3000)       │ <──────────────────────── │  (port 8080)        │
│                     │   GET /v1/{index}/search  │                     │
│   Search Bar        │   GET /v1/{index}/doc/id  │  msmarco-v1-passage │
│   Sample Queries    │                           │  index              │
│   Results Display   │                           │                     │
└─────────────────────┘                           └─────────────────────┘
```

## Quick Start

### 1. Install Anserini Fatjar

```bash
bash scripts/install-anserini.sh
```

This downloads the latest Anserini fatjar from Maven Central, runs a smoke test
(CACM), verifies expected scores, and writes a `.env` file with `ANSERINI_JAR`.

### 2. Start the Backend

```bash
bash scripts/start-backend.sh
```

The REST server starts on port 8080 (configurable with `BACKEND_PORT`).
The MS MARCO v1 passage prebuilt index is downloaded on first query.

Test it:
```bash
curl "http://localhost:8080/v1/msmarco-v1-passage/search?query=what%20is%20anserini&hits=5"
```

### 3. Start the Frontend

In a new terminal:
```bash
bash scripts/start-frontend.sh
```

Open **http://localhost:3000** in your browser.

## Configuration

All settings are configurable via environment variables:

| Variable         | Default               | Description                          |
|-----------------|-----------------------|--------------------------------------|
| `FRONTEND_PORT` | `3000`                | Next.js dev server port              |
| `BACKEND_PORT`  | `8080`                | Anserini REST API port               |
| `BACKEND_HOST`  | `localhost`           | Anserini REST API host               |
| `ANSERINI_INDEX`| `msmarco-v1-passage`  | Anserini prebuilt index name         |

### Using .env.local

Copy the example and customize:
```bash
cp .env.local.example .env.local
# Edit values in .env.local
```

### Custom Backend Port

```bash
BACKEND_PORT=9090 bash scripts/start-backend.sh
```

Then on the frontend:
```bash
BACKEND_PORT=9090 bash scripts/start-frontend.sh
```

## REST API Routes

The Anserini REST server exposes (from `anserini-cli` skill docs):

| Method | Path                                | Description              |
|--------|-------------------------------------|--------------------------|
| GET    | `/v1/{index}/search?query={q}&hits={n}` | Search the index       |
| GET    | `/v1/{index}/doc/{docid}`           | Fetch document by docid  |

## Sample Queries

The frontend shows 5 randomly selected queries from the MS MARCO passage dev set
on each page load. Users can click a sample query to run it immediately.

The query list is stored in `src/lib/sampleQueries.ts`. To refresh it from the
real MS MARCO dev query set:

```bash
bash scripts/fetch-sample-queries.sh
```

Copy the output into `src/lib/sampleQueries.ts`, replacing the `SAMPLE_QUERIES`
array.

## Project Structure

```
.
├── .env.local.example          # Environment variable template
├── next.config.js              # Next.js config (env vars)
├── package.json                # Node dependencies
├── tsconfig.json               # TypeScript config
├── scripts/
│   ├── install-anserini.sh     # Download & verify Anserini fatjar
│   ├── start-backend.sh        # Start Anserini REST API server
│   ├── start-frontend.sh       # Start Next.js dev server
│   └── fetch-sample-queries.sh # Extract queries from TopicsRegistry
└── src/
    ├── app/
    │   ├── globals.css         # Global styles
    │   ├── layout.tsx          # Root layout + metadata
    │   └── page.tsx            # Main page (search + results)
    ├── components/
    │   ├── SearchBar.tsx       # Search input form
    │   ├── SampleQueries.tsx   # Clickable sample query chips
    │   ├── SearchResults.tsx   # Ranked results list
    │   └── ErrorMessage.tsx    # Error display with retry
    └── lib/
        ├── anserini.ts         # REST API client
        └── sampleQueries.ts    # Sample queries + random picker
```

## Prerequisites

- **Java 21** — required by Anserini
- **Node.js 18+** and **npm** — for the Next.js frontend

## Troubleshooting

### Backend not responding
Make sure the Anserini REST server is running. Check the terminal where you ran
`scripts/start-backend.sh`. The first query may take a moment while the
MS MARCO passage index is downloaded.

### Port already in use
Kill the process using the port:
```bash
lsof -ti:8080 | xargs kill
```
Or use a different port:
```bash
BACKEND_PORT=9090 bash scripts/start-backend.sh
BACKEND_PORT=9090 bash scripts/start-frontend.sh
```

### Cannot find ansersini fatjar
Re-run the install script:
```bash
bash scripts/install-anserini.sh
```

### Frontend build errors
Make sure dependencies are installed:
```bash
cd /path/to/this/directory
npm install
```
