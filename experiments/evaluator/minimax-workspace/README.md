# Anserini Prebuilt Index Evaluator

A local web application that surfaces Anserini's prebuilt Lucene inverted
indexes and drives reproducible retrieval evaluations against them through
the Anserini fatjar CLI.

## What it does

- **Catalog**: lists the prebuilt Lucene inverted indexes published by
  Anserini. The list is read live from
  `io.anserini.cli.PrebuiltIndexRegistry --type inverted --list` at
  startup. Indexes with no discovered topics/qrels pairing are kept in
  the catalog and marked as catalog-only.
- **Pairing**: for each evaluable index, the UI shows the topics and
  qrels that the bundled reproduction configs in
  `reproduce/from-prebuilt-indexes/configs/*.yaml` map it to. CACM is
  the default.
- **Metric selector**: lets the user pick `nDCG@10`, `Recall@1000`,
  `MAP`, `P.30`, etc. The user-friendly labels are translated to the
  exact arguments `io.anserini.eval.TrecEval` expects
  (e.g. `nDCG@10` → `-c -m ndcg_cut.10`).
- **Run Evaluation**: runs `io.anserini.search.SearchCollection` for
  the selected (index, topics) pairing, writes a TREC-format run file,
  then runs `io.anserini.eval.TrecEval` and reports the resulting
  score, run metadata, and a preview of the run/eval artifacts.
- **End-to-end test**: a Playwright browser test that drives the
  workflow in a real Chromium instance and verifies the score, the
  run file, the eval file, and the surrounding catalog.

The application is **not** a custom retrieval engine. It does not use
the Anserini REST API. It does not hardcode catalog data or scores; it
reads everything from the fatjar and the on-disk run/eval artifacts.

## Setup

Prerequisites (verified by the smoke test from the
`install-anserini-fatjar` skill):

- Java 21 on `PATH`
- Python 3.9+ with `flask`, `pyyaml`
- The Playwright Python bindings (and a Chromium browser)

Install the Anserini fatjar (if not already present in the workspace):

```bash
# The script inside e2e/run_e2e.sh does this automatically.
ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
  | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
```

Smoke-test the jar with the canonical CACM command (also from
`install-anserini-fatjar`):

```bash
export ANSERINI_JAR="$PWD/anserini-${ANSERINI_VERSION}-fatjar.jar"

java -cp "$ANSERINI_JAR" io.anserini.search.SearchCollection \
  -threads 1 -index cacm -topics cacm \
  -output run.cacm.bm25.txt -hits 1000 -bm25

java -cp "$ANSERINI_JAR" io.anserini.eval.TrecEval \
  -c -m map -m P.30 cacm run.cacm.bm25.txt
# Expect: map = 0.3123, P_30 = 0.1942
```

## Running the app

```bash
# from the workspace root
PORT=5555 python3 app/server.py
# then open http://127.0.0.1:5555/
```

## Running the tests

### Unit tests (no Java / no Anserini jar required)

```bash
python3 app/test_server.py
```

### End-to-end test (Playwright)

```bash
./e2e/run_e2e.sh
```

The script:
1. starts the backend on port 5555 (installing the Anserini fatjar
   from Maven Central if it is not already present),
2. runs the Playwright browser test that opens the app, runs a CACM
   BM25 retrieval, and verifies the score, run metadata, and
   artifacts,
3. stops the backend on exit.

Screenshots are written to `e2e/screenshots/`.

## Layout

```
app/
  server.py            Flask backend (CLI wrapper, JSON API)
  templates/
    index.html         UI markup
  static/
    app.css            styling
    app.js             UI logic (catalog, evaluation, result rendering)
  test_server.py       unit tests for metric translation logic
  data/                cache for derived data
runs/                  generated TREC run files
evals/                 generated trec_eval output files
e2e/
  test_app.py          Playwright end-to-end test
  run_e2e.sh           launcher (start server, run test, stop server)
  screenshots/         output from the e2e run
```

## API

- `GET /` — the UI
- `GET /api/health` — health/version/index counts
- `GET /api/catalog` — prebuilt inverted indexes + pairing info
- `GET /api/topics` — full topics registry list
- `GET /api/pairings` — extracted (index, topic_key, eval_key, metrics)
- `GET /api/metrics?index=…&topic_key=…` — metric options for a
  pairing
- `POST /api/evaluate` — body `{index, topic_key, metric}` → runs
  retrieval + evaluation, returns the score, the run/eval file
  paths, and previews
- `GET /api/artifact?path=…` — serve a generated run/eval file from
  the `runs/` or `evals/` directory (path-validated)
