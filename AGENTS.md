# Agent Instructions

## Preserve Agent Workspaces

Directories named `*-workspace/` contain one-shot implementations produced by benchmark agents. Treat them as benchmark specimens.

Do not edit agent implementation files after the original one-shot run unless the user explicitly asks for that workspace to be modified. This includes source files, app code, tests, README files, package manifests, and profile/config files inside any `*-workspace/` directory.

For judging/evaluation, limited operational changes inside a workspace are acceptable only when they are setup artifacts the implementation itself would reasonably need, for example:

- installing dependencies with package managers
- placing or downloading runtime artifacts such as a documented fatjar
- writing temporary run/evaluation outputs produced by the app or setup smoke checks

Prefer keeping these generated artifacts out of version control and clean them up when the user asks to restore the one-shot workspace state. Never patch an agent implementation just to make the judge pass.

## Judge Harness Changes

Changes to the judge harness should be general. Avoid app-specific branches such as hardcoded Anserini installation logic, hardcoded filenames, or special cases for a particular model workspace.

Good patterns:

- collect context from the PRD, implementation README files, manifests, and referenced local skills
- let the setup planner infer commands from that context
- broaden the harness with generic command handling, safe parsing, better artifact capture, and robust evidence collection
- add regression tests for harness failure modes

Bad patterns:

- modifying an agent workspace to satisfy a test
- adding one-off code in `bench/web_eval` for a specific implementation
- assuming one UI layout, port, filename, or dependency version unless documented by the PRD/README/manifest/skill context

The ideal direction is a lightweight agentic judge loop that can discover how to run and evaluate an app from project-visible evidence while staying bounded in cost. Until then, balance flexibility with deterministic allowlists and clear artifacts.

## Debugging Discipline

When a web eval result looks wrong, inspect artifacts before changing code:

1. `evals/<id>/setup.json`
2. `evals/<id>/setup-context.json`
3. `evals/<id>/run.json`
4. `evals/<id>/evidence/*.json`
5. `evals/<id>/judgments/*.json`
6. screenshots and app logs if available

If an implementation appears broken, report that directly. If the implementation works manually but the judge reports failure, fix the harness only at the general mechanism that caused the false negative.
