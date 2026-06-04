# Product Requirements Document

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Overview
Deliver a Dockerized web application — deployable as a Render web service — that provides live retrieval diagnostics for NFCorpus using Anserini. The application must lean on the repo-local Anserini skills to prepare and verify the NFCorpus retrieval environment, perform live search over NFCorpus, run or validate a BM25 evaluation against expected metrics, and surface the exact commands, generated artifacts, and observed-vs-expected results inside the browser UI.

The scope is intentionally limited to NFCorpus so the demo can run on a modest hosted container. This is not a general BEIR dashboard, and the implementation must not download every BEIR corpus.

## Motivation
Anserini supports reproducing and evaluating retrieval baselines, but the actual workflow is scattered across skill documentation, CLI discovery, run files, qrels, evaluator output, and deployment concerns. The goal is a small hosted demo that makes a real IR workflow visible end-to-end: the user can search NFCorpus live, understand how the dataset was prepared, and confirm whether Anserini's observed evaluation metrics line up with the expected reproduction target.

## Objectives
- Treat the repo-local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Build a live web app deployable as a Render Docker web service.
- Restrict the dataset to NFCorpus.
- Offer live query search over NFCorpus, served by an Anserini-backed backend.
- Run or verify a real BM25 NFCorpus evaluation using actual Anserini commands and qrels.
- Surface expected metrics, observed metrics, deltas, the exact commands, and generated artifact paths.
- Include browser-driven verification that demonstrates the app is not relying on mocked search or mocked evaluation output.

## Out of Scope
- Supporting all BEIR datasets.
- Downloading the full BEIR corpus archive.
- MS MARCO or any other large-corpus demo.
- Dense retrieval, neural reranking, or model training.
- Accounts, authentication, or multi-user job management.
- Custom (non-Anserini) retrieval engines.
- Using `GetDocument` when search hits already contain useful document content.
- Requiring Vercel for deployment.

## Target Users
- IR researchers wanting a small live retrieval-quality demo.
- Developers validating Anserini's NFCorpus setup and evaluation workflows.
- Demo viewers comparing live search results against measured retrieval metrics.
- Operators deploying benchmark outputs onto Render.

## Functional Requirements

### Skills and Anserini setup
- Consult these repo-local skills before building any commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and verify it using the runtime checks described in the skill.
- Discover NFCorpus-related reproduction support through the Anserini reproduction workflow. Use the reproduction listing/show/dry-run behavior where available to determine NFCorpus commands, expected metrics, qrels/eval keys, and setup requirements.

### Dataset handling
- Do not download all BEIR corpora. Any download or cache step must be scoped to NFCorpus, and the UI must document it.
- Prefer a prebuilt/cached NFCorpus index or other NFCorpus-specific artifact when Anserini exposes one. If no usable prebuilt path exists, the app may build or prepare only the NFCorpus index.

### Real Anserini execution
- Use real Anserini commands for setup, search, and evaluation. Do not hardcode or mock search results, run files, qrels, scores, or expected metrics.

### Live search
- Provide a backend that supports live query search over NFCorpus. It may use the Anserini REST server or a CLI-backed search endpoint, but it must be backed by Anserini rather than a custom search implementation.
- Search results must include rank, document id, score, and enough document content or snippet text for the user to inspect each result.

### BM25 evaluation workflow for NFCorpus
- Run `SearchCollection` or the equivalent command provided by the reproduction workflow.
- Produce a TREC-format run file.
- Evaluate using the appropriate Anserini/TrecEval command.
- Parse the observed metric values.
- Compare observed values with the reproduction-provided expected values when those are available.
- If running evaluation live is too slow for hosted use, the app may execute it during setup or startup and expose a browser "Verify/Rerun" control that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a fresh rerun.

### Readiness, commands, and artifacts
- Display a readiness panel covering Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether the app is ready for live search and evaluation.
- Show the exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Show artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.

### Error handling
- Handle the following with clear, user-visible errors: missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- Ship the application as a single Docker web service suitable for Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind HTTP to `0.0.0.0` and read `PORT` from the environment, defaulting to `10000` when unset.
- Expose a `/health` endpoint returning JSON that includes at least:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The app must not require any interactive setup after the container starts.
- Keep large generated files out of source control. Runtime caches must live under a documented cache/data directory. If Render persistent storage is needed, document the mount path.
- Keep the default demo small enough for a modest Render service. Avoid full BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## UX
When the page loads, the user sees a compact diagnostics dashboard containing:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box with a few NFCorpus sample queries or topics.
- A ranked result list showing ranks, ids, scores, and snippets/document content.
- An evaluation panel showing BM25 metrics: expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer that displays the exact Anserini commands and output previews behind the visible results.

The user can type a query or click a sample NFCorpus query to run live search. The user can also inspect the BM25 evaluation state and, when supported by the implementation, trigger a verification/rerun.

## End-to-End Verification
The implementation must include a browser test that boots the app and exercises the primary workflow.

The test must:
- Open the app.
- Confirm the health/readiness panel is present.
- Confirm NFCorpus is identified as the active dataset.
- Confirm Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Confirm ranked search results appear with document ids, ranks, scores, and text/snippets.
- Confirm the evaluation panel shows at least one numeric observed metric.
- Confirm expected metric information appears whenever reproduction discovery exposes it.
- Confirm an observed-vs-expected comparison status or delta is shown.
- Confirm exact command text and artifact paths/previews are visible.
- Confirm the Docker/Render readiness contract (including `PORT` binding) is documented in the app or README.

The test must fail if the app only renders mocked search results, mocked evaluation output, or hardcoded metric values without actually invoking Anserini-backed setup/search/evaluation commands.

## Success Criteria
- The app runs locally in Docker and serves HTTP on the configured `PORT`.
- The app can be deployed as a Render Docker web service.
- Users can run live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see an expected-vs-observed comparison when expected metrics are discoverable.
- By default, the app avoids full-BEIR and other large-corpus downloads.
- Commands, artifacts, and failure states are transparent enough to debug from the UI.
- The Playwright/browser test passes and demonstrates the real Anserini workflow is executed.
