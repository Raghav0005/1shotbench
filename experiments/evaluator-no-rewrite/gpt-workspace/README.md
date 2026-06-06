# Anserini Prebuilt Index Evaluator

Local browser app for registry-derived Anserini prebuilt Lucene inverted indexes and a real CACM retrieval/evaluation workflow.

## Setup

```bash
npm install
npm run anserini:setup   # downloads the latest Maven Central Anserini fatjar if tools/ is empty
npm run anserini:smoke   # optional CACM SearchCollection + TrecEval verification
```

You can also set `ANSERINI_JAR=/path/to/anserini-*-fatjar.jar`.

## Run

```bash
npm start
```

Open <http://localhost:3000>. The catalog comes from:

```bash
java -cp "$ANSERINI_JAR" io.anserini.cli.PrebuiltIndexRegistry --list --type inverted
java -cp "$ANSERINI_JAR" io.anserini.cli.TopicsRegistry --list
```

CACM is the default evaluable pairing (`index=cacm`, `topics=cacm`, `qrels=cacm`) and runs:

```bash
java -cp "$ANSERINI_JAR" io.anserini.search.SearchCollection -threads 1 -index cacm -topics cacm -output <run> -hits 1000 -bm25
java -cp "$ANSERINI_JAR" io.anserini.eval.TrecEval -c -m <metric> cacm <run>
```

Artifacts are written under `runs/evaluations/`.

## Test

```bash
npm run test:e2e
```
