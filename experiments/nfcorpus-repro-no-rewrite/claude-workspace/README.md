# NFCorpus Live Retrieval Diagnostics Workbench

A small, Dockerized web app for **live NFCorpus retrieval diagnostics with
[Anserini](https://github.com/castorini/anserini)**. It lets you:

- run **live BM25 search over NFCorpus** from the browser,
- inspect the **real Anserini commands** used for setup, search, and evaluation,
- see **expected vs. observed** nDCG@10 (with delta) for the BM25 baseline,
- verify with one click via the **Verify / Rerun evaluation** button.

The whole app is wired to real Anserini executions. There are no mocked
search results, no hardcoded run files, no hardcoded scores. The expected
metric value is discovered at startup by running
`io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show`,
and the observed value is parsed from real `TrecEval` output.

## What this app does (and doesn't do)

- **Does**: NFCorpus (3.6k docs / 323 test queries) only. BM25 baseline only.
- **Doesn't**: download the full BEIR archive, MS MARCO, or dense indexes.
  Index downloads are strictly NFCorpus-scoped (~6 MB).

## Architecture

```
┌────────────── browser ──────────────┐
│  /static/index.html  (vanilla JS)   │
└──────────────────┬──────────────────┘
                   │ HTTP  (PORT)
┌──────────────────▼──────────────────┐
│ FastAPI  app/main.py                │
│   /health   /api/state              │
│   /api/search  /api/eval/rerun      │
└─────┬──────────────────────┬────────┘
      │ proxy HTTP            │ subprocess
      │                       ▼
      │       ┌─── java SearchCollection ──► run.nfcorpus.bm25.txt
      │       └─── java TrecEval ──────────► eval.nfcorpus.bm25.txt
      ▼
 java io.anserini.api.RestServer  (live BM25 search backend)
      ▲ uses
      └── prebuilt index "beir-v1.0.0-nfcorpus.flat" (~6 MB)
```

Each major step references the repo-local Anserini skills:

| Step                       | Skill                       | Command                                                  |
| -------------------------- | --------------------------- | -------------------------------------------------------- |
| Locate/verify fatjar       | `install-anserini-fatjar`   | `java -cp $ANSERINI_JAR io.anserini.cli.PrebuiltIndexRegistry --list --filter '^beir-v1.0.0-nfcorpus.flat$'` |
| Discover NFCorpus baseline | `anserini-reproduction`     | `java -cp $ANSERINI_JAR io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show` |
| Live BM25 search           | `anserini-cli`              | `java -cp $ANSERINI_JAR io.anserini.api.RestServer --host 127.0.0.1 --port 8081` |
| BM25 retrieval (eval)      | `anserini-cli`              | `java -cp $ANSERINI_JAR io.anserini.search.SearchCollection -threads 2 -index beir-v1.0.0-nfcorpus.flat -topics beir-v1.0.0-nfcorpus.test -output runs/run.nfcorpus.bm25.txt -bm25 -removeQuery` |
| Eval against qrels         | `anserini-cli` + reproduction | `java -cp $ANSERINI_JAR io.anserini.eval.TrecEval -c -m ndcg_cut.10 -m map -m recall.100 beir-v1.0.0-nfcorpus.test runs/run.nfcorpus.bm25.txt` |

Expected nDCG@10 for the BM25 NFCorpus baseline (from `beir.core` / `flat`
condition): **0.3218**. The app compares the observed value against this with
the same tolerance Anserini's reproduce harness uses
(`match` < 1e-4, `close` ≤ 5e-4, otherwise `fail`).

## Deployment contract (Docker / Render)

- Single Docker image. `Dockerfile` is at repo root.
- Container binds **`0.0.0.0`** on the **`PORT`** environment variable;
  defaults to **`10000`** when `PORT` is unset.
- `GET /health` returns JSON including:
  - `app` (always `"ok"` once the server is up),
  - `anserini_available` (java + fatjar resolved),
  - `nfcorpus_ready` (prebuilt index cached),
  - `search_available` (RestServer up),
  - `eval_available` (evaluation has completed at least once),
  - `eval_status` (`pending` | `running` | `ok` | `error`),
  - `errors` (list of human-readable strings).
- No interactive setup required after `docker run`. NFCorpus index download
  and the initial BM25 evaluation run in the background; readiness is
  reported live by `/health` and the readiness panel.
- Persistent cache lives at **`/data`** inside the container (overridable
  with `NFCORPUS_DATA_DIR`). On Render, mount a small (1 GB) disk at
  `/data` to skip re-downloading the NFCorpus prebuilt index on restart.
  See `render.yaml`.
- Large generated files (`data/`, `*.jar`) are excluded from source control
  (`.gitignore` / `.dockerignore`).

## Local development

```bash
# 1. Install Anserini fatjar (uses the install-anserini-fatjar skill).
ANSERINI_VERSION=2.1.1
curl -fL -o /tmp/anserini.jar \
  "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
export ANSERINI_JAR=/tmp/anserini.jar

# 2. Install Python deps.
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 3. Run.
PORT=10000 NFCORPUS_DATA_DIR=./data python -m app.main
# open http://localhost:10000
```

## Docker

```bash
docker build -t nfcorpus-workbench .
docker run --rm -p 10000:10000 -v "$(pwd)/data:/data" nfcorpus-workbench
# open http://localhost:10000
```

The container will:

1. Verify Java 21 + the bundled Anserini fatjar.
2. Run a `PrebuiltIndexRegistry` filter for `^beir-v1.0.0-nfcorpus.flat$`.
3. Run `ReproduceFromPrebuiltIndexes --config beir.core --show` to discover
   the expected nDCG@10 reproduction target.
4. Warm up / download the NFCorpus prebuilt index (~6 MB) into `/data`.
5. Start `io.anserini.api.RestServer` on `127.0.0.1:8081` (used internally).
6. Run a real BM25 evaluation in the background and report the comparison.

## End-to-end test

`tests/test_e2e.py` is a Playwright test that:

- starts the FastAPI app on a free port,
- waits for `/health` to report `search_available` + `eval_available`,
- opens the page in a browser,
- verifies the readiness panel shows NFCorpus + Anserini status,
- clicks a sample query and verifies real ranked results appear (rank,
  docid, score, snippet),
- verifies the evaluation panel shows observed and expected metric values
  and a numeric delta,
- verifies the exact Anserini command text and artifact paths are visible
  in the command/artifact drawer,
- verifies the Render/Docker readiness contract text is present in the UI,
- triggers `Verify / Rerun evaluation` and confirms a fresh rerun is
  reflected in the UI.

To run it:

```bash
pip install pytest pytest-asyncio playwright
playwright install chromium
ANSERINI_JAR=/tmp/anserini.jar pytest tests/test_e2e.py -v
```

The test fails if:

- search results lack real docids/snippets,
- observed metric values do not appear (i.e. the eval did not actually run),
- exact Anserini command text is missing from the drawer.
