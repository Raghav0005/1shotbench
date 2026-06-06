# NFCorpus Live Retrieval Diagnostics Workbench — Rewritten PRD

## Overview

Create a containerized web application (Docker + Render-compatible) that provides a live, interactive interface for NFCorpus retrieval diagnostics powered by Anserini. The application should leverage the repository's Anserini skill documents to configure and verify an NFCorpus retrieval environment, execute live searches over the NFCorpus collection, run or validate a BM25 evaluation against expected metrics, and surface all commands, artifacts, and observed-vs-expected comparisons in the browser UI.

The scope is intentionally limited to NFCorpus so the demo remains feasible on a lightweight hosted container. A general-purpose BEIR dashboard or bulk download of all BEIR corpora is explicitly out of scope.

## Problem Statement

Anserini supports reproducible retrieval baselines, but the typical workflow involves juggling skill documentation, CLI discovery, run files, qrels, evaluator output, and deployment concerns. We need a small hosted demo that makes a real IR workflow fully inspectable: users should be able to search NFCorpus in real time, understand how the dataset was prepared, and verify whether Anserini's observed evaluation metrics align with the expected reproduction targets.

## Objectives

- Treat the repo-local Anserini skill documents as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation workflows.
- Deliver a live web application that can be deployed as a Render Docker web service.
- Restrict the required dataset to NFCorpus only.
- Support live query-based search over NFCorpus via an Anserini-backed backend.
- Execute or validate a BM25 NFCorpus evaluation using authentic Anserini commands and qrels.
- Present expected metrics, observed metrics, deltas, the exact commands run, and the paths to generated artifacts.
- Include browser-driven verification that confirms the app is not relying on mocked search or evaluation results.

## Explicit Non-Goals

- Supporting all BEIR datasets.
- Downloading the complete BEIR corpus archive.
- MS MARCO or any large-corpus demonstrations.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job scheduling.
- Custom retrieval engines beyond Anserini.
- Using `GetDocument` when search results already provide sufficient document content.
- Requiring Vercel deployment.

## Target Users

- IR researchers seeking a compact live retrieval-quality demo.
- Developers validating Anserini's NFCorpus setup and evaluation workflows.
- Demo viewers comparing live search results against measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Functional Requirements

### Skill-Driven Setup

- Consult the following repo-local skill documents before constructing any commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and verify it using the runtime checks prescribed by the skill.
- Use the Anserini reproduction workflow to discover NFCorpus-related reproduction support. Employ reproduction listing, show, and dry-run behaviors (where available) to identify NFCorpus commands, expected metrics, qrels/eval keys, and any setup prerequisites.

### Dataset and Index Handling

- Do not download all BEIR corpora. Every download or caching step must be scoped exclusively to NFCorpus and documented in the UI.
- Prefer a prebuilt or cached NFCorpus index (or NFCorpus-specific artifact) when Anserini exposes one. If no suitable prebuilt path exists, the app may build or prepare only the NFCorpus index.

### Authentic Anserini Commands

- Use real Anserini commands for setup, search, and evaluation. Never hardcode or mock search results, run files, qrels, scores, or expected metrics.

### Live Search Backend

- Provide a backend that supports live query search over NFCorpus. The backend may use the Anserini REST server or a CLI-backed search endpoint, but it must be backed by Anserini rather than a custom search implementation.
- Search results must include rank, document id, score, and enough document content or snippet text for a user to meaningfully inspect each result.

### BM25 Evaluation Workflow

- Implement a BM25 evaluation workflow for NFCorpus that:
  - Runs `SearchCollection` or the reproduction-provided equivalent command,
  - Writes a TREC-format run file,
  - Evaluates using the appropriate Anserini/TrecEval command,
  - Parses observed metric values,
  - Compares observed values against the reproduction-provided expected values (when available).
- If live evaluation is too slow for hosted use, the app may run evaluation during setup/startup and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a fresh rerun.

### Readiness and Status Display

- Show a readiness panel that reports: Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether the app is ready for live search and evaluation.
- Display the exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.

### Error Handling

- Handle each of the following failure modes with clear, user-visible errors:
  - Missing Java
  - Missing fatjar
  - Unsupported Anserini version
  - Missing NFCorpus artifacts
  - Command failures
  - Unavailable expected metrics
  - Port conflicts
  - Evaluation failures

## Deployment Requirements

- The app must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile (or equivalent generated project files) in the implementation.
- The container must bind HTTP to `0.0.0.0` and use the `PORT` environment variable, defaulting to `10000` when unset.
- Provide a `/health` endpoint returning JSON that includes at minimum:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The app must not require interactive setup after the container starts.
- Large generated files must be excluded from source control. Runtime caches should reside under a documented cache/data directory. If persistent storage is needed on Render, document the mount path.
- Keep the default demo small enough for a modest Render service. Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## User Experience

On page load, the user should see a compact diagnostics dashboard containing:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box with a few NFCorpus sample queries or topics.
- A ranked result list showing ranks, document ids, scores, and snippets or document content.
- An evaluation panel displaying BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer that exposes the exact Anserini commands and output previews used to produce the visible results.

The user can type a query or click a sample NFCorpus query to trigger live search. The user can also inspect the BM25 evaluation status and trigger a verification or rerun when the implementation supports it.

## End-to-End Verification

Include a browser test that starts the app and verifies the main workflow.

The test must:

- Open the app.
- Verify the health/readiness panel appears.
- Verify NFCorpus is identified as the active dataset.
- Verify Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Verify ranked search results appear with document ids, ranks, scores, and text or snippets.
- Verify the evaluation panel displays at least one numeric observed metric.
- Verify expected metric information appears when reproduction discovery exposes it.
- Verify observed-vs-expected comparison status or delta appears.
- Verify exact command text and artifact paths or previews are visible.
- Verify the Docker/Render readiness contract is documented in the app or README, including `PORT` binding.

The test must fail if the app only displays mocked search results, mocked evaluation output, or hardcoded metric values without executing Anserini-backed setup, search, and evaluation commands.

## Acceptance Criteria

- The app runs locally in Docker and serves HTTP on the configured `PORT`.
- The app can be deployed as a Render Docker web service.
- Users can run live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see expected-vs-observed metric comparison when expected metrics are discoverable.
- The app avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to debug.
- The Playwright/browser test passes and proves the real Anserini workflow is exercised.
