# NFCorpus Live Retrieval Diagnostics Workbench

A small, single-container Node.js + Express web application that runs real Anserini retrieval and evaluation commands over the NFCorpus dataset. 

This application uses the official Anserini fatjar and `beir-v1.0.0-nfcorpus.flat` prebuilt index to verify reproduction metrics against expected scores.

## Deployment (Render)
This project is configured to be deployed as a Docker web service on Render or any Docker-compatible hosting platform. 
It satisfies the Render contract by:
- Binding HTTP to `0.0.0.0`
- Using the `$PORT` environment variable (defaults to `10000`).
- Including a `/health` endpoint for readiness probes.

### Docker Usage
```bash
docker build -t nfcorpus-diagnostics .
docker run -p 10000:10000 -e PORT=10000 nfcorpus-diagnostics
```

## Running Locally

1. Install dependencies:
```bash
npm install
```

2. The application expects the `anserini-*-fatjar.jar` in its directory or configured via `ANSERINI_JAR`. If not available, download it:
```bash
ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
wget "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" -O anserini-fatjar.jar
export ANSERINI_JAR="$(pwd)/anserini-fatjar.jar"
```

3. Start the server:
```bash
npm start
```

## Testing
Playwright E2E tests are included. To run them:
```bash
npm test
```
