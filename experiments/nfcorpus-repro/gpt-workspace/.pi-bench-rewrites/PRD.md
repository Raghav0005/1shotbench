# PRD

## Title
Live NFCorpus Retrieval Diagnostics Workbench

## Overview
Create a Dockerized web application that can be deployed to Render and demonstrates live NFCorpus retrieval diagnostics using Anserini. The application must rely on the repo-local Anserini skills to prepare and validate the NFCorpus retrieval environment, perform live NFCorpus search, execute or verify a BM25 evaluation with the expected metric targets, and display in the browser the exact commands, artifacts, and observed-versus-expected outcomes.

The scope is deliberately limited to NFCorpus so the demo can run in a modest hosted container. This is not a general BEIR dashboard and must not download every BEIR corpus.

## Problem Statement
Anserini supports reproducing and evaluating retrieval baselines, but the steps are distributed across skill documentation, command discovery, run files, qrels, evaluator output, and deployment/runtime setup. The goal is a small hosted demo that exposes a real IR workflow: users should be able to run live NFCorpus searches, see how the dataset was prepared, and determine whether observed Anserini evaluation metrics match the expected reproduction target.

## Goals
- Treat the repo-local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Implement a live web application that can run as a Render Docker web service.
- Require only the NFCorpus dataset.
- Support live query search over NFCorpus through a backend backed by Anserini.
- Run or verify a BM25 evaluation for NFCorpus using real Anserini commands and qrels.
- Display expected metrics, observed metrics, deltas, command lines, and generated artifact paths.
- Include browser-driven verification demonstrating that search and evaluation results are not mocked.

## Non-Goals
- Support for all BEIR datasets.
- Downloading the complete BEIR corpus archive.
- Demos for MS MARCO or other large corpora.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engines.
- Use of `GetDocument` when search result output already contains useful document content.
- Requiring deployment on Vercel.

## Intended Users
- IR researchers seeking a compact live retrieval-quality demonstration.
- Developers checking Anserini NFCorpus setup and evaluation workflows.
- Demo viewers comparing live search results with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Functional Requirements
- Before forming commands, use these repo-local skills:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or find an Anserini fatjar and validate it with the runtime checks specified by the relevant skill.
- Use the Anserini reproduction workflow to discover NFCorpus-related reproduction support. Where available, use reproduction listing, show, and dry-run behavior to identify NFCorpus commands, expected metrics, qrels/evaluation keys, and setup requirements.
- Do not download every BEIR corpus. Any download or cache operation must be specific to NFCorpus and described in the UI.
- Prefer a prebuilt/cached NFCorpus index or NFCorpus-specific artifact if Anserini provides one. If no appropriate prebuilt option exists, the app may build or prepare only the NFCorpus index.
- Use actual Anserini commands for setup, search, and evaluation. Search results, run files, qrels, scores, and expected metrics must not be hardcoded or mocked.
- Provide a backend that offers live query search over NFCorpus. This backend may use the Anserini REST server or a CLI-backed search endpoint, but it must be Anserini-backed and not a custom search implementation.
- Search results must show rank, document id, score, and sufficient document content or snippet text for user inspection.
- Provide a BM25 evaluation workflow for NFCorpus that:
  - runs `SearchCollection` or the equivalent command supplied by the reproduction workflow,
  - writes a TREC-format run file,
  - evaluates using the appropriate Anserini/TrecEval command,
  - parses the observed metric values,
  - compares observed values with reproduction-provided expected values when those expected values are available.
- If live evaluation is too slow for hosted operation, evaluation may run during setup/startup and the browser may expose a "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly label cached setup results versus a fresh rerun.
- Include a readiness panel showing Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether live search and evaluation are ready.
- Display the exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Show clear user-visible errors for missing Java, missing fatjar, unsupported Anserini versions, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The app must be deployable as a single Docker web service appropriate for Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind HTTP on `0.0.0.0` and read the port from the `PORT` environment variable, using `10000` by default when `PORT` is unset.
- Provide a `/health` endpoint returning JSON with at least:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The app must not need interactive setup after the container starts.
- Keep large generated files out of source control. Runtime caches must be placed under a documented cache/data directory. If Render persistent storage is required, document the mount path.
- Keep the default demo small enough for a modest Render service. Avoid downloading all BEIR data, MS MARCO data, or heavyweight dense-vector artifacts.

## User Experience
When the page loads, present a compact diagnostics dashboard containing:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box with several NFCorpus sample queries or topics.
- A ranked results list showing ranks, ids, scores, and snippets or document content.
- An evaluation panel with BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer that shows the exact Anserini commands and output previews used to generate the visible data.

Users must be able to type a query or select a sample NFCorpus query to perform live search. Users must also be able to inspect BM25 evaluation status and, when supported by the implementation, trigger a verification/rerun.

## End-to-End Verification
Add a browser test that starts the app and verifies the main workflow.

The test must:
- Open the app.
- Confirm the health/readiness panel is displayed.
- Confirm NFCorpus is shown as the active dataset.
- Confirm Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Confirm ranked search results are displayed with document ids, ranks, scores, and text/snippets.
- Confirm the evaluation panel shows at least one numeric observed metric.
- Confirm expected metric information is displayed when reproduction discovery exposes it.
- Confirm an observed-versus-expected comparison status or delta is displayed.
- Confirm exact command text and artifact paths/previews are visible.
- Confirm the Docker/Render readiness contract is documented in the app or README, including `PORT` binding.

The test must fail if the app presents only mocked search results, mocked evaluation output, or hardcoded metric values without executing Anserini-backed setup/search/evaluation commands.

## Success Criteria
- The app runs locally in Docker and serves HTTP on the configured `PORT`.
- The app can be deployed as a Render Docker web service.
- Browser users can run live NFCorpus search.
- Browser users can inspect real NFCorpus evaluation metrics backed by Anserini.
- Expected-versus-observed metric comparison is visible when expected metrics can be discovered.
- The app avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are sufficiently transparent for debugging.
- The Playwright/browser test passes and verifies that the real Anserini workflow is exercised.
