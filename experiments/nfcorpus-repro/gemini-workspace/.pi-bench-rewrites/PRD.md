# PRD: NFCorpus Live Retrieval Diagnostics Workbench

## Summary
Develop a containerized web application suitable for deployment on Render. It will act as a live retrieval diagnostic tool for NFCorpus using Anserini. The application must leverage specific Anserini skills to set up and validate the retrieval environment, conduct live searches against NFCorpus, execute or verify BM25 evaluation against expected metrics, and display exact commands, artifacts, and observed-vs-expected results in the user interface.

Scope is strictly limited to NFCorpus to ensure it can run on modest hosted containers. Do not build a general BEIR dashboard or download all BEIR corpora.

## Problem Statement
The Anserini workflow for reproducing and evaluating retrieval baselines is distributed across skill docs, CLI discovery, run files, qrels, evaluator outputs, and deployment concerns. A self-contained, hosted demonstration is needed to make a real Information Retrieval (IR) workflow inspectable. Users must be able to perform live searches on NFCorpus, view the dataset preparation steps, and verify if Anserini's observed evaluation metrics align with expected reproduction targets.

## Goals
- Utilize repo-local Anserini skills as the primary source for setup, CLI syntax, reproduction discovery, search, and evaluation.
- Implement a live web application deployable as a Render Docker web service.
- Restrict required datasets to NFCorpus only.
- Enable live query search over NFCorpus through a backend powered by Anserini.
- Execute or verify a BM25 NFCorpus evaluation using authentic Anserini commands and qrels.
- Display expected metrics, observed metrics, deltas, commands used, and paths to generated artifacts.
- Incorporate browser-driven verification to confirm the application uses real, not mocked, search and evaluation results.

## Non-Goals
- Support for all BEIR datasets.
- Downloading the complete BEIR corpus archive.
- Demos for MS MARCO or other large corpora.
- Dense retrieval, neural reranking, or model training functionalities.
- User account management, authentication, or multi-user job management.
- Implementation of custom retrieval engines.
- Utilizing `GetDocument` if search results already contain sufficient document content.
- Requiring deployment on Vercel.

## Users
- IR researchers seeking a lightweight live retrieval-quality demonstration.
- Developers verifying Anserini's setup and evaluation workflows for NFCorpus.
- Demo users comparing live search outcomes with measured retrieval metrics.
- Operators deploying benchmark outputs to Render.

## Core Requirements
- Use the following repo-local skills to formulate commands:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Install or locate an Anserini fatjar and validate it using the runtime checks provided by the skills.
- Discover NFCorpus-related reproduction details utilizing the Anserini reproduction workflow. Employ reproduction listing/show/dry-run capabilities where possible to extract NFCorpus commands, expected metrics, qrels/eval keys, and setup requirements.
- Strictly avoid downloading all BEIR corpora. Any downloading or caching must be specific to NFCorpus and documented within the UI.
- Prefer prebuilt/cached NFCorpus indices or NFCorpus-specific artifacts when provided by Anserini. If none are available, the application may build or prepare the index solely for NFCorpus.
- Execute real Anserini commands for setup, search, and evaluation operations. Hardcoding or mocking search results, run files, qrels, scores, or expected metrics is prohibited.
- The backend must support live query search over NFCorpus, backed by Anserini (e.g., Anserini REST server or CLI-backed endpoint), not a custom search implementation.
- Search results must display rank, document ID, score, and sufficient document content or snippet text for user inspection.
- The BM25 evaluation workflow for NFCorpus must include:
  - Executing `SearchCollection` or equivalent reproduction-provided commands.
  - Writing a TREC-format run file.
  - Evaluating using the appropriate Anserini/TrecEval command.
  - Parsing the observed metric values.
  - Comparing observed values against expected values (if provided by the reproduction).
- If live evaluation performance is insufficient for hosted use, the app may run the evaluation during setup/startup. It should then provide a "Verify/Rerun" action in the browser that reuses cached NFCorpus artifacts. The UI must clearly differentiate between cached results and fresh reruns.
- Display a readiness panel indicating the status of Java/fatjar, NFCorpus artifacts/index, reproduction discovery, and the app's readiness for live search and evaluation.
- Show the exact command lines executed for:
  - Fatjar verification.
  - Reproduction discovery/dry-run.
  - NFCorpus search setup.
  - BM25 retrieval.
  - Evaluation.
- Show artifact paths for generated run files, evaluation outputs, setup logs, and any cached NFCorpus data.
- Gracefully handle and display clear user-visible errors for: missing Java, missing fatjar, unsupported Anserini version, missing NFCorpus artifacts, command failures, unavailable expected metrics, port conflicts, and evaluation failures.

## Deployment Requirements
- The application must be deployable as a single Docker web service suitable for Render.
- Include a Dockerfile (or equivalent generated project files) in the implementation.
- The container must bind HTTP to `0.0.0.0` and utilize the `PORT` environment variable, falling back to `10000` if unset.
- Provide a `/health` endpoint returning a JSON response that includes at least:
  - Application status.
  - Anserini availability.
  - NFCorpus readiness.
  - Search availability status.
  - Evaluation availability status.
- The application must not require interactive setup after the container has started.
- Large generated files must not be committed to source control. Runtime caches should be stored in a documented cache/data directory. Document the mount path if persistent storage is required on Render.
- The default demo must remain small enough for a modest Render service, avoiding full-BEIR downloads, MS MARCO downloads, and heavy dense-vector artifacts.

## UX (User Experience)
Upon page load, the user should be presented with a compact diagnostics dashboard featuring:
- A readiness/status panel for Anserini and NFCorpus.
- A live search box pre-populated with NFCorpus sample queries or topics.
- A ranked result list displaying ranks, document IDs, scores, and snippets/document text.
- An evaluation panel displaying BM25 metrics, expected metrics, observed metrics, deltas, pass/close/fail status, elapsed time, and artifact paths.
- A command/artifact drawer exposing the exact Anserini commands and output previews used to generate the displayed results.

Users must be able to type a query or click a sample NFCorpus query to initiate a live search. They can also inspect the BM25 evaluation status and trigger a verification/rerun if the implementation supports it.

## End-to-End Verification
Include a browser test (e.g., Playwright) that launches the application and verifies the core workflow.
The test must:
- Open the application.
- Verify the appearance of the health/readiness panel.
- Verify that NFCorpus is identified as the active dataset.
- Verify that Anserini setup status is visible.
- Run or select a live NFCorpus query.
- Verify that ranked search results appear, including document IDs, ranks, scores, and text/snippets.
- Verify that the evaluation panel displays at least one numeric observed metric.
- Verify that expected metric information is visible when exposed by reproduction discovery.
- Verify that observed-vs-expected comparison status or delta is shown.
- Verify that exact command text and artifact paths/previews are visible.
- Verify that the Docker/Render readiness contract is documented within the app or README, including the `PORT` binding details.

The test must fail if the application displays mocked search results, mocked evaluation outputs, or hardcoded metric values without having executed Anserini-backed setup/search/evaluation commands.

## Success Criteria
- The application runs locally in Docker and serves HTTP traffic on the configured `PORT`.
- The application can be deployed as a Docker web service on Render.
- Live NFCorpus search can be performed from the browser.
- Real Anserini-backed NFCorpus evaluation metrics can be inspected by users.
- Users can view expected-vs-observed metric comparisons when expected metrics are discoverable.
- The application avoids full-BEIR and large-corpus downloads by default.
- Command lines, artifacts, and failure states are transparent enough to facilitate debugging.
- The browser test passes and demonstrates that the genuine Anserini workflow is executed.
