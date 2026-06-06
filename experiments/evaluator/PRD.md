# PRD

## Title
Anserini Prebuilt Index Evaluator

## Summary
Build a local web application for browsing Anserini's prebuilt Lucene inverted indexes and running reproducible retrieval evaluations. The app will help users discover available indexes, pair an index with compatible topics and qrels when possible, run Anserini retrieval, evaluate the generated run with a selected metric, and inspect the resulting score and run artifacts.

## Problem
Anserini exposes rich registries for prebuilt indexes, topics, and evaluation resources, but using them requires jumping between command-line tools, registry output, run files, and evaluator output. We need a lightweight local app that makes the catalog visible and turns a supported index/topic/qrels pairing into a browser-driven evaluation workflow while still using real Anserini commands underneath.

## Goals
- Use the Anserini fatjar CLI for catalog discovery, retrieval, and evaluation.
- Provide access to Anserini's available prebuilt Lucene inverted indexes.
- Discover or expose compatible topics and qrels/evaluation resources for evaluable indexes.
- Support CACM as the default small end-to-end evaluation dataset.
- Let users choose an evaluation metric, with modern ranking metrics such as `nDCG@10` and `Recall@1000` when supported.
- Show the evaluation score and enough metadata to verify what was run.
- Include an end-to-end browser test that proves the app actually runs retrieval and evaluation.

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
- IR researchers exploring Anserini's prebuilt retrieval resources
- Developers validating Anserini search and evaluation workflows
- Demo users who want a concrete local evaluation interface

## Core Requirements
- Use the repo-local Anserini skills as the source of truth: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Start by installing or locating the Anserini fatjar via `install-anserini-fatjar` and confirm that it works.
- Use Anserini command-line tools for registry discovery, retrieval, and evaluation. Do not use the Anserini REST API for this task.
- Do not hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Discover the exact Anserini CLI syntax from the repo-local skills and command help rather than guessing.
- Build a local web app with a browser UI.
- Discover Anserini's prebuilt Lucene inverted indexes from the Anserini prebuilt-index registry rather than maintaining a hardcoded-only index list.
- Provide a searchable or filterable index catalog for the available prebuilt Lucene inverted indexes.
- Display useful catalog metadata for each index when available, such as name, type, description, and whether it appears evaluable in this app.
- Discover or expose topic sets from Anserini's topics registry.
- Pair indexes with compatible topics and qrels/evaluation resources when this can be determined from Anserini registries, repo-local skills, or reproduction docs.
- Clearly distinguish indexes that are ready for evaluation from indexes that are visible in the catalog but lack an automatically discovered topics/qrels pairing.
- Support CACM as the default evaluation target, including its prebuilt index, topics, and qrels/evaluation setup.
- CACM must be runnable end to end without additional user configuration and should be used as the default Playwright test dataset.
- Provide a metric selector that includes `nDCG@10` and `Recall@1000` when supported by the selected dataset.
- The metric selector may also include classic metrics such as MAP or precision cutoffs when supported, but those should not be the only available choices.
- Map user-friendly metric labels to the exact metric identifiers expected by Anserini's evaluator.
- Provide a Run Evaluation action that:
  - executes retrieval for the selected index/topic pairing,
  - writes a TREC-format run file,
  - evaluates that run with the selected metric,
  - displays the resulting score.
- Display enough run metadata for debugging, including selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and evaluation output path or preview.
- Handle missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures with clear user-visible errors.

## UX
On page load, the user sees a compact catalog-and-evaluation dashboard. The index catalog defaults to CACM as the selected evaluable option and also exposes the broader Anserini prebuilt Lucene inverted-index catalog. Indexes that cannot be evaluated automatically should remain visible but disabled or clearly marked as catalog-only.

When an evaluable index is selected, the UI shows the paired topic set, qrels/evaluation source, and available metrics. The user selects a metric such as `nDCG@10` or `Recall@1000` when available and clicks Run Evaluation. While retrieval and evaluation are running, the UI shows progress or a pending state. When the run completes, the UI shows the score and run metadata.

## End-to-End Verification
Include a Playwright test that starts the app and verifies the workflow in a browser.

The test must:
- Open the app.
- Confirm CACM is selected or selectable.
- Confirm the index catalog exposes more than a hardcoded single CACM option when the prebuilt-index registry is available.
- Confirm CACM shows a topic/qrels or evaluation pairing.
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
