# Anserini Prebuilt Index Evaluator

Local browser application for browsing Anserini prebuilt Lucene inverted indexes and running real Anserini retrieval/evaluation commands.

## Setup

```bash
npm install
npm run setup:anserini
npm run smoke:anserini
```

`setup:anserini` downloads the latest Maven Central `anserini-*-fatjar.jar` into `.anserini/` unless `ANSERINI_VERSION` is set. The app also honors `ANSERINI_JAR` when it points to an existing fatjar.

## Run

```bash
npm start
```

Open http://localhost:3000. CACM is the default evaluable dataset. Other prebuilt inverted indexes are loaded from `io.anserini.cli.PrebuiltIndexRegistry --type inverted --list` and labeled catalog-only unless an automatic topics/qrels pairing is known.

## Test

```bash
npm test
```

The Playwright test launches the browser UI, selects CACM, runs Anserini `SearchCollection`, evaluates with `TrecEval`, verifies a numeric score, and checks that generated run/evaluation artifact files exist.
