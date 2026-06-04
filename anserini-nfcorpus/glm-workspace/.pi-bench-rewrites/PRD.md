# PRD

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Summary
Create a Docker-containerized web application deployable to Render that provides an interactive diagnostics interface for NFCorpus retrieval using Anserini. The application must leverage the project's Anserini skills to prepare and validate an NFCorpus retrieval environment, execute live searches against NFCorpus, perform or confirm a BM25 evaluation against known target metrics, and surface the precise commands, generated artifacts, and observed-versus-expected results in the browser.

The scope is deliberately limited to NFCorpus so the demonstration can run within the resource constraints of a modest hosted container. Do not generalize this into a BEIR dashboard or download corpora beyond NFCorpus.

## Problem
Anserini supports reproducible retrieval evaluation, but the necessary steps are scattered across skill documentation, CLI discovery, run files, qrels, evaluator output, and deployment considerations. A compact hosted demo is needed that makes a real information-retrieval pipeline transparent: end users should be able to search NFCorpus interactively, see how the dataset was prepared, and verify whether observed evaluation metrics match the expected reproduction targets.

## Goals
- Treat the repo-local Anserini skills as the authoritative reference for environment setup, CLI syntax, reproduction discovery, search, and evaluation.
- Deliver a live web application packaged as a Render-compatible Docker web service.
- Require NFCorpus as the sole dataset.
- Offer live query-based search over NFCorpus powered by an Anserini backend.
- Execute or verify a BM25 evaluation on NFCorpus using actual Anserini commands and qrels.
- Display expected metrics, observed metrics, their differences, the commands executed, and paths to generated artifacts.
- Include browser-based verification that confirms the application is backed by real Anserini execution rather than mocked or hardcoded data.

## Non-Goals
- Support for arbitrary BEIR datasets beyond NFCorpus.
- Downloading the full BEIR corpus archive.
- Demos involving MS MARCO or other large corpora.
- Dense retrieval, neural re-ranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engines unrelated to Anserini.
- Using `GetDocument` when search results already carry sufficient document content.
- Requiring Vercel for deployment.

## Users
- IR researchers seeking a lightweight, live retrieval-quality demonstration.
- Developers validating Anserini NFCorpus setup and evaluation procedures.
- Demo audiences comparing interactive search results with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Core Requirements
- Consult the following repo-local skills before constructing any commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and confirm it passes the skill's runtime verification checks.
- Use the Anserini reproduction workflow to discover what NFCorpus-related reproduction support exists. Where available, use reproduction listing, show, and dry-run behavior to identify the correct NFCorpus commands, expected metric values, qrels/eval keys, and setup prerequisites.
- Do not download all BEIR corpora. Every download or cache step must target NFCorpus exclusively and must be documented in the UI.
- Prefer a prebuilt or cached NFCorpus index or NFCorpus-specific artifact when Anserini exposes one. If no suitable prebuilt path exists, the application may build or prepare only the NFCorpus index itself.
- Use actual Anserini commands for setup, search, and evaluation. Never hardcode or mock search results, run files, qrels, scores, or expected metrics.
- Provide a backend endpoint for live query search over NFCorpus. The backend may use the Anserini REST server or a CLI-backed search endpoint, but must delegate retrieval to Anserini rather than implementing a custom search engine.
- Search results must include rank, document ID, score, and enough document content or snippet text for meaningful inspection.
- Implement a BM25 evaluation workflow for NFCorpus that:
  - runs `SearchCollection` or the reproduction-provided equivalent command,
  - writes a TREC-format run file,
  - evaluates using the appropriate Anserini/TrecEval command,
  - parses the observed metric values,
  - compares observed values against the reproduction-provided expected values when available.
- If live evaluation is too slow for hosted use, the application may run evaluation at setup/startup time and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a freshly triggered rerun.
- Display a readiness panel showing Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and whether the application is ready for live search and evaluation.
- Display the exact command lines used for:
  - fatjar verification,
  - reproduction discovery/dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Surface clear user-visible errors for missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The application must be deployable as a single Docker web service compatible with Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind its HTTP server to `0.0.0.0` and read `PORT` from the environment, defaulting to `10000` when the variable is unset.
- Provide a `/health` endpoint returning JSON with at minimum:
  - application status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The application must not require interactive setup after the container starts.
- Large generated files must be excluded from source control. Runtime caches should reside under a documented cache/data directory. If persistent storage is needed on Render, document the mount path.
- Keep the default demo small enough for a modest Render service instance. Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## UX
On page load, the user is presented with a compact diagnostics dashboard containing:

- A readiness/status panel for Anserini and NFCorpus.
- A live search box accompanied by a few NFCorpus sample queries or topics.
- A ranked result list displaying ranks, IDs, scores, and snippets or document content.
- An evaluation panel presenting BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer that exposes the exact Anserini commands and output previews used to produce the visible results.

The user can type a query or click a sample NFCorpus query to execute a live search. The user can also inspect the BM25 evaluation status and trigger a verification/rerun when the implementation supports it.

## End-to-End Verification
Include a browser test that starts the application and validates the primary workflow.

The test must:
- Open the application.
- Confirm the health/readiness panel is visible.
- Confirm NFCorpus is identified as the active dataset.
- Confirm Anserini setup status is visible.
- Execute or select a live NFCorpus query.
- Confirm ranked search results appear with document IDs, ranks, scores, and text or snippets.
- Confirm the evaluation panel displays at least one numeric observed metric.
- Confirm expected metric information appears when reproduction discovery exposes it.
- Confirm an observed-versus-expected comparison status or delta is visible.
- Confirm exact command text and artifact paths or previews are visible.
- Confirm the Docker/Render readiness contract (including `PORT` binding) is documented in the application or README.

The test must fail if the application only displays mocked search results, mocked evaluation output, or hardcoded metric values without executing Anserini-backed setup/search/evaluation commands.

## Success Criteria
- The application runs locally in Docker and serves HTTP on the configured `PORT`.
- The application can be deployed as a Render Docker web service.
- Users can perform live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see an expected-versus-observed metric comparison when expected metrics are discoverable.
- The application avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to debug.
- The Playwright/browser test passes and confirms that the real Anserini workflow is exercised.
