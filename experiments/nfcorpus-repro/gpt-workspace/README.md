# NFCorpus Live Retrieval Diagnostics Workbench

Dockerized web app for live NFCorpus retrieval diagnostics using real Anserini commands.

## What it does

- Downloads or finds an Anserini released fatjar and checks Java/fatjar readiness.
- Uses Anserini reproduction discovery for `beir.core` (`--list`, `--show`, `--dry-run`) to find NFCorpus BM25 commands, qrels/eval key, metric definitions, and expected scores.
- Downloads/prepares only the small NFCorpus prebuilt index (`beir-v1.0.0-nfcorpus.flat`). It does **not** download all BEIR corpora.
- Runs live browser searches through `io.anserini.cli.Search`.
- Runs BM25 evaluation through `io.anserini.search.SearchCollection` plus Anserini `trec_eval`, then displays observed vs expected metrics, deltas, commands, and artifact paths.

## Local run

```bash
python3 app/server.py
# open http://127.0.0.1:10000
```

Optional environment variables:

- `PORT` — HTTP port, default `10000`.
- `ANSERINI_JAR` — path to an existing `anserini-*-fatjar.jar`.
- `ANSERINI_VERSION` — Maven Central version to download when `ANSERINI_JAR` is not provided.
- `NFCORPUS_CACHE_DIR` — runtime cache/data directory, default `.runtime` locally and `/data/nfcorpus-workbench` in Docker.
- `RUN_CACM_SMOKE` — defaults to `1`; runs the small CACM Anserini fatjar smoke test from the install skill before NFCorpus setup.

## Docker / Render

Build and run:

```bash
docker build -t nfcorpus-workbench .
docker run --rm -p 10000:10000 -e PORT=10000 nfcorpus-workbench
```

Render contract:

- Deploy as a Docker web service.
- The app binds to `0.0.0.0`.
- The app reads `PORT` and defaults to `10000` if unset.
- Health endpoint: `/health` returns JSON with app status, Anserini availability, NFCorpus readiness, search availability, and evaluation availability.
- Runtime caches and generated run/eval files live under `NFCORPUS_CACHE_DIR`. For Render persistent storage, mount a disk at `/data` so `/data/nfcorpus-workbench` persists between restarts.

## Browser verification

```bash
npm install
npx playwright install chromium
npm test
```

The test starts the server, waits for Anserini-backed setup/evaluation, searches NFCorpus from the browser, and asserts that exact Anserini search/evaluation commands and generated artifacts are visible.
