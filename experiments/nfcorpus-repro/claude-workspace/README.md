# NFCorpus Live Retrieval Diagnostics Workbench

A small, Docker-based, Render-deployable web app that surfaces **live** NFCorpus
retrieval diagnostics on top of [Anserini](https://github.com/castorini/anserini).
The implementation follows the repo-local skills:

| Skill                       | Used for                                                                |
|-----------------------------|-------------------------------------------------------------------------|
| `install-anserini-fatjar`   | Verifying Java 21 and downloading the released fatjar from Maven Central |
| `anserini-cli`              | `SearchCollection`, `TrecEval`, `PrebuiltIndexRegistry`, `RestServer`    |
| `anserini-reproduction`     | `ReproduceFromPrebuiltIndexes --config beir.core --show / --dry-run`     |

Scope is limited to **NFCorpus only** — the app never downloads the full BEIR
archive, MS MARCO, or any large corpora.

## What it shows

- **Readiness panel** — Java, Anserini fatjar, NFCorpus index, reproduction
  discovery, live-search server, and BM25 evaluation status cards.
- **Live NFCorpus search** — backed by an embedded `io.anserini.api.RestServer`
  process talking to the `beir-v1.0.0-nfcorpus.flat` prebuilt index.
  Results include rank, docid, score, title and snippet text.
- **BM25 evaluation** — a startup pass runs
  `io.anserini.search.SearchCollection` then `io.anserini.eval.TrecEval`
  (`-c -m ndcg_cut.10`, qrels key `beir-v1.0.0-nfcorpus.test`) and compares
  observed nDCG@10 against the expected value (`0.3218`) discovered from the
  reproduction config. A browser-triggered **Rerun** repeats the pipeline.
- **Commands & artifacts** — every spawned `java -cp $ANSERINI_JAR …` command
  is recorded with its argv, working directory, exit code, and stdout/stderr
  previews. Run/eval file paths are surfaced as artifact links.
- **Docker / Render contract panel** — documents the deployment requirements
  below in-app, in addition to this README.

## Anserini facts pinned by the implementation

These are discovered at runtime, not hardcoded into the UI:

| Field                | Value                                                |
|----------------------|------------------------------------------------------|
| Reproduction config  | `beir.core` (condition `flat`)                       |
| Topics symbol        | `beir-nfcorpus`                                      |
| Prebuilt index       | `beir-v1.0.0-nfcorpus.flat`                          |
| Qrels / eval key     | `beir-v1.0.0-nfcorpus.test`                          |
| Metric               | `nDCG@10` via `trec_eval -c -m ndcg_cut.10`          |
| Expected nDCG@10     | `0.3218`                                             |

## Run locally without Docker

```bash
# Java 21 must be on PATH (see install-anserini-fatjar skill).
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PORT=10000 python -m app.main
# then open http://127.0.0.1:10000
```

The first request downloads the Anserini fatjar (~110 MB) and the NFCorpus
prebuilt index (~7 MB) into `./cache/`.

## Run with Docker locally

```bash
docker build -t nfcorpus-workbench .
docker run --rm -p 10000:10000 -e PORT=10000 nfcorpus-workbench
# then open http://127.0.0.1:10000
```

The container binds `0.0.0.0:$PORT` (defaulting to `10000` when `PORT` is unset)
and exposes `/health` for the platform health probe.

## Deploy on Render

1. Create a new **Web Service** → **Deploy from a Git repository** and pick this
   repo (root directory containing the `Dockerfile`).
2. Pick **Docker** as the runtime. No build command is required.
3. Render injects `PORT` automatically; the container binds it on `0.0.0.0`.
   The documented default when `PORT` is unset is `10000`.
4. Set the **Health Check Path** to `/health`.
5. (Recommended) Add a small **Persistent Disk** of ≥ 1 GB mounted at `/data`.
   The cache directory used inside the container is `/data/cache` (controlled
   by the `WORKBENCH_CACHE_DIR` env var). With the mount in place the ~110 MB
   fatjar and the ~7 MB NFCorpus index survive deploys.
6. (Optional) Pin `ANSERINI_VERSION` as an env var if you want a specific
   Anserini release; otherwise the Dockerfile default (`2.1.1`) is used.

The default plan is sized for the NFCorpus-only demo. The app deliberately
avoids any heavyweight downloads (no full BEIR archive, no MS MARCO, no dense
vectors).

## Endpoints

| Endpoint           | Purpose                                               |
|--------------------|-------------------------------------------------------|
| `GET /`            | Dashboard HTML                                        |
| `GET /health`      | Render-style health JSON: app, anserini, nfcorpus, search, evaluation flags |
| `GET /api/status`  | Full status snapshot (cards, commands, evaluation)    |
| `GET /api/search`  | `?q=...&hits=N` proxies to embedded Anserini REST     |
| `POST /api/evaluate` | Triggers a fresh SearchCollection + TrecEval rerun |

## Authenticity

- No mocked search results: `/api/search` always proxies to
  `io.anserini.api.RestServer`. If that server is not yet ready, the endpoint
  returns 503.
- No mocked metrics: the evaluation pipeline always runs `SearchCollection`
  and `TrecEval` against the real qrels (`beir-v1.0.0-nfcorpus.test`). The
  expected value (`nDCG@10 = 0.3218`) is parsed live from the Anserini
  reproduction config output, not hardcoded into the UI.
- The browser test in `tests/test_e2e.py` proves that search docids match the
  NFCorpus pattern (`MED-…`), that observed `nDCG@10` is within 0.005 of the
  reproduction-published expected value, and that command panels reference the
  expected Anserini main classes and the produced run file actually exists on
  disk with TREC-format content.

## Browser tests

```bash
pip install -r requirements.txt
pip install playwright pytest
playwright install chromium
pytest tests/test_e2e.py -s
```

The test boots the FastAPI app in-process, waits for `phase == ready`, opens
the dashboard, exercises a sample query, rerun, and asserts every PRD
end-to-end checkpoint.
