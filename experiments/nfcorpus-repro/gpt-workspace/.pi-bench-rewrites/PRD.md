# PRD

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Summary
Create a Dockerized web application, deployable to Render, that provides live retrieval diagnostics for NFCorpus using Anserini. The application must rely on Anserini skills to prepare and validate an NFCorpus retrieval environment, perform live searches over NFCorpus, execute or verify a BM25 evaluation with expected metrics, and display in the browser the exact commands, artifacts, and observed-versus-expected outcomes.

The scope is deliberately limited to NFCorpus so the demo remains suitable for a modest hosted container. Do not implement a general BEIR dashboard and do not download all BEIR corpora.

## Problem
Although Anserini supports reproducing and evaluating retrieval baselines, the process is distributed across skill documentation, command discovery, run files, qrels, evaluator output, and deployment/runtime setup. The required deliverable is a compact hosted demo that exposes a real IR workflow: users should be able to search NFCorpus live, inspect how the dataset was prepared, and determine whether observed Anserini evaluation metrics match the expected reproduction target.

## Goals
- Treat the repo-local Anserini skills as the authoritative source for setup steps, CLI syntax, reproduction discovery, search, and evaluation.
- Build a live web app that can run as a Render Docker web service.
- Make NFCorpus the only required dataset.
- Provide live query search for NFCorpus through a backend powered by Anserini.
- Run or verify a BM25 NFCorpus evaluation using real Anserini commands and qrels.
- Display expected metrics, observed metrics, deltas, commands, and paths to generated artifacts.
- Add browser-driven verification demonstrating that search and evaluation are not mocked.

## Non-Goals
- Support for every BEIR dataset.
- Downloading the complete BEIR corpus archive.
- Demonstrations using MS MARCO or other large corpora.
- Dense retrieval, neural reranking, or training models.
- User accounts, authentication, or multi-user job management.
- Building a custom retrieval engine.
- Calling `GetDocument` when the search results already provide useful document content.
- Requiring deployment on Vercel.

## Users
- IR researchers needing a small live demo of retrieval quality.
- Developers checking Anserini NFCorpus setup and evaluation procedures.
- Demo viewers comparing live search output against measured retrieval metrics.
- Operators deploying benchmark results to Render.

## Core Requirements
- Before constructing commands, use the following repo-local skills:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or find an Anserini fatjar and validate it using the runtime checks from the relevant skill.
- Discover NFCorpus reproduction support through the Anserini reproduction workflow. Where available, use reproduction listing, show, and dry-run behavior to determine NFCorpus commands, expected metrics, qrels/evaluation keys, and setup requirements.
- Do not download all BEIR corpora. Any cache or download step must be specific to NFCorpus and documented in the UI.
- Prefer a prebuilt or cached NFCorpus index, or another NFCorpus-specific artifact, if Anserini exposes one. If no appropriate prebuilt option exists, the application may prepare or build only the NFCorpus index.
- Use actual Anserini commands for setup, search, and evaluation. Do not hardcode or mock search results, run files, qrels, scores, or expected metrics.
- Implement a backend that supports live query search over NFCorpus. This backend may use the Anserini REST server or a CLI-backed search endpoint, but it must use Anserini rather than a custom search implementation.
- Search results must show rank, document id, score, and sufficient document content or snippet text for user inspection.
- Provide a BM25 evaluation workflow for NFCorpus that:
  - runs `SearchCollection` or an equivalent command supplied by the reproduction workflow,
  - writes a TREC-format run file,
  - evaluates with the appropriate Anserini/TrecEval command,
  - parses observed metric values,
  - compares observed values with reproduction-provided expected values when those are available.
- If running evaluation live is too slow for hosted operation, evaluation may be performed during setup/startup, with a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly indicate which results come from cached setup and which come from a fresh rerun.
- Include a readiness panel showing Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether live search and evaluation are ready.
- Display the exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and cached NFCorpus data, if any.
- Surface clear user-visible errors for missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The app must be deployable as a single Docker web service appropriate for Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind HTTP on `0.0.0.0` and read the port from the `PORT` environment variable, defaulting to `10000` when `PORT` is unset.
- Provide a `/health` endpoint returning JSON that includes at least:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The app must not need interactive setup after container startup.
- Keep large generated files out of source control. Runtime caches must reside in a documented cache/data directory. If Render persistent storage is required, document the mount path.
- Keep the default demo small enough for a modest Render service. Avoid downloading all of BEIR, MS MARCO, or heavyweight dense-vector artifacts.

## UX
When the page loads, show a compact diagnostics dashboard containing:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box with several NFCorpus sample queries or topics.
- A ranked results list including ranks, ids, scores, and snippets or document content.
- An evaluation panel with BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer exposing the exact Anserini commands and output previews used to generate the displayed results.

The user must be able to type a query or click a sample NFCorpus query to perform live search. The user must also be able to view the BM25 evaluation status and trigger verification/rerun when the implementation supports it.

## End-to-End Verification
Add a browser test that starts the application and validates the primary workflow.

The test must:
- Open the app.
- Verify that the health/readiness panel is visible.
- Verify that NFCorpus is shown as the active dataset.
- Verify that Anserini setup status is visible.
- Run or choose a live NFCorpus query.
- Verify that ranked search results are displayed with document ids, ranks, scores, and text/snippets.
- Verify that the evaluation panel shows at least one numeric observed metric.
- Verify that expected metric information is displayed when reproduction discovery provides it.
- Verify that an observed-versus-expected comparison status or delta is displayed.
- Verify that exact command text and artifact paths/previews are visible.
- Verify that the Docker/Render readiness contract is documented in the app or README, including `PORT` binding.

The test must fail if the application merely displays mocked search results, mocked evaluation output, or hardcoded metric values without running Anserini-backed setup, search, and evaluation commands.

## Success Criteria
- The app runs locally in Docker and serves HTTP on the configured `PORT`.
- The app can be deployed as a Render Docker web service.
- Users can run live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see an expected-versus-observed metric comparison when expected metrics are discoverable.
- The app avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are visible enough to support debugging.
- The Playwright/browser test passes and demonstrates that the real Anserini workflow is exercised.
