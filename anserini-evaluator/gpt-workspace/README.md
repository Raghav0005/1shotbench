# Anserini Prebuilt Index Evaluator

Local Express + browser UI for browsing Anserini's prebuilt Lucene inverted-index registry and running a real CACM evaluation through the Anserini fatjar CLI.

## Run

```bash
export ANSERINI_JAR="$PWD/anserini-2.1.1-fatjar.jar" # or another anserini-*-fatjar.jar
npm start
```

Open <http://localhost:3000>.

## Test

```bash
npm run test:e2e
```

The Playwright test starts the app, verifies the registry-derived catalog exposes more than CACM, runs `SearchCollection` and `TrecEval` for CACM, and checks generated run/evaluation artifact files.
