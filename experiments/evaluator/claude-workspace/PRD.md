# PRD

## Title
Anserini Prebuilt Index Evaluator

## Overview
Create a local web application that lets users browse Anserini's prebuilt Lucene inverted indexes and execute reproducible retrieval evaluations against them. The app should make Anserini's catalog discoverable, associate an index with compatible topics and qrels when feasible, invoke real Anserini retrieval, run the evaluator with a chosen metric, and surface the score along with run artifacts.

## Motivation
Anserini already provides registries for prebuilt indexes, topics, and evaluation assets, but exercising them today means hopping between CLI tools, registry dumps, run files, and evaluator output. The goal is a small local app that surfaces the catalog and turns a supported index/topics/qrels combination into a browser-driven evaluation while still executing genuine Anserini commands underneath.

## Objectives
- Drive catalog discovery, retrieval, and evaluation through the Anserini fatjar CLI.
- Expose the available Anserini prebuilt Lucene inverted indexes.
- Surface or discover compatible topics and qrels/evaluation resources for indexes that can be evaluated.
- Ship CACM as the default small end-to-end evaluation dataset.
- Allow the user to pick an evaluation metric, including modern ranking metrics such as `nDCG@10` and `Recall@1000` when supported.
- Display the score and sufficient metadata to verify what actually ran.
- Provide an end-to-end browser test that demonstrates the app really executes retrieval and evaluation.

## Out of Scope
- Calling the Anserini REST API.
- Implementing a bespoke retrieval engine.
- Tuning BM25 parameters.
- Any automated tuning or grid search.
- Model training or fine-tuning.
- Large-scale evaluation as a default.
- Authentication or user accounts.
- Production deployment infrastructure.

## Target Users
- IR researchers who want to explore Anserini's prebuilt retrieval resources.
- Developers verifying Anserini search and evaluation workflows.
- Demo audiences who want a tangible local evaluation interface.

## Functional Requirements
- Treat the repo-local Anserini skills as authoritative: `install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction`.
- Begin by installing or locating the Anserini fatjar using `install-anserini-fatjar` and verifying it runs.
- Use Anserini's command-line interface for registry inspection, retrieval, and evaluation. The Anserini REST API must not be used for this task.
- Do not hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Derive the precise Anserini CLI syntax from the repo-local skills and the tools' own help output rather than guessing.
- Deliver a local web app with a browser-based UI.
- Pull the list of prebuilt Lucene inverted indexes from Anserini's prebuilt-index registry rather than relying on a hardcoded-only list.
- Offer a searchable or filterable catalog over the available prebuilt Lucene inverted indexes.
- For each catalog entry, show useful metadata when it is available, e.g. name, type, description, and whether the entry is evaluable inside this app.
- Discover or expose topic sets from Anserini's topics registry.
- Pair indexes with compatible topics and qrels/evaluation resources whenever this is derivable from Anserini's registries, the repo-local skills, or the reproduction documentation.
- Clearly differentiate indexes that are ready for evaluation from indexes that appear in the catalog but for which no automatic topics/qrels pairing was found.
- Make CACM the default evaluation target, covering its prebuilt index, topics, and qrels/evaluation setup.
- CACM must be runnable end-to-end with no additional user configuration and is the default dataset for the Playwright test.
- Provide a metric selector that includes `nDCG@10` and `Recall@1000` when supported for the chosen dataset.
- The metric selector may additionally include classical metrics such as MAP or precision cutoffs when supported, but those must not be the only available choices.
- Translate user-facing metric labels into the exact metric identifiers Anserini's evaluator expects.
- Provide a Run Evaluation action that:
  - performs retrieval for the chosen index/topics pairing,
  - emits a TREC-format run file,
  - evaluates that run with the selected metric,
  - displays the resulting score.
- Show run metadata sufficient for debugging: selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and the evaluation output path or a preview of it.
- Surface clear user-visible errors for: missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures.

## User Experience
On load, the user sees a compact dashboard that combines the catalog and evaluation. The index catalog defaults to CACM as the selected evaluable option while also exposing the broader Anserini prebuilt Lucene inverted-index catalog. Indexes that cannot be evaluated automatically should still appear, but should be disabled or unambiguously labeled as catalog-only.

When an evaluable index is selected, the UI should show its paired topic set, the qrels/evaluation source, and the available metrics. The user picks a metric (e.g. `nDCG@10` or `Recall@1000` when available) and clicks Run Evaluation. During retrieval and evaluation, the UI shows progress or a pending state. On completion, the UI displays the score and the run metadata.

## End-to-End Verification
Include a Playwright test that launches the app and exercises the workflow in a browser.

The test must:
- Open the app.
- Confirm CACM is either selected or selectable.
- Confirm that, when the prebuilt-index registry is available, the index catalog contains more than a single hardcoded CACM entry.
- Confirm CACM exposes a topic/qrels or evaluation pairing.
- Pick a supported metric such as `nDCG@10` or `Recall@1000`, with a clear fallback if those metrics are not available for CACM.
- Click Run Evaluation.
- Assert that a numeric score appears.
- Assert that run metadata is shown, including index, topics, metric, and run/evaluation artifact paths or previews.
- Assert that at least one catalog-only or non-selected index from the registry-derived catalog is visible.

The Playwright test must fail if the app shows only mocked catalog data or mocked evaluation results without actually executing Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini's prebuilt Lucene inverted-index catalog in the browser.
- Users can run a CACM retrieval evaluation from the browser.
- Users can tell which catalog entries are evaluable versus catalog-only.
- The app uses real outputs from Anserini's CLI registry, retrieval, and evaluation steps.
- The generated run files and evaluation outputs are available for inspection.
- The Playwright end-to-end test passes in a local environment and exercises the main workflow.
