# Project Requirements Document

## Project Title
NFCorpus Live Retrieval Diagnostics Workbench

## Overview
Develop a web application that provides live retrieval diagnostics for NFCorpus using Anserini. The application must be containerized via Docker and capable of being deployed on Render. It is required to utilize Anserini skills to configure and validate an NFCorpus retrieval environment, execute live searches exclusively over NFCorpus, and perform or validate a BM25 evaluation against expected metrics. The web interface must present the exact CLI commands used, generated artifacts, and a comparison between expected and observed results. The project is strictly limited to NFCorpus to ensure it runs efficiently on a standard hosted container, explicitly avoiding general BEIR dashboards or downloading all BEIR corpora.

## Problem Statement
While Anserini supports reproducing and evaluating retrieval baselines, its workflow is currently fragmented across documentation, CLI commands, run files, qrels, and evaluation outputs. There is a need for a compact, hosted demonstration that exposes a tangible Information Retrieval (IR) workflow. Users need the ability to search NFCorpus in real-time, comprehend the dataset preparation process, and verify if the evaluation metrics observed via Anserini align with the expected reproduction targets.

## Objectives
- Act as the source of truth for setup, CLI syntax, reproduction discovery, searching, and evaluation by relying on the repository-local Anserini skills.
- Create a real-time web application suitable for deployment as a Render Docker web service.
- Constrain the required dataset exclusively to NFCorpus.
- Enable live search queries against NFCorpus via a backend powered by Anserini.
- Execute or validate a BM25 evaluation on NFCorpus utilizing actual Anserini commands and qrel files.
- Display expected and observed metrics, the differences (deltas) between them, the specific commands executed, and the paths to generated artifacts.
- Implement browser-based verification to ensure the application utilizes genuine search and evaluation processes rather than mocked data.

## Out of Scope
- Expanding support to encompass all BEIR datasets.
- Downloading the complete BEIR corpus archive.
- Creating demonstrations for MS MARCO or other massive corpora.
- Implementing dense retrieval, neural reranking, or training of models.
- Building features for user accounts, authentication, or multi-tenant job management.
- Developing custom retrieval engines from scratch.
- Using `GetDocument` if the search results already contain sufficient document content.
- Making Vercel deployment a requirement.

## Target Audience
- IR researchers seeking a compact, live demonstration of retrieval quality.
- Developers needing to validate the configuration and evaluation workflows of Anserini for NFCorpus.
- Viewers of the demo who wish to compare real-time search outputs with quantified retrieval metrics.
- Systems operators tasked with deploying benchmark results to Render.

## Core Technical Requirements
- Prior to constructing any commands, consult the following repo-local skills:
  - `install-anserini-fatjar`
  - `anserini-cli`
  - `anserini-reproduction`
- Download or locate an Anserini fatjar, validating it using the runtime checks provided by the corresponding skill.
- Utilize the Anserini reproduction workflow to identify NFCorpus-specific reproduction details. Leverage reproduction listing, displaying, or dry-run functionalities (where available) to extract NFCorpus commands, expected metrics, qrel/evaluation keys, and setup prerequisites.
- Strictly avoid downloading all BEIR corpora. Any downloading or caching steps must be explicitly limited to NFCorpus and clearly documented within the user interface.
- Opt for prebuilt or cached NFCorpus indexes or NFCorpus-specific artifacts whenever Anserini provides them. If prebuilt options are absent, the application is permitted to build or prepare the index exclusively for NFCorpus.
- Ensure all setup, search, and evaluation processes use real Anserini commands. Hardcoding or mocking search results, run files, qrels, scores, or expected metrics is strictly prohibited.
- Implement a backend facilitating live queries against NFCorpus. This backend may utilize the Anserini REST server or an endpoint that interfaces with the CLI, provided the underlying search mechanism is Anserini and not a custom implementation.
- Ensure search results return the rank, document ID, score, and adequate document snippet/content text for user inspection.
- Build a BM25 evaluation workflow specific to NFCorpus that:
  - Executes `SearchCollection` or its reproduction-equivalent command.
  - Generates a run file in TREC format.
  - Evaluates the run using the correct Anserini/TrecEval command.
  - Parses the resulting observed metric values.
  - Compares these observed values against the expected metrics extracted from the reproduction workflow, when available.
- In cases where live evaluation proves too slow for a hosted environment, the application may execute the evaluation during the initial setup/startup phase. It must then offer a "Verify/Rerun" action in the browser that leverages the cached NFCorpus artifacts. The UI must unambiguously differentiate between a fresh rerun and cached setup results.
- Display a readiness/status panel indicating the health of Java/the fatjar, the NFCorpus index/artifacts, the reproduction discovery process, and the overall readiness for live search and evaluation.
- Present the exact command-line strings utilized for:
  - Fatjar verification.
  - Reproduction discovery and dry-runs.
  - NFCorpus search setup.
  - BM25 retrieval operations.
  - Evaluation execution.
- Display the file paths for any produced artifacts, including generated run files, evaluation outputs, setup logs, and cached NFCorpus data.
- Gracefully handle and display clear user-facing errors for scenarios including missing Java installations, missing fatjars, unsupported versions of Anserini, absent NFCorpus artifacts, command execution failures, missing expected metrics, port conflicts, and evaluation errors.

## Deployment Specifications
- The application must be packaged as a single Docker web service, ready for deployment on Render.
- Implementation must include a `Dockerfile` or the equivalent generated project configuration files.
- The Docker container is required to bind its HTTP server to `0.0.0.0` and utilize the `PORT` environment variable. If `PORT` is not set, it should default to `10000`.
- Implement a `/health` endpoint that outputs JSON containing at least:
  - Overall application status.
  - Availability of Anserini.
  - Readiness of NFCorpus.
  - Availability of the search function.
  - Availability of the evaluation function.
- The application must start up and operate without requiring any interactive setup post-container initialization.
- Exclude large generated files from source control. Runtime caches and data must reside in a clearly documented cache or data directory. If Render requires persistent storage, the expected mount path must be documented.
- Maintain a lightweight footprint for the default demo to fit within the constraints of a modest Render service. Prevent full BEIR downloads, MS MARCO downloads, or the generation of heavy dense-vector artifacts.

## User Experience (UX)
Upon loading the page, users must be presented with a consolidated diagnostics dashboard containing:

- A status and readiness panel detailing the health of Anserini and NFCorpus.
- A functional live search input field prepopulated with several sample queries or topics specific to NFCorpus.
- A list of ranked search results displaying ranks, document IDs, scores, and textual snippets or document content.
- An evaluation panel detailing BM25 metrics, expected metrics, observed metrics, the delta between them, a pass/close/fail status, the elapsed execution time, and paths to relevant artifacts.
- A designated section (e.g., a drawer or panel) that reveals the exact Anserini commands executed and provides previews of the outputs generated to produce the displayed results.

Users must be able to input custom queries or select from the sample NFCorpus queries to execute a live search. Furthermore, users should have the ability to review the BM25 evaluation status and initiate a verification or rerun process, provided the implementation supports it.

## End-to-End Verification
Provide a browser-based test suite that launches the application and validates the primary workflow.

The test suite must automatically:
- Access the web application.
- Confirm the visibility of the health and readiness panel.
- Confirm that NFCorpus is recognized as the active dataset.
- Confirm the Anserini setup status is displayed.
- Execute or select a live query against NFCorpus.
- Confirm that the ranked search results populate with document IDs, ranks, scores, and text/snippets.
- Confirm that the evaluation panel renders at least one numeric observed metric.
- Confirm that expected metric data is displayed when it is accessible via reproduction discovery.
- Confirm the visibility of the observed-versus-expected comparison status or delta.
- Confirm that the exact CLI commands and artifact paths/previews are visible in the UI.
- Confirm that the Docker and Render readiness requirements are documented (either within the app or a README), explicitly noting the `PORT` binding behavior.

The test suite is required to fail if the application exhibits mocked search results, mocked evaluation data, or hardcoded metric values instead of relying on the actual execution of Anserini-backed setup, search, and evaluation commands.

## Success Criteria
- The application runs successfully in a local Docker environment and serves HTTP traffic on the specified `PORT`.
- The application is structurally ready for deployment as a Docker web service on Render.
- Users can successfully conduct live NFCorpus searches via the browser interface.
- Users can view and inspect actual evaluation metrics for NFCorpus, powered by Anserini.
- Users can view a comparison between expected and observed metrics, provided expected metrics are discoverable.
- The application strictly avoids full-BEIR and large-corpus downloads under default conditions.
- The UI transparently presents command lines, artifacts, and error states to facilitate debugging.
- The Playwright or corresponding browser test suite passes, demonstrably exercising the genuine Anserini workflow.
