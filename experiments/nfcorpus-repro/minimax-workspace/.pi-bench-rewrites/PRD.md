# PRD

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Summary
Build a Dockerized web application that is deployable to Render and provides a live diagnostic interface for NFCorpus retrieval using Anserini. The application must rely on the repo-local Anserini skills to prepare and validate an NFCorpus retrieval environment, execute live search against NFCorpus, run or verify a BM25 evaluation against expected metrics, and display the exact commands, generated artifacts, and observed-versus-expected results within the browser.

The scope is intentionally limited to NFCorpus so the demo can run on a modest hosted container. A general BEIR dashboard and full BEIR corpus downloads are out of scope.

## Problem
Anserini can reproduce and evaluate retrieval baselines, but the workflow is fragmented across skill documentation, CLI discovery, run files, qrels, evaluator output, and deployment/runtime configuration. A small hosted demo is needed that makes a real information-retrieval workflow inspectable. Users should be able to search NFCorpus live, see how the dataset was prepared, and confirm whether the observed evaluation metrics produced by Anserini match the expected reproduction target.

## Goals
- Use the repo-local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Build a live web application that can be deployed as a Render Docker web service.
- Use NFCorpus as the only required dataset.
- Provide live query search over NFCorpus through an Anserini-backed backend.
- Run or verify a BM25 NFCorpus evaluation using real Anserini commands and qrels.
- Display expected metrics, observed metrics, deltas, the commands used, and the paths of generated artifacts.
- Include a browser-driven verification step that proves the application is not relying on mocked search results or mocked evaluation results.

## Non-Goals
- Support for all BEIR datasets.
- Downloading the full BEIR corpus archive.
- MS MARCO or other large-corpus demos.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engines not provided by Anserini.
- Use of `GetDocument` when the search response already provides useful document content.
- Vercel deployment as a requirement.

## Users
- Information-retrieval researchers who want a small live retrieval-quality demo.
- Developers validating Anserini's NFCorpus setup and evaluation workflows.
- Demo viewers comparing live search output with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Core Requirements
- Before constructing any commands, consult the following repo-local skills:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and verify it using the runtime checks provided by the `install-anserini-fatjar` skill.
- Use the Anserini reproduction workflow to discover NFCorpus-related reproduction support. Use the reproduction listing, show, and dry-run capabilities where available to identify NFCorpus commands, expected metrics, qrels/eval keys, and setup requirements.
- Do not download the full BEIR corpus set. Any download or cache step must be NFCorpus-specific and must be documented within the UI.
- Prefer a prebuilt or cached NFCorpus index, or a NFCorpus-specific artifact, when Anserini exposes one. If no suitable prebuilt path is available, the application may build or prepare only the NFCorpus index.
- All setup, search, and evaluation must use real Anserini commands. Do not hardcode or mock search results, run files, qrels, scores, or expected metrics.
- Provide a backend that supports live query search over NFCorpus. The backend may use the Anserini REST server or a CLI-backed search endpoint, but it must be backed by Anserini rather than a custom search implementation.
- Search results must include rank, document id, score, and enough document content or snippet text for a user to inspect each result.
- Provide a BM25 evaluation workflow for NFCorpus with the following steps:
  - run `SearchCollection` or the reproduction-provided equivalent command,
  - write a TREC-format run file,
  - evaluate with the appropriate Anserini/TrecEval command,
  - parse the observed metric values from the evaluator output,
  - compare the observed values with the reproduction-provided expected values when those are available.
- If live evaluation is too slow for hosted use, the application may run evaluation during setup or startup and expose a browser "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must clearly distinguish cached setup results from a fresh rerun.
- Display a readiness panel containing:
  - Java and fatjar status,
  - NFCorpus artifact and index status,
  - reproduction discovery status,
  - whether the application is ready for live search and evaluation.
- Display the exact command lines used for:
  - fatjar verification,
  - reproduction discovery or dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Handle the following failure modes with clear user-visible errors: missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The application must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile or equivalent generated project files in the implementation.
- The container must bind HTTP to `0.0.0.0` and must use the `PORT` environment variable, defaulting to `10000` when `PORT` is unset.
- Provide a `/health` endpoint that returns JSON containing at least:
  - app status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The application must not require interactive setup after container start.
- Large generated files must be excluded from source control. Runtime caches must live under a documented cache or data directory. If persistent storage is needed on Render, document the mount path.
- Keep the default demo small enough for a modest Render service. Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## UX
On page load, the user must see a compact diagnostics dashboard containing:

- A readiness and status panel for Anserini and NFCorpus.
- A live search box with a few NFCorpus sample queries or topics.
- A ranked result list with ranks, ids, scores, and document content or snippets.
- An evaluation panel showing BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command and artifact drawer that exposes the exact Anserini commands and output previews used to produce the visible results.

The user must be able to type a query or click a sample NFCorpus query to run live search. The user must also be able to inspect the BM25 evaluation status and trigger a verification or rerun when the implementation supports it.

## End-to-End Verification
Include a browser test that starts the application and verifies the main workflow.

The test must:
- Open the application.
- Verify that the health or readiness panel appears.
- Verify that NFCorpus is identified as the active dataset.
- Verify that Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Verify that ranked search results appear with document ids, ranks, scores, and text or snippets.
- Verify that the evaluation panel displays at least one numeric observed metric.
- Verify that expected metric information appears when reproduction discovery exposes it.
- Verify that the observed-versus-expected comparison status or delta appears.
- Verify that exact command text and artifact paths or previews are visible.
- Verify that the Docker and Render readiness contract is documented in the application or README, including `PORT` binding.

The test must fail if the application only displays mocked search results, mocked evaluation output, or hardcoded metric values without executing Anserini-backed setup, search, and evaluation commands.

## Success Criteria
- The application runs locally in Docker and serves HTTP on the configured `PORT`.
- The application can be deployed as a Render Docker web service.
- Users can run live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can see an expected-versus-observed metric comparison when expected metrics are discoverable.
- The application avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to debug.
- The Playwright or browser test passes and proves that the real Anserini workflow is exercised.
