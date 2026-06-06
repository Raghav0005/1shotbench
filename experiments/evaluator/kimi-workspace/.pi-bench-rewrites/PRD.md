# Product Requirements Document

## Title
Anserini Prebuilt Index Evaluator

## Summary
Develop a local web application that lets users browse Anserini’s prebuilt Lucene inverted indexes and perform reproducible retrieval evaluations through the browser. The application should make the catalog discoverable, match an index with its compatible topics and qrels whenever feasible, invoke Anserini retrieval, evaluate the resulting run using a chosen metric, and present the computed score together with run artifacts.

## Problem
Anserini provides detailed registries for prebuilt indexes, topics, and evaluation assets, yet interacting with them currently means switching among command-line utilities, registry listings, run files, and evaluator output. A lightweight local application is needed to surface the catalog and turn a supported index/topic/qrels combination into a browser-based evaluation workflow while still delegating the actual work to real Anserini commands.

## Goals
- Drive catalog discovery, retrieval, and evaluation through the Anserini fatjar CLI.
- Surface Anserini’s available prebuilt Lucene inverted indexes.
- Identify or present compatible topics and qrels/evaluation resources for indexes that can be evaluated.
- Treat CACM as the default small end-to-end evaluation dataset.
- Allow the user to pick an evaluation metric, offering modern ranking metrics such as `nDCG@10` and `Recall@1000` when the dataset supports them.
- Display the evaluation score and sufficient metadata to confirm what was executed.
- Include an end-to-end browser test demonstrating that retrieval and evaluation actually run inside the app.

## Non-Goals
- Using the Anserini REST API
- Building a custom retrieval engine
- BM25 parameter tuning
- Auto tuning or grid search
- Training or fine-tuning models
- Large-scale evaluation by default
- Authentication or user accounts
- Production deployment infrastructure

## Users
- Information-retrieval researchers exploring Anserini’s prebuilt retrieval resources
- Developers validating Anserini search and evaluation workflows
- Demonstration users who want a concrete local evaluation interface

## Core Requirements
- Treat the repository-local Anserini skills as authoritative sources: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing or locating the Anserini fatjar via `install-anserini-fatjar` and verify that it functions.
- Use Anserini command-line tools for registry discovery, retrieval, and evaluation. Do not use the Anserini REST API for this task.
- Do not hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Derive the exact Anserini CLI syntax from the repository-local skills and command help instead of assuming it.
- Construct a local web application with a browser-based interface.
- Enumerate Anserini’s prebuilt Lucene inverted indexes from the Anserini prebuilt-index registry rather than relying solely on a hardcoded list.
- Offer a searchable or filterable catalog of the available prebuilt Lucene inverted indexes.
- Present useful catalog metadata for each index when obtainable, such as name, type, description, and whether the app considers it evaluable.
- Enumerate or expose topic sets from Anserini’s topics registry.
- Associate indexes with compatible topics and qrels/evaluation resources whenever that relationship can be determined from Anserini registries, repository-local skills, or reproduction documentation.
- Visually separate indexes that are prepared for evaluation from indexes that appear in the catalog but lack an automatically discovered topics/qrels pairing.
- Support CACM as the default evaluation target, including its prebuilt index, topics, and qrels/evaluation setup.
- CACM must be executable end to end without extra user configuration and must serve as the default Playwright test dataset.
- Supply a metric selector that includes `nDCG@10` and `Recall@1000` when the chosen dataset supports them.
- The metric selector may also offer classic metrics such as MAP or precision cutoffs when supported, but those must not be the only choices.
- Translate user-friendly metric labels into the precise metric identifiers that Anserini’s evaluator expects.
- Provide a Run Evaluation action that:
  - performs retrieval for the chosen index/topic combination,
  - writes a TREC-format run file,
  - evaluates that run with the selected metric,
  - presents the resulting score.
- Show enough run metadata for debugging, including the selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and evaluation output path or preview.
- Surface clear user-visible errors for missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures.

## User Experience
When the page loads, the user sees a compact catalog-and-evaluation dashboard. The index catalog preselects CACM as the evaluable option and also surfaces the broader set of Anserini prebuilt Lucene inverted indexes. Indexes that cannot be evaluated automatically remain visible but are disabled or explicitly marked as catalog-only.

After selecting an evaluable index, the interface displays the paired topic set, qrels/evaluation source, and available metrics. The user chooses a metric such as `nDCG@10` or `Recall@1000` when offered, then clicks Run Evaluation. While retrieval and evaluation are in progress, the interface indicates a pending or loading state. Upon completion, the interface shows the score and run metadata.

## End-to-End Verification
Include a Playwright test that launches the app and validates the workflow in a browser.

The test must:
- Open the application.
- Verify that CACM is selected or can be selected.
- Verify that the index catalog reveals more than a single hardcoded CACM option when the prebuilt-index registry is accessible.
- Verify that CACM presents a topic/qrels or evaluation pairing.
- Choose a supported metric such as `nDCG@10` or `Recall@1000`, with an explicit fallback if those metrics are unavailable for CACM.
- Click Run Evaluation.
- Confirm that a numeric score appears.
- Confirm that run metadata appears, including index, topics, metric, and run/evaluation artifact paths or previews.
- Confirm that at least one catalog-only or non-selected index is visible from the registry-derived catalog.

The Playwright test must fail if the application displays only mocked catalog data or mocked evaluation results without actually executing Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini’s prebuilt Lucene inverted-index catalog in the browser.
- Users can execute a CACM retrieval evaluation in the browser.
- Users can distinguish catalog indexes that are evaluable from those that are catalog-only.
- The application relies on real Anserini CLI registry, retrieval, and evaluation output.
- Generated run files and evaluation outputs can be inspected.
- The Playwright end-to-end test passes in a local environment and validates the primary workflow.
