# NFCorpus Live Retrieval Diagnostics Workbench

Dockerized web app for live NFCorpus retrieval diagnostics with Anserini.

## What it runs

On startup the server performs non-interactive setup with real commands:

- Java 21 check and Anserini Maven Central fatjar download/location.
- CACM fatjar smoke verification from the `install-anserini-fatjar` workflow.
- `ReproduceFromPrebuiltIndexes --list`, `--show`, and `--dry-run` discovery for `beir.core`.
- NFCorpus-only BM25 retrieval: `SearchCollection -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus ... -bm25 -removeQuery`.
- NFCorpus qrels evaluation with Anserini `TrecEval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test ...`.
- Live browser queries via `io.anserini.cli.Search --index beir-v1.0.0-nfcorpus.flat --json`.

The app does **not** download all BEIR corpora. It uses only the NFCorpus prebuilt index/topics/qrels needed for this demo.

## Local run

```bash
npm start
# open http://localhost:10000
```

Optional environment:

- `PORT` - HTTP port, default `10000`.
- `APP_CACHE_DIR` - runtime cache, default `.cache` locally.
- `ANSERINI_JAR` - existing fatjar path.
- `ANSERINI_VERSION` - Maven Central release to download if no jar is supplied.

## Docker / Render

Build and run:

```bash
docker build -t nfcorpus-workbench .
docker run --rm -p 10000:10000 -e PORT=10000 -v nfcorpus-cache:/data/nfcorpus-workbench nfcorpus-workbench
```

Render setup:

- Service type: Docker web service.
- The container binds to `0.0.0.0` and reads `PORT`, defaulting to `10000`.
- Recommended persistent disk mount: `/data/nfcorpus-workbench`.
- Set `APP_CACHE_DIR=/data/nfcorpus-workbench` to persist the Anserini fatjar, NFCorpus index, run files, logs, topics, and qrels.

Health endpoint:

```bash
curl http://localhost:10000/health
```

It returns JSON with app status, Anserini availability, NFCorpus readiness, search availability, evaluation availability, active dataset, active index, and binding.

## Browser verification

```bash
npm install
npx playwright install chromium
npm test
```

The Playwright test opens the app, waits for real Anserini-backed readiness, runs a live NFCorpus query, verifies ranked docids/scores/snippets, checks observed-vs-expected numeric metrics, and asserts exact Java command lines plus artifact paths are visible.
