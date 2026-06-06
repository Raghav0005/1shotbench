# PRD

## Title
Anserini Prebuilt Index Evaluator

## Summary
Build a local browser-based application that lets users explore Anserini's catalog of prebuilt Lucene inverted indexes and execute reproducible retrieval evaluations. The application surfaces which indexes are available, pairs compatible topics and qrels with each index where possible, drives Anserini retrieval end-to-end, evaluates the resulting TREC run with a chosen metric, and displays both the numeric score and the supporting run artifacts.

## Problem
Anserini ships detailed registries for prebuilt indexes, topics, and evaluation resources, but actually using them means stitching together command-line invocations, registry output, run files, and evaluator output by hand. The project needs a lightweight local web interface that makes the catalog browsable and converts a supported index/topic/qrels triplet into a browser-driven evaluation cycle, all while relying on real Anserini commands under the hood.

## Goals
- Drive catalog discovery, retrieval, and evaluation through the Anserini fatjar CLI.
- Expose the available prebuilt Lucene inverted indexes from Anserini's registries.
- Discover or surface compatible topics and qrels/evaluation resources for indexes that are evaluable.
- Default to CACM as a small, ready-to-run end-to-end evaluation dataset.
- Allow the user to pick an evaluation metric; include modern ranking metrics such as `nDCG@10` and `Recall@1000` when the chosen dataset supports them.
- Show the evaluation score and enough metadata to verify what was executed.
- Provide an end-to-end Playwright browser test that proves the application actually performs retrieval and evaluation.

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
- IR researchers who want to explore Anserini's prebuilt retrieval resources
- Developers validating Anserini search and evaluation workflows
- Demo users who want a concrete local evaluation interface

## Core Requirements
- Treat the three repo-local Anserini skill files as the authoritative source of truth for all Anserini CLI usage:
  - `install-anserini-fatjar` — fatjar download, smoke tests, and environment verification
  - `anserini-cli` — registry discovery (`PrebuiltIndexRegistry`, `TopicsRegistry`), `SearchCollection` retrieval, `TrecEval` evaluation, and REST examples
  - `anserini-reproduction` — reproduction YAML configs, expected scores, and `trec_eval` workflows
- Begin by installing or locating the Anserini fatjar using the `install-anserini-fatjar` skill and confirm the installation works.
- Use Anserini command-line tools for every step of registry discovery, retrieval, and evaluation. Do not use the Anserini REST API for this task.
- Never hardcode or mock retrieval results, run files, evaluation scores, or catalog data.
- Derive the exact Anserini CLI syntax from the repo-local skills and from command help output (`--help`), not from guessing.
- Build a local web application with a browser UI.
- Discover Anserini's prebuilt Lucene inverted indexes by querying the `PrebuiltIndexRegistry` CLI (`io.anserini.cli.PrebuiltIndexRegistry`) rather than relying solely on a hardcoded index list.
- Present a searchable or filterable index catalog showing all the available prebuilt Lucene inverted indexes.
- Display useful catalog metadata for each index when available — name, type, description, and whether the index appears evaluable within the application.
- Discover or expose topic sets from the `TopicsRegistry` CLI (`io.anserini.cli.TopicsRegistry`).
- Pair indexes with compatible topics and qrels/evaluation resources when those pairings can be determined from Anserini registries, the repo-local skills, or the reproduction documentation.
- Visibly distinguish indexes that are ready for evaluation from those that appear in the catalog but lack an automatically discovered topics/qrels pairing.
- Support CACM as the default evaluation target: its prebuilt index, topics, and qrels/evaluation setup must all work out of the box.
- CACM must be fully runnable end-to-end with no extra user configuration and must serve as the default dataset for the Playwright test.
- Provide a metric picker that includes `nDCG@10` and `Recall@1000` when those metrics are supported by the selected dataset.
- The metric picker may also offer classic metrics such as MAP or precision cutoffs when they are supported, but the picker must not be limited to classic metrics alone.
- Translate user-facing metric labels into the exact metric identifiers that Anserini's evaluator (`io.anserini.eval.TrecEval`) expects.
- Provide a Run Evaluation action that:
  - runs retrieval for the selected index/topic pairing,
  - produces a TREC-format run file,
  - evaluates that run file with the selected metric,
  - shows the resulting score.
- Display enough run metadata for debugging: selected index, selected topics, qrels/evaluation source, metric, status, elapsed time, generated run file path, and evaluation output path or preview.
- Handle the following error conditions with clear, user-facing messages: missing Java, missing fatjar, unsupported index/topic pairings, command failures, unavailable metrics, and evaluation failures.

## UX
On page load the user should see a compact catalog-and-evaluation dashboard. The index catalog defaults to CACM as the selected evaluable option and also exposes the full Anserini prebuilt Lucene inverted-index catalog. Indexes that cannot be evaluated automatically should remain visible but be disabled or clearly tagged as catalog-only.

When the user selects an evaluable index, the UI shows the paired topic set, qrels/evaluation source, and the metrics available for that pairing. The user picks a metric (for instance `nDCG@10` or `Recall@1000` when available) and clicks Run Evaluation. While retrieval and evaluation are in progress the UI displays a progress or pending state. When the run finishes the UI shows the score together with the run metadata.

## End-to-End Verification
Include a Playwright test that launches the application and exercises the workflow in a real browser.

The test must:
- Open the application.
- Confirm that CACM is either already selected or can be selected.
- Confirm that the index catalog shows more entries than a single hardcoded CACM option when the prebuilt-index registry is reachable.
- Confirm that CACM displays a topic/qrels or evaluation pairing.
- Select a supported metric such as `nDCG@10` or `Recall@1000`, with a clear fallback if those metrics are unavailable for CACM.
- Click Run Evaluation.
- Verify that a numeric score is displayed.
- Verify that run metadata appears, including index, topics, metric, and paths or previews of run and evaluation artifacts.
- Verify that at least one catalog-only (non-selected) index is visible from the registry-derived catalog.

The Playwright test must fail if the application only displays mocked catalog data or mocked evaluation results without actually executing Anserini retrieval and evaluation.

## Success Criteria
- Users can browse Anserini's prebuilt Lucene inverted-index catalog from the browser.
- Users can execute a CACM retrieval evaluation from the browser.
- Users can see which catalog indexes are evaluable and which are catalog-only.
- The application consumes real Anserini CLI registry, retrieval, and evaluation output.
- Generated run files and evaluation outputs are available for inspection.
- The Playwright end-to-end test passes in a local environment and validates the primary workflow.
