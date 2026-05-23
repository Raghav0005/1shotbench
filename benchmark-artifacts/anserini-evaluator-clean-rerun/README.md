# Anserini Evaluator Clean Rerun

Run id: `20260523-032002-d5f3fc6f`
Label: `anserini-evaluator-clean-rerun`
Date: 2026-05-23 UTC / 2026-05-22 America/Toronto
Prompt: `@PRD-anserini-evaluator.md`
Runner commit: `b97edad Fix Pi JSON stream handling for long lines`

This rerun was launched after cleaning all model workspaces back to the scaffolded baseline and after fixing the benchmark runner's long Pi JSON-line handling.

## Outcome

| Model | Status | Duration | Total tokens | Cost USD | Requests |
| --- | --- | ---: | ---: | ---: | ---: |
| Gemini | completed | 160.8s | 1,055,729 | 0.5798976 | 31 |
| GPT | completed | 465.9s | 987,853 | 1.3869050 | 44 |
| Claude | completed | 492.1s | 1,592,921 | 1.11476865 | 45 |
| GLM | completed | 442.8s | 1,263,804 | 0.0 | 43 |
| MiniMax | completed | 769.2s | 3,369,733 | 0.26478675 | 66 |
| Kimi | manually stopped | n/a | n/a | n/a | n/a |

Kimi did not show the prior runner hang signature. The runner continued receiving events, and Kimi kept editing and rerunning tests. It was manually stopped after a prolonged repair loop, so this should be classified as model/agent non-termination rather than a harness timeout.

## Files

- `*/result.json`: completed per-model benchmark result files for the five successful runs.
- `*/stdout.log`: rendered progress logs for each model, including Kimi's partial run.
- `prompt.txt`: prompt captured by the benchmark runner.

The full raw `events.jsonl` files were intentionally not committed because the clean run's event traces are about 576 MB. The full raw run remains locally at `runs/20260523-032002-d5f3fc6f` if deeper forensic inspection is needed.
