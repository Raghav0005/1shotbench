# PRD

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Summary
Build a Dockerized, Render-deployable web application for live NFCorpus retrieval diagnostics with Anserini. The app should use Anserini skills to prepare and verify an NFCorpus retrieval environment, run live search over NFCorpus, run or verify a BM25 evaluation with expected metrics, and show the exact commands, artifacts, and observed-vs-expected results in the browser.

This task is intentionally scoped to NFCorpus so the demo can run on a modest hosted container. Do not build a general BEIR dashboard or download all BEIR corpora.

## Problem
Anserini can reproduce and evaluate retrieval baselines, but the workflow is split across skill docs, command-line discovery, run files, qrels, evaluator output, and deployment/runtime concerns. We need a small hosted demo that makes a real IR workflow inspectable: users should be able to search NFCorpus live, understand how the dataset was prepared, and see whether Anserini's observed evaluation metrics match the expected reproduction target.

## Goals
- Use the repo-local Anserini skills as the source of truth for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Build a live web app that can be deployed as a Render Docker web service.
- Use NFCorpus as the only required dataset.
- Provide live query search over NFCorpus through an Anserini-backed backend.
- Run or verify a BM25 NFCorpus evaluation using real Anserini commands and qrels.
- Show expected metrics, observed metrics, deltas, commands, and generated artifact paths.
- Include browser-driven verification that proves the app is not using mocked search or mocked evaluation results.

## Non-Goals
- Supporting all BEIR datasets.
- Downloading the full BEIR corpus archive.
- MS MARCO or other large-corpus demos.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engines.
- Using `GetDocument` when search results already include useful document content.
- Requiring Vercel deployment.

## Users
- IR researchers who want a small live retrieval-quality demo.
- Developers validating Anserini NFCorpus setup and evaluation workflows.
- Demo viewers comparing live search results with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Core Requirements
- Use these repo-local skills before constructing commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and verify it with the skill's runtime checks.
- Discover NFCorpus-related reproduction support using the Anserini reproduction workflow. Use reproduction listing/show/dry-run behavior where available to identify NFCorpus commands, expected metrics, qrels/eval keys, and setup requirements.
- Do not download all BEIR corpora. Any download or cache step must be NFCorpus-specific and must be documented in the UI.
- Prefer a prebuilt/cached NFCorpus index or NFCorpus-specific artifact when Anserini exposes one. If no suitable prebuilt path is available, the app may build or prepare only the NFCorpus index.
- Use real Anserini commands for setup, search, and evaluation. Do not hardcode or mock search results, run files, qrels, scores, or expected metrics.
- Provide a backend that supports live query search over NFCorpus. The backend may use Anserini REST server or a CLI-backed search endpoint, but it must be backed by Anserini rather than a custom search implementation.
- Search results must include rank, document id, score, and enough document content/snippet text for a user to inspect the result.
- Provide a BM25 evaluation workflow for NFCorpus:
  - run `SearchCollection` or the reproduction-provided equivalent command,
  - write a TREC-format run file,
  - evaluate with the appropriate Anserini/TrecEval command,
  - parse observed metric values,
  - compare observed values with the reproduction-provided expected values when available.
- If live evaluation is too slow for hosted use, the app may run evaluation during setup/startup and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a fresh rerun.
- Show a readiness panel with Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether the app is ready for live search and evaluation.
- Show exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Show artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Handle missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures with clear user-visible errors.

## Deployment Requirements
- The app must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind HTTP to `0.0.0.0` and use `PORT` from the environment, defaulting to `10000` when unset.
- Provide a `/health` endpoint that returns JSON with at least:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The app must not require interactive setup after container start.
- Large generated files should be kept out of source control. Runtime caches should live under a documented cache/data directory. If persistent storage is needed on Render, document the mount path.
- Keep the default demo small enough for a modest Render service. Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## UX
On page load, the user sees a compact diagnostics dashboard:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box with a few NFCorpus sample queries or topics.
- A ranked result list with ranks, ids, scores, and snippets/document content.
- An evaluation panel showing BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer that exposes the exact Anserini commands and output previews used to produce the visible results.

The user can type a query or click a sample NFCorpus query to run live search. The user can also inspect the BM25 evaluation status and trigger a verification/rerun when supported by the implementation.

## End-to-End Verification
Include a browser test that starts the app and verifies the main workflow.

The test must:
- Open the app.
- Verify the health/readiness panel appears.
- Verify NFCorpus is identified as the active dataset.
- Verify Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Verify ranked search results appear with document ids, ranks, scores, and text/snippets.
- Verify the evaluation panel displays at least one numeric observed metric.
- Verify expected metric information appears when reproduction discovery exposes it.
- Verify observed-vs-expected comparison status or delta appears.
- Verify exact command text and artifact paths/previews are visible.
- Verify the Docker/Render readiness contract is documented in the app or README, including `PORT` binding.

The test must fail if the app only displays mocked search results, mocked evaluation output, or hardcoded metric values without executing Anserini-backed setup/search/evaluation commands.

## Success Criteria
- The app runs locally in Docker and serves HTTP on the configured `PORT`.
- The app can be deployed as a Render Docker web service.
- Users can run live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see expected-vs-observed metric comparison when expected metrics are discoverable.
- The app avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to debug.
- The Playwright/browser test passes and proves the real Anserini workflow is exercised.
