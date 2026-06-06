# PRD — Anserini Prebuilt Index Evaluator

## Title
Anserini Prebuilt Index Evaluator

## Overview
Create a local web application that lets users explore Anserini's catalog of prebuilt Lucene inverted indexes and run full retrieval evaluations through the browser. The application wraps Anserini fatjar CLI commands for index discovery, retrieval over selected topic sets, and evaluation of the resulting TREC run files—so users can pair an index with its compatible topics and qrels, pick a metric, execute the pipeline, and inspect both the score and the output artifacts, all without leaving the browser.

## Problem Statement
Anserini provides registries for prebuilt indexes, topic files, and evaluation resources, but driving a full evaluation currently requires manually stringing together CLI commands, interpreting registry listings, locating compatible topics/qrels pairs, and examining separate run and evaluator output files. A lightweight browser-based interface should surface the catalog, automate the pairing of indexes with their topics and qrels, and present the evaluation results alongside the raw artifacts—all backed by real Anserini commands.

## Goals
- Leverage the Anserini fatjar CLI for every stage: catalog lookup, retrieval, and evaluation.
- Surface all available Anserini prebuilt Lucene inverted indexes in a browsable catalog.
- Identify and present compatible topics and qrels/evaluation resources for indexes where such a pairing is known.
- Ship CACM as the default small dataset that works end-to-end without extra configuration.
- Offer a metric selector that includes modern ranking metrics like `nDCG@10` and `Recall@1000` when the chosen dataset supports them.
- Render the evaluation score together with sufficient metadata to reproduce and verify the run.
- Include a Playwright end-to-end test that exercises the real retrieval and evaluation pipeline in the browser.

## Non-Goals
- Using the Anserini REST API (the REST server is out of scope).
- Implementing a custom retrieval engine.
- BM25 parameter tuning, auto-tuning, or grid search.
- Model training or fine-tuning.
- Large-scale evaluation as the default mode.
- Authentication, user accounts, or production deployment infrastructure.

## Target Users
- IR researchers browsing Anserini's prebuilt retrieval resources.
- Developers verifying Anserini search and evaluation workflows.
- Demo users wanting a hands-on local evaluation interface.

## Core Requirements

### Anserini Integration
- Treat the repo-local Anserini skills as authoritative references: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- At startup, install or locate the Anserini fatjar via the `install-anserini-fatjar` skill and verify it is functional.
- Use only Anserini command-line tools for registry discovery, retrieval, and evaluation. Do not call the Anserini REST API.
- Derive exact CLI command syntax from the repo-local skills and built-in help output—never guess.
- Never hardcode or mock catalog data, retrieval results, run files, or evaluation scores.

### Index Catalog
- Discover prebuilt Lucene inverted indexes from Anserini's prebuilt-index registry rather than relying solely on a hardcoded list.
- Present a searchable or filterable catalog of available indexes.
- For each index, display available metadata such as name, type, description, and whether the index is evaluable within this application.
- Clearly differentiate indexes that are ready for evaluation (i.e., have a discoverable topics/qrels pairing) from those that are visible for browsing but cannot be evaluated automatically. Non-evaluable indexes should remain visible but be disabled or distinctly marked as catalog-only.

### Topics, Qrels, and Index Pairing
- Discover topic sets from Anserini's topics registry.
- When possible, pair an index with its compatible topics and qrels/evaluation resources using information from Anserini registries, repo-local skills, or reproduction documentation.
- CACM must be supported as the default evaluation target, complete with its prebuilt index, topics, and qrels/evaluation setup.
- CACM must run end-to-end without additional user configuration and serve as the default dataset for the Playwright test.

### Metric Selection
- Provide a metric selector UI.
- Include `nDCG@10` and `Recall@1000` among the options when the selected dataset supports them.
- Classic metrics (e.g., MAP, precision cutoffs) may also appear when supported, but must not be the sole choices.
- Map user-facing metric labels to the precise metric identifiers that Anserini's evaluator expects.

### Evaluation Pipeline
- Provide a "Run Evaluation" action that:
  1. Executes retrieval for the chosen index/topic pairing.
  2. Writes a TREC-format run file.
  3. Evaluates the run with the selected metric.
  4. Displays the resulting numeric score.
- After completion, show run metadata for debugging: selected index, selected topics, qrels/evaluation source, metric, execution status, elapsed time, generated run file path, and evaluation output path or preview.

### Error Handling
- Surface clear, user-visible errors for: missing Java, missing fatjar, unsupported index/topic combinations, command failures, unsupported metrics, and evaluation failures.

## User Experience Flow
On page load the user lands on a compact dashboard combining the index catalog and the evaluation panel. CACM is pre-selected as the default evaluable index, while the broader Anserini prebuilt Lucene inverted-index catalog is also visible. Indexes without an automatic evaluation pairing are shown but marked or disabled as catalog-only.

When an evaluable index is active, the UI presents the paired topic set, qrels/evaluation source, and the metric selector. The user picks a metric (e.g., `nDCG@10` or `Recall@1000` when available) and clicks Run Evaluation. During execution the UI reflects a pending or in-progress state. Upon completion the score and full run metadata are displayed.

## End-to-End Verification (Playwright Test)
Include a Playwright test that launches the app and validates the workflow in a real browser.

The test must:
1. Open the application.
2. Confirm that CACM is selected or selectable.
3. Confirm that the index catalog surfaces more than a single hardcoded CACM entry when the prebuilt-index registry is accessible.
4. Confirm that CACM displays a topic/qrels or evaluation pairing.
5. Select a supported metric such as `nDCG@10` or `Recall@1000`, with a clear fallback strategy if neither is available for CACM.
6. Trigger the Run Evaluation action.
7. Assert that a numeric evaluation score appears.
8. Assert that run metadata is displayed, including index, topics, metric, and paths or previews of run/evaluation artifacts.
9. Assert that at least one catalog-only or non-selected index is visible among the registry-derived entries.

The Playwright test must fail if the application presents only mocked catalog data or mocked evaluation results without actually invoking Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini's prebuilt Lucene inverted-index catalog from the browser.
- Users can execute a CACM retrieval evaluation from the browser.
- Users can distinguish evaluable indexes from catalog-only indexes.
- The application relies on real Anserini CLI output for registry data, retrieval, and evaluation.
- Generated run files and evaluation outputs are available for inspection.
- The Playwright end-to-end test passes locally and validates the primary workflow.
