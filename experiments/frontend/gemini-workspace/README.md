# MS MARCO Passage Search Application

A local web-based search application utilizing a Next.js frontend integrated with an Anserini REST API backend, enabling searches across the MS MARCO passage corpus.

## Prerequisites
- Java 21+
- Node.js 18+
- Anserini fatjar (downloaded using `install-anserini-fatjar` skill)

## Backend (Anserini REST API)

By default, the backend runs on port 8080 and uses the MS MARCO passage corpus.

To start the backend, run the following command from the same directory where your Anserini fatjar is located:
```bash
# Ensure ANSERINI_JAR is set to your downloaded fatjar, e.g.:
# export ANSERINI_JAR="anserini-2.1.1-fatjar.jar"
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port 8080
```
*Note: You can change the port by replacing `--port 8080` with `--port <YOUR_PORT>`.*

## Frontend (Next.js)

The frontend connects to the backend and serves the UI on port 3000 by default.

To start the frontend:
```bash
# Install dependencies (only needed once)
npm install

# Start the frontend development server
npm run dev
```

### Configuration
You can configure both frontend and backend ports using environment variables.

If you changed the backend port, start the frontend with the `BACKEND_PORT` variable set:
```bash
BACKEND_PORT=8081 npm run dev
```

To change the frontend port itself, use the standard Next.js `PORT` environment variable:
```bash
PORT=3001 npm run dev
```

## Features
- **Sample Queries**: On page load, 5 random sample queries from the MS MARCO passage dev query set are displayed. Clicking on any will immediately execute the search.
- **Search Functionality**: Manually input any query and submit to see ranked MS MARCO passage results.
- **Graceful Error Handling**: Appropriate messages are displayed if there's no result, an empty search, or an unreachable backend.