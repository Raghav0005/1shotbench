# Anserini Prebuilt Index Evaluator

A local web app that browses Anserini's prebuilt Lucene inverted-index catalog
and runs reproducible BM25 retrieval + `trec_eval` evaluation entirely from the
browser. All retrieval and evaluation work is delegated to the published
Anserini fatjar (no mocking, no REST API).

## Requirements

- Java 21+ on `PATH` (Anserini's current runtime requirement)
- Node.js 18+
- `jq` is **not** required (the catalog is parsed in Node)
- ~110 MB of free disk for the Anserini fatjar plus a few MB per first-time
  prebuilt-index download

## Setup

Download the Anserini fatjar from Maven Central (this is the workflow defined
by the `install-anserini-fatjar` skill):

```bash
ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
  | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
mkdir -p anserini
curl -fL -o "anserini/anserini-${ANSERINI_VERSION}-fatjar.jar" \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
```

The app will auto-discover the jar at `./anserini/anserini-*-fatjar.jar`. You
can also point at any other location by exporting `ANSERINI_JAR=/path/to/jar`.

Install Node deps:

```bash
npm install
```

## Run

```bash
npm start                 # http://localhost:4317
PORT=9000 npm start       # custom port
```

The first catalog request triggers ~17 short JVM spawns (one
`PrebuiltIndexRegistry --list`, one `TopicsRegistry --list`, plus one
`ReproduceFromPrebuiltIndexes --show` per shipped reproduction config). After
that, the catalog is cached in memory until the server restarts.

CACM evaluates end-to-end in seconds. Other indexes (MS MARCO, BEIR, BRIGHT)
trigger a one-time prebuilt-index download into `~/.cache/pyserini/indexes/`.

## What the UI does

1. **Catalog (left).** Lists every prebuilt **inverted** Lucene index returned
   by `io.anserini.cli.PrebuiltIndexRegistry --type inverted --list`. Indexes
   that have a registered topics/qrels pairing are tagged **evaluable**;
   indexes that appear only in the registry are tagged **catalog-only** and
   are disabled for evaluation.
2. **Detail (middle).** For the selected index, shows registry metadata
   (description, document count, on-disk size) and the registered pairings
   pulled from the shipped `ReproduceFromPrebuiltIndexes` configs.
3. **Metrics.** The metric selector exposes every metric defined for the
   pairing in the reproduction config, plus the standard ranking metrics the
   PRD asks for: **nDCG@10** and **Recall@1000**. The mapping from user label
   to `trec_eval` args (`-c -m ndcg_cut.10`, `-c -m recall.1000`, …) is taken
   verbatim from Anserini's own configs.
4. **Run Evaluation.** Calls `io.anserini.search.SearchCollection` to produce a
   TREC-format run file, then `io.anserini.eval.TrecEval` to score it against
   the paired qrels. The UI shows the parsed score, the full evaluator output,
   a tail of the run file, both invoked commands, and links to the generated
   artifacts.

## Catalog pairing logic

The catalog augments the `PrebuiltIndexRegistry` listing with topics/qrels
pairings extracted from `ReproduceFromPrebuiltIndexes --show`. For each
condition we tokenize the YAML `command:` field, substitute `$topics` with
each declared `topic_key`, and treat the expanded `-index` value as the
prebuilt-index name that pairs with that topic + `eval_key`. This means CACM
appears as evaluable because the shipped `cacm` config pairs index `cacm` with
topics `cacm` and qrels `cacm`; BEIR indexes pair with `beir-*` topics and
`beir-v1.0.0-*.test` qrels via `beir.core`; and so on. Nothing is hardcoded.

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET    | `/api/health` | Checks for Java 21+ and the Anserini fatjar |
| GET    | `/api/catalog` | Returns the unified catalog (indexes + pairings) |
| POST   | `/api/catalog/refresh` | Forces a fresh catalog build |
| POST   | `/api/evaluate` | Runs retrieval + evaluation for one pairing |
| GET    | `/api/artifacts/:name` | Streams a generated run/eval file |

## End-to-end test

```bash
npx playwright install chromium      # one-time
npm run test:e2e
```

`tests/e2e.spec.js` boots the app, loads the live registry-derived catalog,
verifies CACM is selectable, picks `nDCG@10` (falling back to whatever metric
CACM exposes if nDCG@10 is missing), clicks Run Evaluation, and asserts a real
numeric score, real artifacts on disk, and that the displayed commands
reference `io.anserini.search.SearchCollection`, `io.anserini.eval.TrecEval`,
and the `anserini-*-fatjar.jar`.

## Files

```
anserini/anserini-*-fatjar.jar  # downloaded Maven Central fatjar
lib/anserini.js                 # thin wrapper around the Anserini CLI
lib/catalog.js                  # registry + reproduce-config pairing logic
server.js                       # Express API + static UI
public/                         # browser UI (vanilla HTML/CSS/JS)
artifacts/                      # generated TREC run + trec_eval outputs
tests/e2e.spec.js               # Playwright end-to-end test
playwright.config.js
```

## Troubleshooting

- **`✗ java -version failed` / Java < 21.** Install JDK 21 (`brew install
  openjdk@21` on macOS) and ensure it's on `PATH`.
- **`Could not locate the Anserini fatjar`.** Re-run the setup `curl` command
  or set `ANSERINI_JAR` explicitly.
- **Evaluating a non-CACM index hangs on first run.** Anserini downloads the
  prebuilt index into `~/.cache/pyserini/indexes/` on first use; some indexes
  are >10 GB. Subsequent runs are fast.
- **Server says "Index X is catalog-only".** That index has no registered
  topics/qrels pairing in the shipped reproduction configs. It remains visible
  in the catalog for browsing but cannot be evaluated automatically.
