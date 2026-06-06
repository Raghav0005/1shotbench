# NFCorpus Live Retrieval Diagnostics Workbench

A small Dockerized web application that exposes an Anserini-backed retrieval
diagnostics dashboard for the BEIR **NFCorpus** collection. It can be
deployed as a single Docker web service on [Render](https://render.com) (or
any other container host) and lets a user:

1. Check the readiness of Java, the Anserini fatjar, and the NFCorpus
   prebuilt index.
2. Run live BM25 searches against NFCorpus from the browser and inspect
   ranked hits with snippets.
3. Run a full BM25 evaluation on the BEIR/nfcorpus test topics, see the
   observed metrics, and compare them to the expected reproduction target
   (`nDCG@10 = 0.3218` from `beir.core · flat`).
4. Inspect the exact Anserini commands and the paths of every generated
   artifact.

The app is intentionally limited to NFCorpus so that a modest hosted
container is enough — it does not download the full BEIR archive and it
does not need MS MARCO, dense retrieval, or authentication.

## Project layout

```text
.
├── Dockerfile                # Container build for Render
├── .dockerignore
├── requirements.txt
├── nfcorpus_app/
│   ├── __init__.py           # Flask routes (/, /health, /api/*)
│   ├── anserini.py           # Anserini CLI + reproduction wrappers
│   ├── config.py             # Paths, dataset constants, runtime checks
│   └── static/               # Dashboard HTML/CSS/JS
├── e2e/
│   ├── test_dashboard.py     # Playwright end-to-end test
│   └── README.md
└── README.md                 # You are here
```

## Quick start (local Docker)

```bash
docker build -t nfcorpus-workbench .
docker run --rm -p 10000:10000 -e PORT=10000 nfcorpus-workbench
```

Open <http://localhost:10000/>. The first request will trigger the fatjar
verification (already pre-staged in the image) and the NFCorpus prebuilt
index download (~6.2 MB). Subsequent runs reuse the cache.

## Quick start (local Python)

```bash
python3 -m pip install -r requirements.txt
ANSERINI_JAR=/path/to/anserini-X.Y.Z-fatjar.jar \
  python3 -m gunicorn --bind 0.0.0.0:10000 nfcorpus_app:app
```

If `ANSERINI_JAR` is unset, the app downloads the fatjar from Maven
Central on first request.

## HTTP API

| Route                       | Method | Purpose |
|-----------------------------|--------|---------|
| `/`                         | GET    | Dashboard (HTML). |
| `/health`                   | GET    | JSON readiness probe. |
| `/api/status`               | GET    | Full readiness + dataset details. |
| `/api/setup/fatjar`         | POST   | Download + verify the Anserini fatjar. |
| `/api/setup/reproduction`   | GET    | Parse `ReproduceFromPrebuiltIndexes --show` for NFCorpus. |
| `/api/search?q=…&hits=…`    | GET    | Live BM25 search via `io.anserini.cli.Search --json`. |
| `/api/evaluate`             | GET/POST | Run cached batch retrieval + TrecEval. |
| `/api/verify`               | POST   | Force a fresh rerun of the evaluation. |
| `/api/artifacts`            | GET    | List generated run/eval/log files. |
| `/api/commands/<name>`      | GET    | Raw stdout/stderr of a recorded command. |

## What the dashboard does

* **Readiness panel** — Java, fatjar, NFCorpus prebuilt index, reproduction
  discovery, live search, and BM25 evaluation signals. When the fatjar is
  missing, clicking *Refresh* (or hitting the endpoint) triggers a
  Maven-Central download.
* **Live search** — A free-text box plus a handful of NFCorpus sample
  queries. Each call invokes `io.anserini.cli.Search --json
  --index beir-v1.0.0-nfcorpus.flat`. Results show rank, docid, BM25
  score, title, snippet, and source URL.
* **BM25 evaluation** — `io.anserini.search.SearchCollection` writes a
  TREC run file under `data/runs/`, then `io.anserini.eval.TrecEval`
  produces `data/eval/eval.nfcorpus.bm25.txt`. Observed metrics are parsed
  and compared to the reproduction-provided expected values
  (`nDCG@10 = 0.3218`). The verdict is `match` / `close` (within 1%
  relative tolerance) / `fail` / `missing`. A cached version of the run
  is reused by default; *Verify/Rerun* forces a fresh run.
* **Commands & artifacts drawer** — Every Anserini command line is
  captured with elapsed time and the full log under `data/logs/`. All
  generated files are listed with their sizes.

## End-to-end test

The Playwright test in `e2e/test_dashboard.py` boots the dashboard (the
caller is responsible for starting the server — see the script for the
recommended invocation) and asserts:

* The readiness panel and the `dataset: nfcorpus` badge are visible.
* Java + Anserini + NFCorpus readiness dots turn green.
* A live search returns at least one ranked result with a docid and a
  numeric score.
* The evaluation panel shows at least one numeric observed metric and the
  expected-vs-observed comparison.
* The commands drawer lists the exact Anserini command lines.
* The Docker / Render readiness contract is documented in the UI.

Run it with:

```bash
python3 -m pip install playwright pytest
python3 -m playwright install chromium
NFCORPUS_BASE_URL=http://localhost:10000 \
  python3 -m pytest e2e/test_dashboard.py -v
```

## Deployment on Render

1. Push this repository to GitHub/GitLab.
2. Create a **Web Service** on Render pointing at the repository.
3. Set:
   * **Environment** = `Docker`
   * **Region** = any
   * **Instance type** = at least `Standard` (1 GB RAM recommended so the
     Lucene index fits in memory).
   * **Health check path** = `/health`
4. Render will inject `PORT`. The container already binds
   `0.0.0.0:${PORT}` and defaults `PORT` to `10000`.
5. (Optional) Add a persistent disk and mount it at `/app/data` to keep
   the cached NFCorpus index, run files, and command logs across deploys.

The first hit to `/api/evaluate` may take a few seconds while the
~6.2 MB NFCorpus prebuilt index is downloaded from
`huggingface.co/datasets/castorini/prebuilt-indexes-beir/`. Subsequent
deploys reuse the cached index.

## Data sources

* Anserini fatjar — <https://repo1.maven.org/maven2/io/anserini/anserini/>
* NFCorpus prebuilt index — `beir-v1.0.0-nfcorpus.flat` (~6.2 MB,
  registered in `io.anserini.cli.PrebuiltIndexRegistry`).
* BEIR topics + qrels — `beir-nfcorpus` and `beir-v1.0.0-nfcorpus.test`
  from Anserini's built-in topics/qrels registry.
* Reproduction config — `io.anserini.reproduce.ReproduceFromPrebuiltIndexes
  --config beir.core --show`, filtered to topic `nfcorpus` under
  condition `flat`.

## Troubleshooting

* **Java not found** — the container must run with a JDK 21 image; locally
  install JDK 21 (`brew install openjdk@21` or equivalent).
* **Fatjar download fails** — verify outbound HTTPS to
  `repo1.maven.org` is allowed. Re-run `POST /api/setup/fatjar`.
* **NFCorpus index download fails** — verify outbound HTTPS to
  `huggingface.co` and `rgw.cs.uwaterloo.ca` (the pyserini cache mirrors
  Anserini's prebuilt indexes). The index is only ~6.2 MB.
* **Port conflict** — the README and `/health` document the
  `PORT` contract; on Render the variable is auto-injected.
* **`unsupported Anserini version`** — the app intentionally targets
  the Anserini fatjar; if a new major version is required, bump
  `ANSERINI_VERSION` in the `Dockerfile` and verify with the
  `install-anserini-fatjar` skill.
