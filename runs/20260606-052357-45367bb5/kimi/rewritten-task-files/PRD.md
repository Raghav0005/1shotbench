# Product Requirements Document

## Title
NFCorpus Live Retrieval Diagnostics Workbench

## Overview
Create a containerized web application—deployable as a Docker service on Render—that delivers live NFCorpus retrieval diagnostics powered by Anserini. The application must rely on the repository’s local Anserini skills to prepare and validate an NFCorpus retrieval environment, execute live searches against NFCorpus, perform or validate a BM25 evaluation against known metrics, and surface the precise commands, artifacts, and observed-versus-expected outcomes directly in the browser.

This work is deliberately confined to NFCorpus so the demonstration can operate within a modest hosted container. Do not implement a general-purpose BEIR dashboard or fetch the entire collection of BEIR corpora.

## Problem Statement
Anserini is capable of reproducing and evaluating retrieval baselines, yet the overall workflow is fragmented across skill documentation, command-line invocation, run files, qrels, evaluator output, and runtime or deployment considerations. A small, hosted demonstration is needed to make a genuine information-retrieval workflow transparent and inspectable: users should be able to search NFCorpus in real time, understand how the dataset was prepared, and confirm whether Anserini’s measured evaluation metrics align with the expected reproduction targets.

## Objectives
- Treat the repository’s local Anserini skills as the authoritative source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Deliver a live web application that can be deployed as a Render Docker web service.
- Restrict the required dataset to NFCorpus alone.
- Support live query search over NFCorpus through an Anserini-backed backend.
- Execute or verify a BM25 evaluation for NFCorpus using actual Anserini commands and qrels.
- Display expected metrics, observed metrics, deltas, the commands that produced them, and the paths to generated artifacts.
- Incorporate browser-driven verification that demonstrates the application is not relying on mocked search results or mocked evaluation output.

## Out of Scope
- Supporting any BEIR datasets beyond NFCorpus.
- Downloading the complete BEIR corpus archive.
- MS MARCO or other large-corpus demonstrations.
- Dense retrieval, neural reranking, or model training.
- User accounts, authentication, or multi-user job orchestration.
- Custom retrieval engines.
- Using `GetDocument` when search results already contain sufficient document content.
- Mandating deployment on Vercel.

## Intended Audience
- Information-retrieval researchers seeking a compact, live demonstration of retrieval quality.
- Developers who need to validate Anserini NFCorpus setup and evaluation workflows.
- Demonstration viewers comparing live search results against quantified retrieval metrics.
- Operators who will deploy benchmark outputs to Render.

## Functional Requirements
- Before constructing any commands, consult these repository-local skills:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and confirm it using the runtime checks defined by the corresponding skill.
- Identify NFCorpus-related reproduction support through the Anserini reproduction workflow. Leverage reproduction listing, show, or dry-run capabilities—where they exist—to determine the exact NFCorpus commands, expected metrics, qrels and evaluation keys, and setup prerequisites.
- Do not download all BEIR corpora. Any download or caching operation must be limited to NFCorpus and must be disclosed in the user interface.
- Favor a prebuilt or cached NFCorpus index, or any NFCorpus-specific artifact that Anserini provides. If no suitable prebuilt path exists, the application may build or prepare only the NFCorpus index.
- Use genuine Anserini commands for setup, search, and evaluation. Do not hardcode or fabricate search results, run files, qrels, scores, or expected metrics.
- Supply a backend that enables live query search over NFCorpus. The backend may use the Anserini REST server or a CLI-backed search endpoint, but it must be driven by Anserini rather than a custom search implementation.
- Search results must contain the rank, document identifier, score, and enough document content or snippet text for a user to examine the result.
- Implement a BM25 evaluation workflow for NFCorpus:
  - Invoke `SearchCollection` or the equivalent command provided by the reproduction workflow.
  - Write a TREC-format run file.
  - Evaluate using the appropriate Anserini or TrecEval command.
  - Extract the observed metric values.
  - Compare the observed values against the expected values supplied by reproduction discovery, when such values are available.
- If live evaluation is too slow for a hosted environment, the application may perform evaluation during setup or startup and expose a browser action labeled “Verify” or “Rerun” that reuses cached NFCorpus artifacts. The user interface must clearly differentiate cached setup results from a freshly executed rerun.
- Present a readiness panel that reports:
  - Java and fatjar status,
  - NFCorpus artifact and index status,
  - reproduction discovery status,
  - whether the application is prepared for live search and evaluation.
- Expose the exact command lines used for:
  - fatjar verification,
  - reproduction discovery or dry-run,
  - NFCorpus search setup,
  - BM25 retrieval,
  - evaluation.
- Display artifact paths for generated run files, evaluation output, setup logs, and any cached NFCorpus data.
- Surface clear, user-visible errors for conditions such as missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The application must be deployable as a single Docker web service appropriate for Render.
- Include a Dockerfile—or equivalent generated project files—in the implementation.
- The container must bind HTTP to `0.0.0.0` and read the `PORT` environment variable, defaulting to `10000` when the variable is not set.
- Expose a `/health` endpoint that returns JSON containing at least:
  - overall application status,
  - Anserini availability,
  - NFCorpus readiness,
  - whether search is available,
  - whether evaluation is available.
- The application must not require interactive setup after the container starts.
- Keep large generated files out of source control. Runtime caches must reside under a documented cache or data directory. If persistent storage is necessary on Render, document the intended mount path.
- Keep the default demonstration small enough to run on a modest Render service. Avoid whole-BEIR downloads, MS MARCO downloads, and heavyweight dense-vector artifacts.

## User Experience
When the page loads, the user should see a concise diagnostics dashboard containing:
- A readiness or status panel for Anserini and NFCorpus.
- A live search field accompanied by a handful of sample NFCorpus queries or topics.
- A ranked results list showing ranks, identifiers, scores, and snippets or document content.
- An evaluation panel that presents BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command and artifact drawer that reveals the exact Anserini commands and output previews that produced the visible results.

The user may type a query or select a sample NFCorpus query to execute live search. The user may also inspect the BM25 evaluation status and initiate a verification or rerun when the implementation supports it.

## End-to-End Verification
Include a browser test that launches the application and validates the primary workflow.

The test is required to:
- Open the application.
- Confirm that the health or readiness panel is visible.
- Confirm that NFCorpus is labeled as the active dataset.
- Confirm that Anserini setup status is visible.
- Execute or select a live NFCorpus query.
- Confirm that ranked search results appear, including document identifiers, ranks, scores, and text or snippets.
- Confirm that the evaluation panel shows at least one numeric observed metric.
- Confirm that expected metric information appears when reproduction discovery makes it available.
- Confirm that an observed-versus-expected comparison status or delta appears.
- Confirm that exact command text and artifact paths or previews are visible.
- Confirm that the Docker and Render readiness contract is documented within the application or the README, including the `PORT` binding behavior.

The test must fail if the application displays mocked search results, mocked evaluation output, or hardcoded metric values without actually executing Anserini-backed setup, search, or evaluation commands.

## Success Criteria
- The application runs locally inside Docker and serves HTTP on the configured `PORT`.
- The application can be deployed as a Render Docker web service.
- Users can perform live NFCorpus search from the browser.
- Users can inspect real Anserini-backed NFCorpus evaluation metrics.
- Users can view an expected-versus-observed metric comparison whenever expected metrics are discoverable.
- The application avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to support debugging.
- The Playwright or browser test passes and proves that a genuine Anserini workflow is being exercised.
