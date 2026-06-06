# Anserini Prebuilt Index Evaluator

A small local web app that lets you browse Anserini's prebuilt Lucene
inverted-index catalog and execute real BM25 retrieval + `trec_eval`
evaluations from the browser. All catalog, retrieval, and evaluation data is
produced by the **Anserini fatjar CLI** (no mocks, no REST API).

## Prerequisites

- Java 21 on `PATH` (matches Anserini's current runtime requirement).
- Node.js 18+.
- The Anserini fatjar. The simplest way is to follow the repo-local
  `install-anserini-fatjar` skill:

  ```bash
  ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
    | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
  curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
    "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
  export ANSERINI_JAR="$PWD/anserini-${ANSERINI_VERSION}-fatjar.jar"
  ```

  The server looks for `ANSERINI_JAR`, falling back to any
  `anserini-*-fatjar.jar` in the workspace root or this app directory.

## Install + run

```bash
cd app
npm install
npm start
# open http://localhost:5173
```

On first launch the server invokes
`java -cp $ANSERINI_JAR io.anserini.cli.PrebuiltIndexRegistry --type inverted --list`
and
`java -cp $ANSERINI_JAR io.anserini.cli.TopicsRegistry --list`
to build the catalog. CACM is the default selection and runs end-to-end with
no further configuration.

## What's "evaluable"?

An index is marked **Evaluable** when this app can derive a compatible topic
set and qrels symbol from Anserini's registries using documented naming
conventions (e.g. `cacm` → `cacm`, `<collection>.flat` → `<collection>.test`,
`msmarco-v1-passage` → `msmarco-passage-dev-subset`, ...).
Indexes with no derivable pairing show up as **Catalog only** so users can
still browse them.

When you click **Run Evaluation** on an evaluable index, the server runs:

```bash
java -cp $ANSERINI_JAR io.anserini.search.SearchCollection \
  -threads 1 -index <index> -topics <topics> \
  -output runs/run.<index>.bm25.<ts>.txt -hits 1000 -bm25

java -cp $ANSERINI_JAR io.anserini.eval.TrecEval \
  -c -m <metric> <qrels> runs/run.<index>.bm25.<ts>.txt
```

and returns the parsed score plus paths to the run/eval artifacts.

## Metrics

The metric selector exposes user-facing labels mapped to exact `trec_eval`
identifiers:

| Label        | `trec_eval -m` arg | Result key       |
|--------------|--------------------|------------------|
| nDCG@10      | `ndcg_cut.10`      | `ndcg_cut_10`    |
| Recall@1000  | `recall.1000`      | `recall_1000`    |
| MAP          | `map`              | `map`            |
| P@30         | `P.30`             | `P_30`           |

## End-to-end test

```bash
cd app
npx playwright install chromium   # one-off
npm run test:e2e
```

The Playwright test:

- launches the server (which loads the live registry),
- confirms CACM is selected by default,
- asserts the catalog contains far more than a single hardcoded entry,
- asserts CACM exposes a topics/qrels pairing,
- selects `nDCG@10`,
- clicks **Run Evaluation**, waits for the real Anserini commands to finish,
- asserts a numeric score appears in the UI and that it matches Anserini's
  canonical CACM BM25 nDCG@10 of `~0.4543` (so a mocked or fabricated value
  would fail the test),
- asserts the run / eval artifact paths and a `trec_eval` preview are shown,
- asserts at least one **Catalog only** entry from the registry is visible.

## Project layout

```
app/
  server/
    index.js        Express server + /api/{catalog,health,evaluate}
    anserini.js     spawn() wrappers around the Anserini Java classes
    pairings.js     index -> topics/qrels inference
    metrics.js      user labels -> trec_eval -m identifiers
  public/           static HTML/CSS/JS frontend
  test/e2e.spec.js  Playwright end-to-end test
  runs/             generated TREC run files + eval previews (gitignored)
```
