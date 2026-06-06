# NFCorpus Live Retrieval Diagnostics Workbench

Anserini-backed web dashboard for live NFCorpus BM25 search and evaluation diagnostics. Built for deployment as a Render Docker web service.

## Quickstart (Local)

```bash
# Install dependencies
pip install -r requirements.txt

# Ensure Java 21 is available
java -version  # must show 21.x

# Run the app
python app.py
```

The app starts on port 10000 (configurable via `PORT` env var).

Open http://localhost:10000 in your browser.

## What It Does

1. **Verifies environment**: checks Java 21, downloads Anserini fatjar, runs CACM smoke test
2. **Prepares NFCorpus**: sets up the `beir-v1.0.0-nfcorpus.flat` prebuilt index
3. **Live Search**: execute real Anserini-backed search queries over NFCorpus from the browser
4. **BM25 Evaluation**: run `SearchCollection` + `TrecEval` and compare observed metrics against expected values
5. **Transparency**: shows exact command lines, artifact paths, and raw evaluation output

## Docker

```bash
docker build -t nfcorpus-workbench .
docker run -p 10000:10000 nfcorpus-workbench
```

### Pre-downloaded in Image
The Docker image includes:
- Anserini 2.1.1 fatjar
- CACM prebuilt index (smoke test)
- NFCorpus `beir-v1.0.0-nfcorpus.flat` prebuilt index

This avoids download delays on cold start.

## Render Deployment

### Docker Web Service

1. Push the repository to GitHub/GitLab
2. Create a new Render **Web Service** pointing to the repo
3. Set:
   - **Runtime**: Docker
   - **Port**: `10000` (Render auto-sets `PORT` env var)
   - **Health Check Path**: `/health`
   - **Plan**: At least 2 GB RAM recommended for Java + Lucene index

### Health Endpoint

`GET /health` returns:

```json
{
  "status": "ready",
  "anserini_available": true,
  "nfcorpus_ready": true,
  "search_available": true,
  "evaluation_available": true,
  "java_version": "openjdk version \"21.0.11\" ...",
  "errors": []
}
```

### Persistent Storage (Optional)

The NFCorpus prebuilt index is cached at:
```
~/.cache/pyserini/indexes/
```

For Render persistent disk, mount at `/root/.cache/pyserini` to retain indexes across deploys. The Dockerfile already pre-downloads indexes during build, so persistent storage is optional.

## Expected BM25 Metrics (NFCorpus)

| Metric  | Expected | Anserini Command                                    |
|---------|----------|-----------------------------------------------------|
| nDCG@10 | 0.3218   | `TrecEval -c -m ndcg_cut.10`                        |
| R@100   | 0.2457   | `TrecEval -c -m recall.100`                         |
| R@1000  | 0.3704   | `TrecEval -c -m recall.1000`                        |

From Anserini reproduction config `beir-v1.0.0-nfcorpus.flat`.

## Browser Tests

```bash
pip install pytest playwright
playwright install chromium
python -m pytest tests/test_browser.py -v
```

The test verifies:
- Health endpoint and readiness panel
- Live NFCorpus search with ranked results (doc IDs, scores, text)
- Evaluation metrics display (observed vs expected)
- Command and artifact visibility
- Real Anserini commands (not mocked)
- PORT binding for Render

## Architecture

```
app.py              Flask backend + Anserini CLI wrapper
templates/index.html HTML/JS dashboard
Dockerfile           Docker image with Java 21 + Anserini fatjar
tests/test_browser.py Playwright E2E test
data/                Runtime cache directory (gitignored)
```

## Dataset

- **Corpus**: NFCorpus (BEIR v1.0.0), 3,633 biomedical documents
- **Topics**: 323 test queries
- **Qrels**: Included with Anserini topics registry
- **Index**: Prebuilt Lucene inverted index (`beir-v1.0.0-nfcorpus.flat`)

## Notes

- This app is intentionally scoped to NFCorpus only. It does not download other BEIR corpora or MS MARCO.
- All search and evaluation uses real Anserini commands via the fatjar. No results are hardcoded or mocked.
- First startup may take 1-2 minutes for index download and CACM smoke test. Subsequent starts use cached indexes.
