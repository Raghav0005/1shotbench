# MS MARCO Passage Search

A simple search application for exploring MS MARCO passage retrieval through Anserini.

## Requirements
- Node.js 18+
- Java 21+

## Running the Backend

Download the Anserini fatjar and run the REST server on port 8080:

```bash
# Download the Anserini fatjar
ANSERINI_VERSION="2.1.1"
curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

# Run the backend
java -cp "anserini-${ANSERINI_VERSION}-fatjar.jar" io.anserini.api.RestServer --port 8080
```
Note: To use a different port, change `--port 8080` and pass `BACKEND_PORT` to the frontend.

## Running the Frontend

Install dependencies and start the Next.js frontend:

```bash
cd msmarco-app
npm install

# Run in development mode (starts on port 3000)
npm run dev
```

To configure ports via environment variables:

```bash
PORT=3001 BACKEND_PORT=8081 npm run dev
```

## Features
- Search over the MS MARCO passage corpus using the Anserini REST backend (`msmarco-v1-passage`).
- View ranked passage candidates and their document IDs.
- Random sample queries from the `msmarco-v1-passage-dev` topic set provided for immediate testing.
