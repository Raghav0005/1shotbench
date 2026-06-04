# NFCorpus Live Retrieval Diagnostics Workbench

## Project Overview

Build a single Dockerized web application deployable on Render that provides live NFCorpus retrieval diagnostics powered by Anserini. The application must let users search NFCorpus in real time, observe how the dataset was prepared using Anserini skills, and verify whether Anserini's observed BM25 evaluation metrics match the expected reproduction targets. The scope is intentionally limited to NFCorpus only—no full BEIR download, no general-purpose retrieval dashboard.

---

## Problem Statement

Anserini's retrieval evaluation workflow is spread across skill documentation, CLI commands, run files, qrels, evaluator output, and deployment concerns. Researchers and developers need a small, hosted, self-contained demo that makes a real IR workflow fully inspectable: live search, dataset preparation, and observed-vs-expected evaluation metrics—all visible in a browser.

---

## Users

| Persona | Need |
|---|---|
| IR researchers | Small live retrieval-quality demo |
| Anserini developers | Validate NFCorpus setup and evaluation workflows |
| Demo viewers | Compare live search results with measured retrieval metrics |
| Operators | Deploy benchmark outputs to Render |

---

## Goals (What the App Must Do)

1. **Use repo-local Anserini skills** as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation commands.
2. **Deploy as a single Render Docker web service.**
3. **Use NFCorpus as the sole dataset**—no other BEIR corpora.
4. **Live query search** over NFCorpus via an Anserini-backed backend (REST server or CLI-backed endpoint).
5. **Run or verify a BM25 evaluation** using real Anserini commands and qrels.
6. **Show expected vs. observed metrics**, deltas, commands, and artifact paths in the browser.
7. **Browser-driven verification** proving no mocked search or mocked evaluation results.

---

## Non-Goals (What the App Must NOT Do)

- Support all BEIR datasets or download the full BEIR corpus archive
- MS MARCO or other large-corpus demos
- Dense retrieval, neural reranking, or model training
- User accounts, authentication, or multi-user job management
- Custom retrieval engines
- Use `GetDocument` when search results already include useful document content
- Require Vercel deployment

---

## Core Requirements

### Skill Dependencies
The app must consult these repo-local skills before constructing any commands:
- `install-anserini-fatjar`
- `anserini-cli`
- `anserini-reproduction`

### Fatjar Setup
- Locate or install an Anserini fatjar and verify it using the skill's runtime checks.
- Store the verification command in the UI.

### Reproduction Discovery
- Discover NFCorpus-related reproduction support using the Anserini reproduction workflow.
- Use reproduction listing/show/dry-run behavior where available to identify:
  - NFCorpus setup commands
  - Expected metrics
  - qrels/eval keys
  - Setup requirements

### Dataset Scope
- Any download or cache step must be NFCorpus-specific and documented in the UI.
- Do not download all BEIR corpora.

### Artifact Preference
- Prefer a prebuilt/cached NFCorpus index or NFCorpus-specific artifact when Anserini exposes one.
- If no suitable prebuilt path is available, the app may build or prepare only the NFCorpus index.

### Real Command Execution
- Use real Anserini commands for setup, search, and evaluation.
- Do NOT hardcode or mock: search results, run files, qrels, scores, or expected metrics.

### Search Backend
- Backend must support live query search over NFCorpus.
- Implementation may use Anserini REST server or CLI-backed search endpoint.
- Must be backed by Anserini, not a custom search implementation.
- Search results must include: rank, document id, score, and document content/snippet text.

### BM25 Evaluation Workflow
The app must:
1. Run `SearchCollection` or the reproduction-provided equivalent command
2. Write a TREC-format run file
3. Evaluate with the appropriate Anserini/TrecEval command
4. Parse observed metric values
5. Compare observed values with the reproduction-provided expected values when available

### Cached Evaluation Option
- If live evaluation is too slow for hosted use, the app may run evaluation during setup/startup and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts.
- The UI must clearly distinguish cached setup results from a fresh rerun.

### Status/Readiness Panel
Show a readiness panel with:
- Java/fatjar status
- NFCorpus artifact/index status
- Reproduction discovery status
- Whether the app is ready for live search
- Whether the app is ready for evaluation

### Command Visibility
Show exact command lines for:
- Fatjar verification
- Reproduction discovery/dry-run
- NFCorpus search setup
- BM25 retrieval
- Evaluation

### Artifact Path Visibility
Show artifact paths for:
- Generated run files
- Evaluation output
- Setup logs
- Any cached NFCorpus data

### Error Handling
Handle and display clear user-visible errors for:
- Missing Java
- Missing fatjar
- Unsupported Anserini version
- Missing NFCorpus artifacts
- Command failures
- Unavailable expected metrics
- Port conflicts
- Evaluation failures

---

## Deployment Requirements

### Docker/Render Readiness
- Must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile or equivalent generated project files.
- Container must bind HTTP to `0.0.0.0` and use `PORT` from the environment, defaulting to `10000` when unset.
- Must not require interactive setup after container start.

### File Management
- Large generated files should be kept out of source control.
- Runtime caches should live under a documented cache/data directory.
- If persistent storage is needed on Render, document the mount path.

### Size Constraints
- Keep the default demo small enough for a modest Render service.
- Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

### Health Endpoint
Provide a `/health` endpoint returning JSON with at least:
- App status
- Anserini availability
- NFCorpus readiness
- Whether search is available
- Whether evaluation is available

---

## UX Specification

### Page Layout
On page load, display a compact diagnostics dashboard with:

1. **Readiness/Status Panel** — Anserini and NFCorpus readiness indicators
2. **Live Search Box** — With a few NFCorpus sample queries/topics
3. **Ranked Result List** — Ranks, ids, scores, snippets/document content
4. **Evaluation Panel** — BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, artifact paths
5. **Command/Artifact Drawer** — Exact Anserini commands and output previews used to produce the visible results

### Interactions
- User can type a query or click a sample NFCorpus query to run live search
- User can inspect BM25 evaluation status
- User can trigger a verification/rerun when supported by the implementation

---

## End-to-End Browser Test Requirements

The included Playwright/browser test must:

1. Open the app
2. Verify the health/readiness panel appears
3. Verify NFCorpus is identified as the active dataset
4. Verify Anserini setup status is visible
5. Run or select a live NFCorpus query
6. Verify ranked search results appear with document ids, ranks, scores, and text/snippets
7. Verify the evaluation panel displays at least one numeric observed metric
8. Verify expected metric information appears when reproduction discovery exposes it
9. Verify observed-vs-expected comparison status or delta appears
10. Verify exact command text and artifact paths/previews are visible
11. Verify the Docker/Render readiness contract is documented (README or in-app), including `PORT` binding

**The test must FAIL if the app only displays mocked search results, mocked evaluation output, or hardcoded metric values without executing Anserini-backed setup/search/evaluation commands.**

---

## Success Criteria

| # | Criterion |
|---|---|
| 1 | The app runs locally in Docker and serves HTTP on the configured `PORT` |
| 2 | The app can be deployed as a Render Docker web service |
| 3 | Users can run live NFCorpus search from the browser |
| 4 | Users can inspect real Anserini-backed NFCorpus evaluation metrics |
| 5 | Users can see expected-vs-observed metric comparison when expected metrics are discoverable |
| 6 | The app avoids full-BEIR and large-corpus downloads by default |
| 7 | Command lines, artifacts, and failure states are transparent enough to debug |
| 8 | The Playwright/browser test passes and proves the real Anserini workflow is exercised |

---

## Summary

This is a single-purpose, self-contained NFCorpus retrieval diagnostics workbench. It must use real Anserini commands (not mocks), expose the full pipeline and artifacts in the UI, and be deployable as one Docker service on Render. Everything—skills, commands, metrics, and artifacts—must be inspectable in the browser.