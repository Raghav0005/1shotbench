# NFCorpus Live Retrieval Diagnostics Workbench

A small Dockerized web app that turns the BEIR **NFCorpus** BM25 baseline into a
live, inspectable IR demo. It is driven entirely by real Anserini commands
(via the published Maven Central fatjar) and is designed to deploy as a single
Render Docker web service.

This implementation follows the three repo-local Anserini skills referenced in
the PRD:

- **`install-anserini-fatjar`** &mdash; the Dockerfile downloads
  `anserini-${ANSERINI_VERSION}-fatjar.jar` from Maven Central and points
  `ANSERINI_JAR` at it (no source build, no full BEIR archive).
- **`anserini-cli`** &mdash; the app uses `io.anserini.cli.PrebuiltIndexRegistry`
  to verify the NFCorpus prebuilt index entry and `io.anserini.api.RestServer`
  for live search.
- **`anserini-reproduction`** &mdash; setup runs
  `io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show`
  and `--dry-run` to *discover* the NFCorpus condition, qrels key, expected
  metric (`nDCG@10`), and exact commands rather than hardcoding them.

The only dataset downloaded is the ~7&nbsp;MB
`beir-v1.0.0-nfcorpus.flat` prebuilt index (3 633 documents).

## What the app does

1. **Setup phase (background thread)**
   - `java -version` check
   - `io.anserini.cli.PrebuiltIndexRegistry --list --filter '^beir-v1.0.0-nfcorpus.flat$'`
   - `io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show`
     &rarr; parse YAML, locate the `flat` / `nfcorpus` target
   - `... --dry-run` &rarr; capture the exact retrieval + eval commands
   - `io.anserini.search.SearchCollection -threads 4 -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus -bm25 -removeQuery -output cache/run.beir.bm25.nfcorpus.txt`
   - `io.anserini.eval.TrecEval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test cache/run.beir.bm25.nfcorpus.txt`
   - Parse observed metrics, compare to expected (`nDCG@10 = 0.3218`)
2. **Live search** &mdash; `io.anserini.api.RestServer` runs in the background on
   `127.0.0.1:$ANSERINI_REST_PORT` (default `8081`). Flask proxies
   `/api/search?q=...&hits=...` to it. Results include rank, docid, BM25 score,
   title, and the actual document text returned by the prebuilt index.
3. **Rerun** &mdash; `POST /api/evaluation/rerun` re-executes SearchCollection +
   TrecEval against the cached index. The UI labels the result as *fresh
   rerun* vs *cached setup pass*.
4. **Dashboard** &mdash; readiness panel, search panel, evaluation panel
   (observed vs expected with deltas/status), and a command/artifact drawer
   showing every `java -cp $ANSERINI_JAR ...` invocation, its exit code,
   elapsed time, stdout, and stderr.

## Docker / Render contract

- Container binds `0.0.0.0:$PORT`. `PORT` defaults to `10000` when unset
  (Render convention).
- `/health` returns JSON with `status`, `phase`, `anserini_available`,
  `nfcorpus_ready`, `search_available`, `evaluation_available`, plus the
  current dataset and any errors.
- Long-lived caches live under `${APP_CACHE_DIR}` (default `/data`). The
  Anserini prebuilt-index cache is symlinked into `/data/pyserini-cache`. Mount
  a Render disk at `/data` to keep NFCorpus warm across deploys (see
  `render.yaml`).
- No interactive setup &mdash; the entrypoint starts the RestServer and Flask;
  the rest happens in a background thread.

## Run locally with Docker

```bash
docker build -t nfcorpus-diagnostics .
docker run --rm -p 10000:10000 nfcorpus-diagnostics
# then open http://localhost:10000
```

The first run downloads the NFCorpus prebuilt index (~7 MB). Setup typically
finishes within ~60 seconds on a small container; the BM25 sweep over the
NFCorpus topics takes ~1 second once the index is local.

### Local Python (without Docker)

```bash
export ANSERINI_JAR=$PWD/anserini-2.1.1-fatjar.jar       # or any later release
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.server                                     # binds 0.0.0.0:10000
```

If the fatjar is not yet present, download it (per `install-anserini-fatjar`):

```bash
ANSERINI_VERSION=2.1.1
curl -fL -o anserini-${ANSERINI_VERSION}-fatjar.jar \
  https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar
export ANSERINI_JAR=$PWD/anserini-${ANSERINI_VERSION}-fatjar.jar
```

## Deploy to Render

The repo includes a `render.yaml` Blueprint:

- `runtime: docker`
- `healthCheckPath: /health`
- `disk: mountPath: /data` (1 GB, plenty for the NFCorpus index)
- `envVars`: `PORT`, `ANSERINI_REST_PORT`, `APP_CACHE_DIR`

Create a new Web Service from this repo and Render will read the Blueprint.

## HTTP API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Diagnostics dashboard (single-page). |
| `GET` | `/health` | Liveness + readiness JSON (PRD contract). |
| `GET` | `/api/status` | Full setup state, commands, evaluation, deployment info. |
| `GET` | `/api/search?q=...&hits=...` | Live BM25 search via Anserini RestServer. |
| `GET` | `/api/evaluation` | Current observed vs expected metrics. |
| `POST` | `/api/evaluation/rerun` | Re-run SearchCollection + TrecEval. |
| `GET` | `/api/artifacts` | List on-disk artifacts and sizes. |
| `GET` | `/api/artifact-preview?path=...` | Tail-safe preview of an artifact. |

## End-to-end test

A Playwright test exercises the full workflow:

```bash
pip install -r tests/requirements.txt
playwright install chromium
# Start the app first (Docker or `python -m app.server`).
APP_URL=http://localhost:10000 pytest tests/test_e2e.py -s
```

The test fails if the dashboard ever shows mocked search results, mocked eval
output, or hardcoded metric values without an Anserini-backed command behind
them. It also requires the Render readiness contract (PORT, /health) to be
documented in the UI.

## Project layout

```
.
├── app/
│   ├── __init__.py
│   ├── anserini.py          # subprocess wrappers around the fatjar
│   ├── setup.py             # background setup pipeline
│   ├── restserver.py        # io.anserini.api.RestServer lifecycle
│   ├── server.py            # Flask app + HTTP API
│   └── static/              # SPA frontend
├── tests/test_e2e.py        # Playwright end-to-end test
├── Dockerfile
├── entrypoint.sh
├── render.yaml
├── requirements.txt
└── README.md
```

## NFCorpus expected metric

Anserini's `ReproduceFromPrebuiltIndexes --config beir.core --show` reports
`nDCG@10 = 0.3218` for the BM25 flat baseline on `beir-v1.0.0-nfcorpus.test`.
The dashboard surfaces both the discovered expected value and the observed
value reported by `TrecEval`, plus a delta and pass/close/fail status.

## Troubleshooting

- **`ANSERINI_JAR not set`** &mdash; check the env in the container; the
  Dockerfile sets it to `/opt/anserini-${ANSERINI_VERSION}-fatjar.jar`.
- **Java major != 21** &mdash; Anserini requires Java 21; the image uses
  `eclipse-temurin:21-jdk`.
- **Port in use** &mdash; change `PORT` or `ANSERINI_REST_PORT`.
- **Cold start** &mdash; the first Render deploy downloads the NFCorpus index
  into `/data`; subsequent deploys reuse it.
