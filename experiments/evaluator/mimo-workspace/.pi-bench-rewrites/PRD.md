# PRD

## Title
Anserini Prebuilt Index Evaluator

## Summary
Create a local web application that lets users explore Anserini's catalog of prebuilt Lucene inverted indexes and perform reproducible retrieval evaluations through a browser interface. The application should make it easy to discover available indexes, match an index with appropriate topics and qrels when possible, execute Anserini retrieval commands, evaluate the resulting run file with a chosen metric, and review the score along with run details.

## Problem
Anserini maintains registries for prebuilt indexes, topics, and evaluation resources, but working with them currently requires navigating between CLI tools, registry output, run files, and evaluator output separately. This project aims to solve that by providing a lightweight local app that surfaces the index catalog and converts a supported index/topic/qrels combination into a browser-driven evaluation workflow, while still invoking real Anserini commands behind the scenes.

## Goals
- Leverage the Anserini fatjar CLI for catalog discovery, retrieval, and evaluation tasks.
- Expose Anserini's available prebuilt Lucene inverted indexes to the user.
- Surface compatible topics and qrels/evaluation resources for indexes that support evaluation.
- Use CACM as the default small end-to-end evaluation dataset.
- Allow users to select an evaluation metric, including modern ranking metrics such as `nDCG@10` and `Recall@1000` when applicable.
- Present the evaluation score along with sufficient metadata to verify what was executed.
- Include a Playwright end-to-end test that demonstrates the app performs actual retrieval and evaluation.

## Non-Goals
- Integrating with the Anserini REST API
- Constructing a custom retrieval engine
- BM25 parameter tuning
- Auto-tuning or grid-search functionality
- Training or fine-tuning models
- Large-scale evaluation by default
- Authentication or user account management
- Production deployment infrastructure

## Users
- IR researchers exploring Anserini's prebuilt retrieval resources
- Developers validating Anserini search and evaluation workflows
- Demo users seeking a concrete local evaluation interface

## Core Requirements
- Treat the repo-local Anserini skills as the authoritative source: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing or locating the Anserini fatjar through `install-anserini-fatjar` and verify that it functions correctly.
- Perform all registry discovery, retrieval, and evaluation via Anserini command-line tools; do not use the Anserini REST API for any part of this task.
- Do not hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Derive the exact Anserini CLI syntax from the repo-local skills and command help rather than inferring or guessing it.
- Build a local web application with a browser-based UI.
- Populate the index catalog by querying the Anserini prebuilt-index registry rather than relying solely on a hardcoded list.
- Offer search or filtering capabilities for the available prebuilt Lucene inverted indexes.
- Display useful catalog metadata per index when available—e.g., name, type, description, and whether the index is evaluable within this app.
- Retrieve topic sets from Anserini's topics registry.
- Match indexes with compatible topics and qrels/evaluation resources when this can be determined from Anserini registries, repo-local skills, or reproduction documentation.
- Visually differentiate indexes that are ready for evaluation from those that appear in the catalog but lack an automatically discovered topics/qrels pairing.
- Treat CACM as the default evaluation target, including its prebuilt index, topics, and qrels/evaluation configuration.
- Ensure CACM can run end to end without extra user configuration; also use it as the default Playwright test dataset.
- Provide a metric selector that includes `nDCG@10` and `Recall@1000` when the selected dataset supports them.
- The metric selector may also include classic metrics such as MAP or precision cutoffs when supported, but these must not be the only available choices.
- Map user-friendly metric labels to the precise metric identifiers expected by Anserini's evaluator.
- Provide a Run Evaluation action that:
  - Executes retrieval for the selected index/topic pairing,
  - Writes a TREC-format run file,
  - Evaluates that run with the selected metric,
  - Displays the resulting score.
- Show sufficient run metadata for debugging: selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and evaluation output path or preview.
- Handle missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures with clear user-visible error messages.

## UX
When the page loads, the user should see a compact catalog-and-evaluation dashboard. The index catalog should default to CACM as the selected evaluable option and also expose the broader Anserini prebuilt Lucene inverted-index catalog. Indexes that cannot be evaluated automatically should remain visible but be disabled or clearly marked as catalog-only.

Once an evaluable index is selected, the UI should display the paired topic set, qrels/evaluation source, and available metrics. The user selects a metric such as `nDCG@10` or `Recall@1000` (when available) and clicks Run Evaluation. While retrieval and evaluation are in progress, the UI should show a progress indicator or pending state. On completion, the UI should display the score and run metadata.

## End-to-End Verification
Include a Playwright test that launches the app and verifies the full workflow in a browser.

The test must:
- Open the app.
- Confirm CACM is selected or selectable.
- Confirm the index catalog exposes more than a hardcoded single CACM option when the prebuilt-index registry is available.
- Confirm CACM displays a topic/qrels or evaluation pairing.
- Select a supported metric such as `nDCG@10` or `Recall@1000`, with a clear fallback if those metrics are unavailable for CACM.
- Click Run Evaluation.
- Verify that a numeric score appears.
- Verify that run metadata appears, including index, topics, metric, and run/evaluation artifact paths or previews.
- Verify that at least one catalog-only or non-selected index is visible from the registry-derived catalog.

The Playwright test must fail if the app only displays mocked catalog data or mocked evaluation results without executing Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini's prebuilt Lucene inverted-index catalog from the browser.
- Users can run a CACM retrieval evaluation from the browser.
- Users can see which catalog indexes are evaluable and which are catalog-only.
- The app uses real Anserini CLI registry, retrieval, and evaluation outputs.
- The generated run files and evaluation outputs are available for inspection.
- The Playwright e2e test passes in a local environment and verifies the main workflow.
