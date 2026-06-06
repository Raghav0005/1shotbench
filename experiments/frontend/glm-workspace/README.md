# MS MARCO Passage Search App

A locally-runnable web application that pairs a Next.js frontend with an Anserini REST API backend for searching the MS MARCO passage corpus.

## Architecture

- **Backend**: Anserini REST API server serving the `msmarco-v1-passage` prebuilt index (default port `8080`)
- **Frontend**: Next.js app (default port `3000`) with search input, clickable sample queries, and ranked passage results

## Prerequisites

- Java 21
- Node.js 18+ and npm
- Anserini fatjar (already included: `anserini-2.1.1-fatjar.jar`)

## Quick Start

### 1. Start the Backend

```bash
./start-backend.sh
```

The backend defaults to port `8080`. Override with:

```bash
BACKEND_PORT=9000 ./start-backend.sh
```

Wait for `Server started on port ...` in the logs.

### 2. Start the Frontend

In a separate terminal:

```bash
./start-frontend.sh
```

The frontend defaults to port `3000`. Override with:

```bash
FRONTEND_PORT=4000 ./start-frontend.sh
```

If using a custom backend port, also pass it so the proxy works:

```bash
BACKEND_PORT=9000 FRONTEND_PORT=4000 ./start-frontend.sh
```

### 3. Open the App

Navigate to [http://localhost:3000](http://localhost:3000) (or your custom port).

## Usage

- **Sample queries**: On page load, 10 random queries from the MS MARCO passage dev set are displayed. Click any to run a search.
- **Manual search**: Type a query and press Enter or click Search.
- **Results**: Ranked passages are displayed with doc ID, score, and passage text.
- **Error handling**: Clear messages are shown for empty queries, zero results, and backend connection issues.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BACKEND_PORT` | `8080` | Port for the Anserini REST API server |
| `FRONTEND_PORT` | `3000` | Port for the Next.js dev server |
| `ANSERINI_JAR` | auto-detected | Path to the Anserini fatjar |

## Project Structure

```
├── anserini-2.1.1-fatjar.jar   # Anserini fatjar
├── start-backend.sh             # Start the REST API server
├── start-frontend.sh            # Start the Next.js dev server
├── frontend/
│   ├── next.config.ts           # Next.js config with API proxy rewrite
│   └── src/app/
│       ├── layout.tsx           # Root layout
│       ├── page.tsx             # Main search page (client component)
│       ├── globals.css          # Global styles
│       └── sample_queries.json  # 6980 MS MARCO dev queries
└── README.md
```
