# Product Requirements Document

## Project Name
NFCorpus Live Retrieval Diagnostics Workbench

## Overview
Create a Docker-packaged web application, deployable on Render, that provides live NFCorpus retrieval diagnostics powered by Anserini. The application must use Anserini skills to set up and validate an NFCorpus retrieval environment, execute live search queries against NFCorpus, perform or confirm a BM25 evaluation run with known target metrics, and surface all commands, data artifacts, and observed-versus-expected metric comparisons in the browser.

Scope is deliberately limited to NFCorpus so the demo fits within a small hosted container. This is not a general BEIR dashboard, and it must not download the entire BEIR corpus collection.

## Motivation
Anserini supports reproducible retrieval baselines, but the process spans multiple skill documents, CLI exploration, run-file generation, qrels files, evaluator output, and deployment considerations. A small hosted demo is needed that makes an actual IR pipeline inspectable: users should search NFCorpus interactively, understand how the dataset was prepared, and confirm whether Anserini's measured evaluation metrics align with published reproduction targets.

## Objectives
- Treat the repo-local Anserini skills as the authoritative reference for environment setup, CLI syntax, reproduction discovery, search, and evaluation.
- Deliver a live web application packaged as a Render-compatible Docker web service.
- Support NFCorpus as the sole required dataset.
- Offer live query-based search over NFCorpus via an Anserini-backed backend.
- Execute or verify a BM25 NFCorpus evaluation using actual Anserini commands and qrels.
- Display expected metrics, observed metrics, differences between them, commands used, and paths of generated artifacts.
- Include browser-based verification demonstrating that the application runs real Anserini commands rather than returning mocked search or evaluation data.

## Out of Scope
- Support for any BEIR datasets beyond NFCorpus.
- Downloading the full BEIR corpus archive.
- MS MARCO or other large-corpus demonstrations.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engine implementations.
- Using `GetDocument` when search results already include usable document content.
- Requiring Vercel deployment.

## Target Users
- IR researchers wanting a small, live retrieval-quality demonstration.
- Developers validating Anserini NFCorpus setup and evaluation workflows.
- Demo viewers comparing interactive search results with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Functional Requirements

### Skill-Driven Setup
- Consult the following repo-local skills before constructing any commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and pass the skill's runtime verification checks.

### Reproduction Discovery
- Use the Anserini reproduction workflow to discover NFCorpus-related reproduction support. Leverage reproduction listing, show, and dry-run capabilities (where available) to identify the NFCorpus commands, expected metrics, qrels/eval keys, and setup requirements.

### Dataset Constraints
- Do not download all BEIR corpora. Every download or cache step must target NFCorpus exclusively and must be documented in the UI.
- Prefer a prebuilt or cached NFCorpus index or NFCorpus-specific artifact when Anserini provides one. If no suitable prebuilt path exists, the application may build or prepare only the NFCorpus index itself.

### Real Anserini Commands
- Use actual Anserini commands for all setup, search, and evaluation operations. Never hardcode or mock search results, run files, qrels, scores, or expected metrics.

### Live Search
- Provide a backend supporting live query search over NFCorpus. The backend may use the Anserini REST server or a CLI-backed search endpoint, but it must be powered by Anserini—not a custom search implementation.
- Each search result must include rank, document ID, score, and sufficient document content or snippet text for inspection.

### BM25 Evaluation Pipeline
- Implement a BM25 evaluation workflow for NFCorpus consisting of:
  1. Running `SearchCollection` or the reproduction-provided equivalent command.
  2. Writing a TREC-format run file.
  3. Evaluating with the appropriate Anserini/TrecEval command.
  4. Parsing the observed metric values.
  5. Comparing observed values against reproduction-provided expected values when available.
- If live evaluation is too slow for hosted use, the application may run evaluation during setup/startup and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a fresh rerun.

### Readiness Panel
- Display a readiness panel reporting: Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether the application is ready for live search and evaluation.

### Command Transparency
- Show the exact command lines used for:
  - fatjar verification
  - reproduction discovery/dry-run
  - NFCorpus search setup
  - BM25 retrieval
  - evaluation

### Artifact Visibility
- Show paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.

### Error Handling
- Handle the following conditions with clear user-visible errors: missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The application must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile (or equivalent generated project files) in the implementation.
- The container must bind its HTTP server to `0.0.0.0` and read the port from the `PORT` environment variable, defaulting to `10000` when `PORT` is unset.
- Provide a `/health` endpoint returning JSON with at minimum:
  - app status
  - Anserini availability
  - NFCorpus readiness
  - whether search is available
  - whether evaluation is available
- The application must not require interactive setup after the container starts.
- Large generated files must be excluded from source control. Runtime caches should reside under a documented cache/data directory. If persistent storage is needed on Render, document the mount path.
- Keep the default demo small enough to run on a modest Render service. Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## User Interface Layout
On page load, present a compact diagnostics dashboard containing:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box accompanied by a few NFCorpus sample queries or topics.
- A ranked result list displaying ranks, document IDs, scores, and snippets/document content.
- An evaluation panel showing BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer exposing the exact Anserini commands and output previews used to produce the visible results.

The user can type a query or click a sample NFCorpus query to execute live search. The user can also inspect the BM25 evaluation status and trigger a verification/rerun action when the implementation supports it.

## End-to-End Browser Test
Include a browser test that starts the application and validates the primary workflow.

The test must:
- Open the application.
- Confirm the health/readiness panel is visible.
- Confirm NFCorpus is identified as the active dataset.
- Confirm Anserini setup status is visible.
- Execute or select a live NFCorpus query.
- Confirm ranked search results appear with document IDs, ranks, scores, and text/snippets.
- Confirm the evaluation panel shows at least one numeric observed metric.
- Confirm expected metric information appears when reproduction discovery exposes it.
- Confirm an observed-versus-expected comparison status or delta is displayed.
- Confirm exact command text and artifact paths or previews are visible.
- Confirm the Docker/Render readiness contract is documented in the app or README, including `PORT` binding.

The test must fail if the application displays only mocked search results, mocked evaluation output, or hardcoded metric values without actually executing Anserini-backed setup, search, and evaluation commands.

## Acceptance Criteria
- The application runs locally in Docker and serves HTTP on the configured `PORT`.
- The application is deployable as a Render Docker web service.
- Users can execute live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see expected-versus-observed metric comparisons when expected metrics are discoverable.
- The application avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to support debugging.
- The Playwright/browser test passes and confirms that the real Anserini workflow is exercised.
