# Product Requirements Document (Rewritten)

## Overview
Develop a local web application that interfaces with Anserini's prebuilt Lucene inverted indexes to facilitate reproducible retrieval evaluations. The application allows users to discover indexes, automatically pair them with topics and qrels when possible, execute Anserini retrieval workflows, run evaluations with specific metrics, and view the results and artifacts.

## Scope and Constraints
- **In-Scope**: 
  - Using Anserini's fatjar CLI for discovery, retrieval, and evaluation.
  - Browsing prebuilt Lucene inverted indexes from Anserini's registry.
  - Exposing topics and evaluation resources.
  - Defaulting to the CACM dataset for small-scale end-to-end evaluation.
  - Metric selection including `nDCG@10` and `Recall@1000` (where supported).
  - Displaying evaluation scores and run metadata.
  - Implementing an end-to-end browser test with Playwright.
- **Out-of-Scope**:
  - Anserini REST API usage.
  - Custom retrieval engine implementation.
  - BM25 parameter tuning or grid search/auto-tuning.
  - Model training or fine-tuning.
  - Large-scale evaluations as a default.
  - Authentication, user accounts, and production deployment.

## Technical Requirements
### Anserini CLI Integration
- Utilize the repository-local skills (`install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`) as the primary references.
- Begin by installing or finding the Anserini fatjar using the instructions in `install-anserini-fatjar`, confirming its functionality.
- Rely strictly on Anserini command-line tools for accessing registries, running retrievals, and performing evaluations. Do not use the Anserini REST API.
- Refrain from hardcoding or mocking catalog data, retrieval results, run files, or evaluation scores.
- Determine the correct Anserini CLI syntax by consulting the repo-local skills and CLI help text rather than assuming parameters.

### Data Discovery and Mapping
- Discover prebuilt Lucene inverted indexes dynamically from the Anserini prebuilt-index registry rather than using a static, hardcoded list.
- Extract and display catalog metadata for indexes (e.g., name, type, description, and evaluability status).
- Discover topics from the Anserini topics registry.
- Establish pairings between indexes, compatible topics, and qrels/evaluation resources based on data from Anserini registries, repo-local skills, or reproduction documentation.

### User Interface and Workflow
- Implement a local web application with a browser interface consisting of a dashboard.
- Display a searchable or filterable catalog of available prebuilt Lucene inverted indexes.
- Default the application to the CACM index, ensuring it is ready for end-to-end evaluation without further configuration.
- Clearly differentiate between indexes that are ready for evaluation (paired with topics/qrels) and those that are merely visible in the catalog (catalog-only).
- Upon selecting an evaluable index (like CACM), display its associated topic set, qrels/evaluation source, and available metrics.
- Provide a metric selector mapping user-friendly labels to the precise identifiers expected by the Anserini evaluator. The selector must include `nDCG@10` and `Recall@1000` where supported, and may include classic metrics like MAP or precision cutoffs, but should not be limited to only the classics.
- Include a "Run Evaluation" action that performs the following:
  - Displays a progress or pending indicator during execution.
  - Runs the retrieval process for the selected index and topic.
  - Generates a TREC-format run file.
  - Evaluates the run file using the selected metric.
  - Displays the resulting evaluation score and relevant run metadata (index, topics, metric, status, elapsed time, run file path, and evaluation output path/preview).
- Gracefully handle and display user-visible errors for scenarios such as missing Java, missing fatjar, unsupported pairings, command failures, missing metrics, or evaluation errors.

### End-to-End Testing (Playwright)
- Write a Playwright browser test that launches the application and verifies the complete user journey.
- The test suite must assert the following:
  - The app opens successfully.
  - CACM is the default or can be selected.
  - The index catalog displays multiple options sourced from the prebuilt-index registry (not just a single hardcoded CACM option).
  - CACM displays an associated topic/qrels or evaluation pairing.
  - A supported metric (e.g., `nDCG@10` or `Recall@1000`) is selected, with an appropriate fallback if those are unavailable for CACM.
  - Clicking "Run Evaluation" initiates the process.
  - A numeric evaluation score is rendered on the screen.
  - Run metadata is present, detailing the index, topics, metric, and artifact paths/previews.
  - At least one catalog-only (non-evaluable or non-selected) index is visible in the registry-derived catalog list.
- The test must be designed to fail if the application relies on mocked catalog data or mocked evaluation results instead of executing real Anserini processes.

## Acceptance Criteria
- Users can access the Anserini prebuilt Lucene inverted-index catalog via the browser interface.
- Users can successfully execute an end-to-end retrieval and evaluation workflow for CACM directly from the UI.
- The interface effectively communicates which indexes are evaluable and which are catalog-only.
- The application relies exclusively on real Anserini CLI executions for registries, retrievals, and evaluations.
- Run files (TREC-format) and evaluation outputs are preserved and accessible for inspection.
- The Playwright end-to-end test executes and passes in a local environment, validating the application's actual functionality.
