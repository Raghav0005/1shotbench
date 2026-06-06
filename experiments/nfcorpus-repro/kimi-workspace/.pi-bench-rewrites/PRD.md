# PRD

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Overview
Create a containerized web application deployable to Render as a Docker web service. The application must perform live NFCorpus retrieval diagnostics using Anserini, leverage the repository's local skill files to prepare and validate the retrieval environment, execute real-time search against NFCorpus, perform or validate a BM25 evaluation with measured metrics, and present the precise commands, generated artifacts, and side-by-side observed versus expected results in the browser.

This scope is intentionally limited to NFCorpus so the demonstration remains feasible on a modest hosted container. Do not implement a general BEIR dashboard or fetch the entire BEIR corpora collection.

## Motivation
Anserini supports reproducing and evaluating retrieval baselines, yet the process is distributed across skill documentation, command-line exploration, run files, qrels, evaluator output, and runtime or deployment considerations. The objective is a compact hosted demonstration that exposes a genuine IR workflow: users must be able to search NFCorpus live, understand how the dataset was prepared, and confirm whether Anserini's measured evaluation metrics align with the expected reproduction benchmark.

## Objectives
- Rely on the repository-local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Deliver a live web application capable of deployment as a Render Docker web service.
- Restrict the required dataset to NFCorpus exclusively.
- Expose live query search over NFCorpus through an Anserini-driven backend.
- Execute or verify a BM25 NFCorpus evaluation using genuine Anserini commands and qrels.
- Display expected metrics, measured metrics, deltas, commands, and artifact paths.
- Incorporate browser-driven verification demonstrating that the application does not rely on simulated search or fabricated evaluation results.

## Out of Scope
- Supporting additional BEIR datasets.
- Retrieving the complete BEIR corpus archive.
- MS MARCO or other large-corpus demonstrations.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job management.
- Custom retrieval engines separate from Anserini.
- Using `GetDocument` when search results already contain sufficient document content.
- Mandating Vercel deployment.

## Intended Audience
- IR researchers seeking a compact live retrieval-quality demonstration.
- Developers validating Anserini NFCorpus setup and evaluation workflows.
- Demonstration viewers comparing live search results against quantified retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Functional Requirements
- Consult the following repository-local skills before building any commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and confirm it using the runtime checks defined in the corresponding skill.
- Identify NFCorpus-related reproduction support through the Anserini reproduction workflow. Leverage reproduction listing, show, and dry-run capabilities where available to determine the NFCorpus commands, expected metrics, qrels/eval keys, and setup prerequisites.
- Do not download the full BEIR corpora. Any download or caching operation must be NFCorpus-specific and must be disclosed in the UI.
- Favor a prebuilt or cached NFCorpus index or NFCorpus-specific artifact if Anserini provides one. If no appropriate prebuilt path exists, the application may construct or prepare only the NFCorpus index.
- Use authentic Anserini commands for setup, search, and evaluation. Do not hardcode or simulate search results, run files, qrels, scores, or expected metrics.
- Provide a backend capable of live query search over NFCorpus. The backend may utilize the Anserini REST server or a CLI-backed search endpoint, but it must be driven by Anserini rather than a bespoke search implementation.
- Search results must present rank, document identifier, score, and adequate document content or snippet text for user inspection.
- Implement a BM25 evaluation workflow for NFCorpus:
  - Execute `SearchCollection` or the equivalent command supplied by the reproduction workflow.
  - Produce a TREC-format run file.
  - Evaluate using the appropriate Anserini/TrecEval command.
  - Extract the observed metric values.
  - Compare the observed values against the expected values provided by the reproduction workflow when they are available.
- If live evaluation is prohibitively slow for a hosted environment, the application may execute evaluation during setup or startup and expose a browser-based "Verify/Rerun" action that reuses cached NFCorpus artifacts. The UI must unambiguously differentiate cached setup results from a fresh rerun.
- Render a readiness panel indicating Java/fatjar status, NFCorpus artifact/index status, reproduction discovery status, and overall readiness for live search and evaluation.
- Display the exact command lines used for:
  - fatjar verification,
  - reproduction discovery or dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Surface clear user-visible errors when Java is missing, the fatjar is missing, the Anserini version is unsupported, NFCorpus artifacts are absent, commands fail, expected metrics are unavailable, ports conflict, or evaluation fails.

## Deployment Requirements
- The application must be deployable as a single Docker web service compatible with Render.
- Include a Dockerfile or equivalent generated project files in the deliverable.
- The container must listen for HTTP on `0.0.0.0` and read the `PORT` environment variable, falling back to `10000` when the variable is unset.
- Expose a `/health` endpoint returning JSON containing at least:
  - application status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The application must not require interactive setup after the container starts.
- Large generated files must remain outside source control. Runtime caches must reside within a documented cache or data directory. If persistent storage is necessary on Render, document the mount path.
- Keep the default demonstration lightweight enough for a modest Render service. Avoid full-BEIR downloads, MS MARCO downloads, and heavy dense-vector artifacts.

## User Experience
When the page loads, the user encounters a concise diagnostics dashboard containing:

- A readiness or status panel for Anserini and NFCorpus.
- A live search input with a selection of NFCorpus sample queries or topics.
- A ranked results list showing ranks, identifiers, scores, and document snippets or content.
- An evaluation panel presenting BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command and artifact drawer revealing the exact Anserini commands and output previews that produced the visible results.

The user may type a query or select a sample NFCorpus query to execute live search. The user may also inspect the BM25 evaluation status and initiate a verification or rerun when supported.

## End-to-End Verification
Include a browser test that launches the application and validates the primary workflow.

The test must:
- Open the application.
- Confirm the health or readiness panel is visible.
- Confirm NFCorpus is labeled as the active dataset.
- Confirm Anserini setup status is visible.
- Execute or select a live NFCorpus query.
- Confirm ranked search results appear containing document identifiers, ranks, scores, and text or snippets.
- Confirm the evaluation panel shows at least one numeric observed metric.
- Confirm expected metric information appears when reproduction discovery exposes it.
- Confirm an observed-versus-expected comparison status or delta appears.
- Confirm exact command text and artifact paths or previews are visible.
- Confirm the Docker and Render readiness contract is documented within the application or README, including the `PORT` binding behavior.

The test must fail if the application displays only simulated search results, fabricated evaluation output, or hardcoded metric values without executing Anserini-backed setup, search, or evaluation commands.

## Success Criteria
- The application runs locally in Docker and serves HTTP on the configured `PORT`.
- The application can be deployed as a Render Docker web service.
- Users can execute live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can view an expected-versus-observed metric comparison when expected metrics are discoverable.
- The application avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to support debugging.
- The Playwright or browser test passes and demonstrates that the real Anserini workflow is exercised.
