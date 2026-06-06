# PRD (Rewritten)

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Overview
Implement a Docker-based, Render-deployable web application that surfaces live retrieval diagnostics over NFCorpus using Anserini. The implementation must rely on the repo-local Anserini skills to set up and verify the retrieval environment, perform live search on NFCorpus, run (or verify) a BM25 evaluation against expected metrics, and surface the actual commands executed, the produced artifacts, and the observed-vs-expected results inside the browser UI.

The scope is deliberately restricted to NFCorpus so that the demo fits a modest hosted container. This is not a general BEIR dashboard, and no full BEIR corpus download is allowed.

## Motivation
Anserini supports reproducing and evaluating retrieval baselines, but the full path (skill docs, CLI discovery, run files, qrels, evaluator output, deployment/runtime concerns) is fragmented. The goal is a small hosted demo that makes a genuine IR workflow inspectable: a user can issue live NFCorpus queries, see how the dataset was prepared, and check whether the observed Anserini evaluation metrics line up with the published reproduction target.

## Goals
- Treat the repo-local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Ship a live web app deployable as a Render Docker web service.
- Require only NFCorpus as a dataset.
- Offer live NFCorpus search via an Anserini-backed backend.
- Either execute or verify a BM25 NFCorpus evaluation using real Anserini commands and qrels.
- Surface expected metrics, observed metrics, deltas, command lines, and produced artifact paths.
- Provide an automated browser-driven verification confirming that search and evaluation are not mocked.

## Out of Scope
- Coverage of all BEIR datasets.
- Downloading the full BEIR corpus archive.
- Demos based on MS MARCO or other large corpora.
- Dense retrieval, neural rerankers, or any model training.
- Authentication, user accounts, or multi-user job orchestration.
- Custom retrieval engines (Anserini must back the search/eval).
- Using `GetDocument` if the search response already provides usable document content.
- Vercel deployment is not required.

## Target Users
- IR researchers wanting a compact live retrieval-quality demo.
- Developers validating NFCorpus setup and the evaluation workflow with Anserini.
- Demo viewers correlating live search results with measured retrieval metrics.
- Operators publishing benchmark outputs on Render.

## Functional Requirements

### Skill Usage
Before any command construction, consult these repo-local skills:
- `install-anserini-fatjar`
- `anserini-cli`
- `anserini-reproduction`

### Anserini Environment
- Install or locate an Anserini fatjar and verify it via the runtime checks defined by the skill.
- Use the Anserini reproduction workflow to discover NFCorpus-related reproduction support. Use the available listing/show/dry-run behavior to determine NFCorpus commands, expected metrics, qrels/eval keys, and any setup prerequisites.

### Dataset Handling
- Do not download all BEIR corpora. Any download/cache action must be NFCorpus-only and must be documented inside the UI.
- Prefer a prebuilt/cached NFCorpus index or NFCorpus-specific artifact when Anserini exposes one. If no suitable prebuilt option exists, the app is allowed to build or prepare only the NFCorpus index.

### Authenticity
- All setup, search, and evaluation must go through real Anserini commands. Search results, run files, qrels, scores, and expected metrics must not be mocked or hardcoded.

### Search Backend
- Provide a backend that supports live NFCorpus query search. It may use the Anserini REST server or a CLI-backed search endpoint, but the search itself must be backed by Anserini (not a custom implementation).
- Each search result must include: rank, document id, score, and enough document content/snippet text for inspection.

### BM25 Evaluation Workflow
Provide a BM25 evaluation pipeline for NFCorpus that:
- runs `SearchCollection` or the reproduction-provided equivalent,
- writes a TREC-format run file,
- evaluates it with the appropriate Anserini/TrecEval command,
- parses observed metric values, and
- compares observed values with the reproduction-provided expected values when those are available.

If running evaluation live is too slow for the hosted environment, the app may run evaluation during setup/startup and offer a browser-triggered "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly indicate when results come from cached setup vs. a fresh rerun.

### Diagnostics UI Content
- A readiness panel covering: Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and overall readiness for live search and evaluation.
- Exact command lines for: fatjar verification, reproduction discovery/dry-run, NFCorpus search setup, BM25 retrieval, and evaluation.
- Artifact paths for: generated run files, evaluation output, setup logs, and any cached NFCorpus data.

### Error Handling
Surface clear, user-visible errors for: missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The app must deploy as a single Docker web service compatible with Render.
- Include a Dockerfile (or equivalent generated project files) in the implementation.
- The container must bind HTTP on `0.0.0.0`, read the port from the `PORT` environment variable, and default to `10000` when `PORT` is unset.
- Expose a `/health` endpoint returning JSON containing at least:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- No interactive setup may be required after container start.
- Keep large generated files out of source control. Runtime caches must live under a documented cache/data directory; if persistent storage on Render is required, document the mount path.
- Keep the default demo small enough for a modest Render plan: avoid full-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## UX Layout
On initial page load, the user lands on a compact diagnostics dashboard containing:
- A readiness/status panel for Anserini and NFCorpus.
- A live search box plus a few NFCorpus sample queries or topics.
- A ranked result list including ranks, document ids, scores, and snippets/document content.
- An evaluation panel that shows: BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer exposing the exact Anserini commands and output previews tied to the visible results.

User interactions:
- Type a query or click a sample NFCorpus query to run live search.
- Inspect the BM25 evaluation status and, when supported by the implementation, trigger a verification/rerun.

## End-to-End Browser Verification
Provide a browser test that boots the app and walks the main workflow. The test must:
- Open the application.
- Confirm the health/readiness panel renders.
- Confirm NFCorpus is shown as the active dataset.
- Confirm the Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Confirm ranked search results appear with document ids, ranks, scores, and text/snippets.
- Confirm the evaluation panel displays at least one numeric observed metric.
- Confirm expected metric information appears when reproduction discovery exposes it.
- Confirm an observed-vs-expected comparison status or delta is shown.
- Confirm exact command text and artifact paths/previews are visible.
- Confirm the Docker/Render readiness contract, including `PORT` binding, is documented either in the app UI or the README.

The test must fail when the app merely renders mocked search results, mocked evaluation output, or hardcoded metric values without exercising Anserini-backed setup/search/evaluation commands.

## Success Criteria
- The app runs locally in Docker and serves HTTP on the configured `PORT`.
- The app can be deployed as a Render Docker web service.
- Live NFCorpus search is usable from the browser.
- Real Anserini-backed NFCorpus evaluation metrics are inspectable.
- An expected-vs-observed metric comparison is shown when expected metrics are discoverable.
- The default behavior avoids full-BEIR and other large-corpus downloads.
- Command lines, artifacts, and failure states are transparent enough for debugging.
- The Playwright/browser test passes and demonstrates that the actual Anserini workflow is exercised.
