# PRD (rewritten restatement)

## Title
Anserini Prebuilt Index Evaluator

## Summary
Construct a locally hosted web application that surfaces Anserini's prebuilt Lucene inverted indexes and runs reproducible retrieval evaluations against them. The application is intended to make the index catalog browsable, automatically pair indexes with compatible topics and qrels where the registries support it, drive Anserini retrieval and evaluation through the fatjar CLI, and display the resulting score along with the generated run artifacts.

## Problem
Anserini provides registries for prebuilt indexes, topics, and evaluation resources, but working with them today requires moving between command-line invocations, registry output, run files, and evaluator output. A lightweight local application is needed that exposes the catalog in a browser and turns a supported index/topic/qrels combination into a UI-driven evaluation workflow, while still relying on actual Anserini commands underneath.

## Goals
- Drive catalog discovery, retrieval, and evaluation through the Anserini fatjar CLI.
- Expose Anserini's available prebuilt Lucene inverted indexes through the app.
- Discover or surface compatible topics and qrels/evaluation resources for indexes that can be evaluated.
- Treat CACM as the default small end-to-end evaluation dataset.
- Offer a metric selector that includes modern ranking metrics such as `nDCG@10` and `Recall@1000` when the selected dataset supports them.
- Display the evaluation score and supporting metadata that lets a user verify what was executed.
- Ship a Playwright end-to-end browser test that demonstrates the app actually performs retrieval and evaluation.

## Non-Goals
- Using the Anserini REST API.
- Implementing a custom retrieval engine.
- Tuning BM25 parameters.
- Automated hyperparameter tuning or grid search.
- Training or fine-tuning models.
- Defaulting to large-scale evaluation.
- Authentication or user account management.
- Production deployment infrastructure.

## Users
- Information-retrieval researchers exploring Anserini's prebuilt retrieval resources.
- Developers validating Anserini search and evaluation workflows.
- Demo users who want a concrete local interface for running evaluations.

## Core Requirements
- Treat the repo-local Anserini skills as authoritative references: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing or locating the Anserini fatjar through `install-anserini-fatjar` and verify that it functions.
- Use Anserini command-line tools for registry discovery, retrieval, and evaluation. Do not use the Anserini REST API for this task.
- Do not hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Derive the exact Anserini CLI syntax from the repo-local skills and `command help` output rather than guessing.
- Build a local web application with a browser UI.
- Discover Anserini's prebuilt Lucene inverted indexes from the Anserini prebuilt-index registry rather than relying on a hardcoded index list alone.
- Provide a searchable or filterable catalog view for the available prebuilt Lucene inverted indexes.
- Display useful catalog metadata for each index when available, including name, type, description, and whether the app considers it evaluable.
- Discover or expose topic sets from Anserini's topics registry.
- Pair indexes with compatible topics and qrels/evaluation resources where this can be determined from Anserini registries, repo-local skills, or reproduction docs.
- Visually distinguish indexes that are ready for evaluation from indexes that appear in the catalog but lack an automatically discovered topics/qrels pairing.
- Support CACM as the default evaluation target, including its prebuilt index, topics, and qrels/evaluation setup.
- CACM must run end to end without additional user configuration and must be used as the default Playwright test dataset.
- Provide a metric selector that includes `nDCG@10` and `Recall@1000` when the selected dataset supports them.
- The metric selector may also offer classic metrics such as MAP or precision cutoffs when supported, but those must not be the only available choices.
- Translate user-friendly metric labels into the exact metric identifiers that Anserini's evaluator expects.
- Provide a Run Evaluation action that:
  - executes retrieval for the selected index/topic pairing,
  - writes a TREC-format run file,
  - evaluates that run with the selected metric,
  - displays the resulting score.
- Display sufficient run metadata for debugging, including the selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and evaluation output path or preview.
- Handle missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures with clear user-visible errors.

## UX
On page load, the user sees a compact catalog-and-evaluation dashboard. The index catalog defaults to CACM as the selected evaluable option while also exposing the broader Anserini prebuilt Lucene inverted-index catalog. Indexes that cannot be evaluated automatically remain visible but are disabled or clearly marked as catalog-only.

When an evaluable index is selected, the UI shows the paired topic set, the qrels/evaluation source, and the available metrics. The user picks a metric such as `nDCG@10` or `Recall@1000` when available and triggers Run Evaluation. While retrieval and evaluation are running, the UI shows progress or a pending state. When the run finishes, the UI shows the score and the run metadata.

## End-to-End Verification
Include a Playwright test that launches the app and validates the workflow in a browser.

The test must:
- Open the app.
- Confirm that CACM is selected or selectable.
- Confirm that the index catalog exposes more than a hardcoded single CACM option when the prebuilt-index registry is available.
- Confirm that CACM displays a topic/qrels or evaluation pairing.
- Select a supported metric such as `nDCG@10` or `Recall@1000`, with a clear fallback if those metrics are not available for CACM.
- Click Run Evaluation.
- Verify that a numeric score appears.
- Verify that run metadata appears, including index, topics, metric, and run/evaluation artifact paths or previews.
- Verify that at least one catalog-only or non-selected index is visible from the registry-derived catalog.

The Playwright test must fail if the app only shows mocked catalog data or mocked evaluation results without actually executing Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini's prebuilt Lucene inverted-index catalog from the browser.
- Users can run a CACM retrieval evaluation from the browser.
- Users can see which catalog indexes are evaluable and which are catalog-only.
- The app relies on real Anserini CLI registry, retrieval, and evaluation outputs.
- The generated run files and evaluation outputs are available for inspection.
- The Playwright e2e test passes in a local environment and validates the main workflow.
