# PRD (Restated)

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Summary
Produce a Docker-based web application, suitable for Render deployment, that delivers live retrieval diagnostics for the NFCorpus benchmark using Anserini. The app must leverage the repo-local Anserini skill files (`install-anserini-fatjar`, `anserini-cli`, `anserini-reproduction`) to set up and confirm an NFCorpus retrieval environment, serve live search over NFCorpus, execute or verify a BM25 evaluation against known expected metrics, and expose the exact commands, generated artifacts, and observed-vs-expected metric comparisons in the browser.

The scope is deliberately restricted to NFCorpus so the demo can fit within a modest hosted container. Do not construct a general BEIR dashboard or attempt to download all BEIR corpora.

## Problem
Anserini is capable of reproducing and evaluating retrieval baselines, but the full workflow is distributed across skill documentation, command-line discovery, run files, qrels, evaluator output, and deployment/runtime concerns. The goal is a compact hosted demo that makes a real IR workflow inspectable: users should be able to search NFCorpus live, understand the steps used to prepare the dataset, and verify whether Anserini's observed evaluation metrics align with the expected reproduction numbers.

## Goals
- Treat the repo-local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation steps.
- Build a live web application deployable as a Render Docker web service.
- Use NFCorpus as the sole required dataset.
- Provide live query search over NFCorpus via an Anserini-powered backend.
- Run or verify a BM25 NFCorpus evaluation using real Anserini commands and qrels.
- Display expected metrics, observed metrics, deltas, the commands executed, and paths to generated artifacts.
- Include a browser-driven end-to-end verification that proves the app is not relying on mocked search or mocked evaluation results.

## Non-Goals
- Supporting all BEIR datasets.
- Downloading the full BEIR corpus archive.
- MS MARCO or other large-corpus demonstrations.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engines.
- Using `GetDocument` when search results already contain useful document content.
- Requiring Vercel deployment.

## Users
- IR researchers evaluating a small live retrieval-quality demo.
- Developers validating Anserini NFCorpus setup and evaluation workflows.
- Demo viewers comparing live search results with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Core Requirements
- Before constructing any commands, consult these repo-local skills:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and confirm it passes the skill's runtime checks.
- Discover NFCorpus-related reproduction support through the Anserini reproduction workflow. Where available, use reproduction listing, show, or dry-run behavior to identify NFCorpus commands, expected metrics, qrels/eval keys, and setup requirements.
- Do not download all BEIR corpora. Any download or cache step must be NFCorpus-specific and must be documented in the UI.
- Prefer a prebuilt or cached NFCorpus index, or an NFCorpus-specific artifact, when Anserini exposes one. If no suitable prebuilt path is available, the app may build or prepare only the NFCorpus index.
- Use real Anserini commands for setup, search, and evaluation. Do not hardcode or mock search results, run files, qrels, scores, or expected metrics.
- Provide a backend that supports live query search over NFCorpus. The backend may use the Anserini REST server or a CLI-backed search endpoint, but it must be backed by Anserini rather than a custom search implementation.
- Search results must include rank, document id, score, and enough document content or snippet text for a user to inspect the result.
- Provide a BM25 evaluation workflow for NFCorpus:
  - run `SearchCollection` or the equivalent command surfaced by the reproduction workflow,
  - write a TREC-format run file,
  - evaluate with the appropriate Anserini/TrecEval command,
  - parse observed metric values,
  - compare observed values with the expected values provided by the reproduction workflow when available.
- If live evaluation is too slow for hosted use, the app may run evaluation during setup/startup and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a fresh rerun.
- Show a readiness panel with Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether the app is ready for live search and evaluation.
- Show exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Show artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Handle these error conditions with clear user-visible errors: missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The app must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind HTTP to `0.0.0.0` and read the `PORT` environment variable, defaulting to `10000` when `PORT` is unset.
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
- A ranked result list with ranks, ids, scores, and snippets or document content.
- An evaluation panel showing BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer that exposes the exact Anserini commands and output previews used to produce the visible results.

The user can type a query or click a sample NFCorpus query to run live search. The user can also inspect the BM25 evaluation status and trigger a verification or rerun when supported by the implementation.

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
