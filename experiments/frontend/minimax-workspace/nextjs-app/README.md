# MS MARCO Passage Search App

A local search application with a Next.js frontend and an Anserini REST API backend for searching the MS MARCO passage corpus.

## Features

- **Anserini REST API Backend** - Powered by the Anserini search library
- **Next.js Frontend** - Modern web interface for submitting queries and viewing results
- **Sample Queries** - Randomly selected queries from the MS MARCO passage dev set on page load
- **Clickable Samples** - Click any sample query to run the search instantly
- **Ranked Results** - Display passage results with relevance scores
- **Error Handling** - Clear handling of empty queries, no-results, and backend errors

## Prerequisites

- **Java 21** - Required to run the Anserini REST API server
- **Node.js 18+** - Required for the Next.js frontend

## Quick Start

### 1. Start the Backend (Anserini REST API Server)

```bash
# Set the port (optional, defaults to 8080)
export BACKEND_PORT=8080

# Start the server
./start-backend.sh
```

The server will automatically download the MS MARCO passage index on first use.

### 2. Start the Frontend (Next.js)

In a new terminal:

```bash
# Navigate to the app directory
cd nextjs-app

# Install dependencies (if not already done)
npm install

# Start the development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

### 3. Search!

Open `http://localhost:3000` in your browser. You should see:

1. A search input box
2. Several randomly selected sample queries from the MS MARCO dev set
3. Type a query or click a sample query to search
4. View ranked passage results with relevance scores

## Configuration

### Environment Variables

#### Backend
| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_PORT` | `8080` | Port for the REST API server |
| `ANSERINI_VERSION` | `2.1.1` | Anserini version to use |
| `ANSERINI_JAR` | `./anserini-{version}-fatjar.jar` | Path to the Anserini fatjar |

#### Frontend
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8080` | Backend API URL |

### Example Custom Configuration

```bash
# Custom backend port
export BACKEND_PORT=9000

# Custom backend URL for frontend
export NEXT_PUBLIC_BACKEND_URL=http://localhost:9000
```

## API Endpoints

### Search
```
GET /v1/msmarco-v1-passage/search?query={query}&hits={num_hits}
```

Example:
```bash
curl "http://localhost:8080/v1/msmarco-v1-passage/search?query=what%20is%20a%20lobster%20roll&hits=10"
```

### Get Document
```
GET /v1/msmarco-v1-passage/doc/{docid}
```

Example:
```bash
curl "http://localhost:8080/v1/msmarco-v1-passage/doc/2161721"
```

## Architecture

```
┌─────────────────┐         ┌─────────────────────┐
│   Next.js UI    │────────▶│  Anserini REST API  │
│  (Port 3000)    │  HTTP   │    (Port 8080)      │
└─────────────────┘         └─────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────┐
                              │  MS MARCO Passage   │
                              │     Prebuilt        │
                              │      Index          │
                              └─────────────────────┘
```

## Troubleshooting

### "Port already in use" error
Choose a different port:
```bash
export BACKEND_PORT=8081
./start-backend.sh
```

### Index download issues
The first search will download the MS MARCO passage index (~500MB). Ensure stable internet connection.

### Java version error
Ensure Java 21 is installed:
```bash
java -version
```

## Project Structure

```
nextjs-app/
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   └── sample-queries/
│   │   │       └── route.ts      # API endpoint for sample queries
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx             # Main search interface
│   └── lib/
│       ├── sampleQueries.ts    # Sample queries utilities
│       └── types.ts            # TypeScript type definitions
├── start-backend.sh            # Script to start the REST API server
├── .env.local                  # Environment variables (create this)
└── package.json
```

## License

This project uses the MS MARCO passage corpus and Anserini library under their respective licenses.