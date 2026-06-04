# NFCorpus Live Retrieval Diagnostics Workbench

A Dockerized web app for live NFCorpus retrieval diagnostics with Anserini. It uses the repo-local Anserini skill workflow: Java/fatjar verification, `ReproduceFromPrebuiltIndexes` discovery for `beir.core`, live `io.anserini.cli.Search`, BM25 `SearchCollection`, and `io.anserini.eval.TrecEval`.

## What runs

- Dataset: **NFCorpus only** (`beir-v1.0.0-nfcorpus.flat`, topics `beir-nfcorpus`, qrels/eval key `beir-v1.0.0-nfcorpus.test`).
- Search: `java -cp $ANSERINI_JAR io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat --query ... --json`.
- Evaluation: `SearchCollection` writes a TREC run file, then `TrecEval -c -m ndcg_cut.10` evaluates it.
- Expected metric is discovered from Anserini reproduction config `beir.core` (`flat` / `nfcorpus`) and compared with observed output.

No full BEIR archive, MS MARCO, dense-vector artifacts, or non-NFCorpus BEIR corpora are downloaded by default. Runtime caches and generated run/eval logs live in `DATA_DIR` (default `./data`; Docker default `/var/data/nfcorpus-workbench`).

## Local run

```bash
npm install
npm start
# open http://localhost:10000
```

If `ANSERINI_JAR` is unset, the app locates `/opt/anserini/anserini-$ANSERINI_VERSION-fatjar.jar` or downloads the Maven Central fatjar into `DATA_DIR/jars`.

## Docker / Render

The container is a single Render-compatible web service. It binds HTTP to `0.0.0.0` and uses `PORT` from the environment, defaulting to `10000`.

```bash
docker build -t nfcorpus-workbench .
docker run --rm -p 10000:10000 -e PORT=10000 -v nfcorpus-data:/var/data/nfcorpus-workbench nfcorpus-workbench
```

Render settings:

- Service type: Docker Web Service
- Health check path: `/health`
- Optional persistent disk mount: `/var/data/nfcorpus-workbench`
- Optional env: `PORT`, `DATA_DIR`, `ANSERINI_VERSION`, `ANSERINI_THREADS`

`/health` returns JSON containing app status, Anserini availability, NFCorpus readiness, search availability, and evaluation availability.

## Browser verification

```bash
npx playwright install chromium
npm test
```

The test opens the app, runs a real query, verifies ranked results with doc ids/scores/snippets, checks a numeric observed metric plus expected-vs-observed delta/status, and confirms exact Anserini command text and artifact paths are visible.
