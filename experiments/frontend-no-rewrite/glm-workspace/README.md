# MS MARCO Passage Search App

A local search application with a Next.js frontend and an Anserini REST API backend that searches over the MS MARCO passage corpus.

## Architecture

- **Backend**: Anserini REST API server serving the `msmarco-v1-passage` prebuilt index
- **Frontend**: Next.js app with search input, sample queries, and ranked passage results

## Quick Start

```bash
./start.sh
```

This starts both the backend (default port 8080) and frontend (default port 3000).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BACKEND_PORT` | `8080` | Anserini REST API port |
| `FRONTEND_PORT` | `3000` | Next.js dev server port |
| `ANSERINI_JAR` | auto-detected | Path to Anserini fatjar |

Example with custom ports:

```bash
BACKEND_PORT=9090 FRONTEND_PORT=4000 ./start.sh
```

## Features

- **Search**: Type a query and get ranked passage results from the MS MARCO passage corpus
- **Sample Queries**: Random sample queries from the MS MARCO passage dev set are shown on page load — click any to search
- **Result Display**: Each result shows rank, doc ID, score, and the full passage text
- **Error Handling**: Clear messages for empty queries, no-results states, and backend connection issues

## Requirements

- Java 21
- Node.js (for Next.js)
