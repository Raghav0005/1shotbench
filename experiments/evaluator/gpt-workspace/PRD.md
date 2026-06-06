# PRD

## Title
Anserini Prebuilt Index Evaluator

## Summary
Create a local browser-based application for exploring Anserini prebuilt Lucene inverted indexes and executing reproducible retrieval evaluations. The application should let users find available indexes, connect an index to compatible topics and qrels when that pairing can be identified, run Anserini retrieval, evaluate the produced run with a chosen metric, and review the score together with the generated artifacts.

## Problem
Anserini provides extensive registries for prebuilt indexes, topics, and evaluation resources, but using them currently requires moving between CLI commands, registry listings, run files, and evaluator output. A lightweight local application is needed to expose the catalog and convert supported index/topic/qrels combinations into a browser-driven evaluation flow, while still executing real Anserini commands underneath.

## Goals
- Rely on the Anserini fatjar CLI for catalog discovery, retrieval, and evaluation.
- Make Anserini's available prebuilt Lucene inverted indexes accessible.
- Find or show compatible topics and qrels/evaluation resources for indexes that can be evaluated.
- Use CACM as the default small dataset for end-to-end evaluation.
- Allow users to select an evaluation metric, including current ranking metrics such as `nDCG@10` and `Recall@1000` when the dataset supports them.
- Present the evaluation score and sufficient metadata to confirm what was executed.
- Add an end-to-end browser test demonstrating that retrieval and evaluation actually run.

## Non-Goals
- Using the Anserini REST API
- Implementing a custom retrieval engine
- Tuning BM25 parameters
- Performing automatic tuning or grid search
- Training or fine-tuning models
- Running large-scale evaluation by default
- Adding authentication or user accounts
- Creating production deployment infrastructure

## Users
- IR researchers investigating Anserini prebuilt retrieval resources
- Developers checking Anserini search and evaluation workflows
- Demo users seeking a concrete local evaluation UI

## Core Requirements
- Treat the repo-local Anserini skills as authoritative: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing or finding the Anserini fatjar using `install-anserini-fatjar`, then verify that it works.
- Use Anserini command-line tools for registry discovery, retrieval, and evaluation. The Anserini REST API must not be used for this task.
- Do not hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Determine the exact Anserini CLI syntax from the repo-local skills and command help instead of guessing.
- Build a local web application with a browser UI.
- Obtain Anserini prebuilt Lucene inverted indexes from the Anserini prebuilt-index registry rather than depending on a hardcoded-only index list.
- Provide a catalog of available prebuilt Lucene inverted indexes that can be searched or filtered.
- Show useful index catalog metadata when available, including details such as name, type, description, and whether the app appears able to evaluate the index.
- Discover or expose topic sets from Anserini's topics registry.
- Match indexes to compatible topics and qrels/evaluation resources when this can be inferred from Anserini registries, repo-local skills, or reproduction documentation.
- Clearly separate indexes that are ready for evaluation from catalog entries that are visible but do not have an automatically discovered topics/qrels pairing.
- Support CACM as the default evaluation target, including its prebuilt index, topics, and qrels/evaluation configuration.
- CACM must run end to end without extra user configuration and should be the default dataset for the Playwright test.
- Include a metric selector with `nDCG@10` and `Recall@1000` when the selected dataset supports them.
- The metric selector may also provide classic metrics such as MAP or precision cutoffs when supported, but those classic metrics must not be the only options.
- Convert user-friendly metric names to the exact metric identifiers required by Anserini's evaluator.
- Provide a Run Evaluation action that:
  - runs retrieval for the selected index/topic pairing,
  - creates a TREC-format run file,
  - evaluates the run using the selected metric,
  - shows the resulting score.
- Show enough metadata to debug a run, including selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and evaluation output path or preview.
- Present clear user-visible errors for missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures.

## UX
When the page loads, the user should see a compact dashboard that combines the catalog and evaluation workflow. CACM should be the default selected evaluable option, while the wider Anserini prebuilt Lucene inverted-index catalog is also available. Indexes that cannot be automatically evaluated should still be shown, but they should be disabled or clearly labeled as catalog-only.

After selecting an evaluable index, the UI should display the associated topic set, qrels/evaluation source, and available metrics. The user can choose a metric such as `nDCG@10` or `Recall@1000` when available and then click Run Evaluation. During retrieval and evaluation, the UI should indicate progress or a pending state. After completion, the UI should display the score and run metadata.

## End-to-End Verification
Add a Playwright test that launches the app and verifies the workflow through the browser.

The test must:
- Open the app.
- Verify that CACM is selected or can be selected.
- Verify that, when the prebuilt-index registry is available, the index catalog contains more than one hardcoded CACM option.
- Verify that CACM displays a topic/qrels or evaluation pairing.
- Select a supported metric such as `nDCG@10` or `Recall@1000`, with an explicit fallback if those metrics are not available for CACM.
- Click Run Evaluation.
- Verify that a numeric score is displayed.
- Verify that run metadata is shown, including index, topics, metric, and run/evaluation artifact paths or previews.
- Verify that at least one catalog-only or non-selected index from the registry-derived catalog is visible.

The Playwright test must fail if the app displays only mocked catalog data or mocked evaluation results without running Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini's prebuilt Lucene inverted-index catalog in the browser.
- Users can execute a CACM retrieval evaluation in the browser.
- Users can identify which catalog indexes are evaluable and which are catalog-only.
- The app is based on real Anserini CLI registry, retrieval, and evaluation outputs.
- Generated run files and evaluation outputs can be inspected.
- The Playwright e2e test passes locally and verifies the primary workflow.
