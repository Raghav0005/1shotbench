# MS MARCO Passage Search App

A Next.js frontend for searching the MS MARCO passage corpus via the Anserini REST API.

## Prerequisites

- Node.js 18+
- The Anserini REST server running on port 8080 (or the port specified by `BACKEND_PORT`)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3000` | Port the Next.js frontend listens on |
| `BACKEND_PORT` | `8080` | Port of the Anserini REST API backend |

## Development

```bash
npm install
npm run dev
```

The app will be available at http://localhost:3000.

## Production

```bash
npm run build
npm run start
```

## Features

- Full-text search against the MS MARCO passage corpus
- Random sample queries from the MS MARCO passage dev set displayed on load
- Click any sample query to execute it immediately
- Ranked results with docid, score, and passage text
- Clear feedback for empty queries, no-results states, and backend errors
