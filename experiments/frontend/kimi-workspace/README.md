# MS MARCO Passage Search App

A local search application with a Next.js frontend and an Anserini REST API backend. Search over the MS MARCO passage corpus and explore sample queries from the dev query set.

## Architecture

- **Backend**: Anserini REST API (port 8080)
- **Frontend**: Next.js 16 with TypeScript and Tailwind CSS (port 3000)

## Prerequisites

- Java 21
- Node.js 18+
- The MS MARCO passage prebuilt index will be downloaded automatically on first search

## Quick Start

### 1. Start the Anserini REST API Server

```bash
export ANSERINI_JAR="anserini-2.1.1-fatjar.jar"
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```

The server will start on port 8080 by default. The first search may take a moment as the MS MARCO passage index is downloaded (~2.5GB).

### 2. Start the Next.js Frontend

```bash
cd my-app
npm run dev
```

The frontend will start on port 3000 (or the next available port if 3000 is in use).

### 3. Open the App

Navigate to `http://localhost:3000` (or the port shown in the terminal).

## Environment Variables

Create a `.env.local` file in the `my-app` directory to customize:

```env
# Backend API URL (default: http://localhost:8080)
NEXT_PUBLIC_BACKEND_URL=http://localhost:8080
```

To use a different backend port:

```bash
# Terminal 1: Start Anserini on a custom port
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8081

# Terminal 2: Start frontend with custom backend URL
cd my-app
NEXT_PUBLIC_BACKEND_URL=http://localhost:8081 npm run dev
```

To use a different frontend port:

```bash
cd my-app
npm run dev -- --port 3001
```

## Features

- **Search**: Enter any query to search the MS MARCO passage corpus
- **Sample Queries**: Click on any of the 8 randomly selected sample queries from the MS MARCO dev set
- **Ranked Results**: View passages ranked by relevance with scores and document IDs
- **Error Handling**: Clear messages for empty queries, no results, and backend errors

## API Endpoints

The Anserini REST API provides:

- `GET /v1/msmarco-v1-passage/search?query={query}&hits={n}` - Search passages
- `GET /v1/msmarco-v1-passage/doc/{docid}` - Get a specific document

## Sample Queries

The app includes 6,980 sample queries from the MS MARCO passage dev set. On each page load, 8 random queries are displayed for users to try.

## Troubleshooting

### Backend connection errors

Ensure the Anserini REST server is running on the correct port:

```bash
curl http://localhost:8080/v1/msmarco-v1-passage/search?query=test&hits=1
```

### Port already in use

If port 3000 is in use, Next.js will automatically use the next available port. Check the terminal output for the actual URL.

### First search is slow

The MS MARCO passage index (~2.5GB) is downloaded on the first search query. Subsequent searches will be fast.

## Files

- `anserini-2.1.1-fatjar.jar` - Anserini fatjar
- `my-app/` - Next.js frontend application
- `msmarco_sample_queries.txt` - Sample queries from MS MARCO dev set
