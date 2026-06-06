# MS MARCO Passage Search Application

A local search tool combining a Next.js web interface with an Anserini REST API backend for searching the MS MARCO passage collection.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Next.js       │     │   Anserini      │
│   Frontend      │────▶│   REST Server   │
│   (Port 3000)   │     │   (Port 8080)   │
└─────────────────┘     └─────────────────┘
```

## Quick Start

### Prerequisites

- Java 21 (required for Anserini)
- Node.js 18+ (required for Next.js)
- npm

### Option 1: Using the startup script

```bash
# Make the script executable (if not already)
chmod +x start.sh

# Run the startup script
./start.sh
```

This will:
1. Start the Anserini REST API server on port 8080
2. Start the Next.js frontend on port 3000
3. Display the URLs for both services
4. Handle graceful shutdown with Ctrl+C

### Option 2: Manual startup

#### 1. Install Anserini Fatjar

```bash
# Download the Anserini fatjar
ANSERINI_VERSION="2.1.1"
curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

# Set the environment variable
export ANSERINI_JAR="anserini-${ANSERINI_VERSION}-fatjar.jar"
```

#### 2. Start Anserini REST Server

```bash
# Start the REST server (default port 8080)
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```

#### 3. Start Next.js Frontend

```bash
cd search-app

# Install dependencies (first time only)
npm install

# Start the development server
npm run dev
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANSERINI_PORT` | 8080 | Port for the Anserini REST server |
| `FRONTEND_PORT` | 3000 | Port for the Next.js frontend |
| `ANSERINI_JAR` | `anserini-2.1.1-fatjar.jar` | Path to the Anserini fatjar |

### Example with custom ports

```bash
# Terminal 1: Start Anserini on port 8081
ANSERINI_PORT=8081 java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8081

# Terminal 2: Start Next.js on port 3001
cd search-app
FRONTEND_PORT=3001 PORT=3001 npm run dev
```

Then update `search-app/.env` to match:
```
ANSERINI_PORT=8081
```

## Usage

1. Open your browser and navigate to `http://localhost:3000`
2. You'll see a search input field and sample queries
3. Click on a sample query or type your own
4. View the ranked passage results

## API Endpoints

### Frontend API (Next.js)

- `GET /api/search?query=<query>&hits=<n>` - Search for passages

### Backend API (Anserini)

- `GET /v1/msmarco-v1-passage/search?query=<query>&hits=<n>` - Search passages
- `GET /v1/msmarco-v1-passage/doc/<docid>` - Get document by ID

## Project Structure

```
.
├── anserini-2.1.1-fatjar.jar    # Anserini fatjar (downloaded)
├── start.sh                      # Startup script
├── README.md                     # This file
└── search-app/                   # Next.js application
    ├── src/
    │   ├── app/
    │   │   ├── api/search/       # API route for search
    │   │   ├── layout.tsx        # Root layout
    │   │   └── page.tsx          # Main search page
    │   └── data/
    │       └── sample-queries.json  # Sample MS MARCO queries
    ├── .env                      # Environment variables
    └── package.json              # Node.js dependencies
```

## Troubleshooting

### Anserini server won't start

- Ensure Java 21 is installed: `java -version`
- Check if port 8080 is already in use: `lsof -i :8080`
- Verify the fatjar exists and is not corrupted

### Frontend can't connect to backend

- Ensure Anserini is running: `curl http://localhost:8080/`
- Check the `ANSERINI_PORT` in `search-app/.env`
- Look for CORS or network issues in browser console

### No results returned

- The MS MARCO passage index may need to be downloaded (first use)
- Check Anserini logs for errors
- Try a simpler query

## License

This project is for local development and research purposes.
