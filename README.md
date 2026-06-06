# 1ShotBench

1ShotBench runs the same task prompt through multiple Pi agent workspaces so you can compare how different models behave under the same harness.

The old Codex proxy path has been removed. Implementation agents now run through the `pi` CLI directly, using a small `bench.toml` file inside each model workspace.

## Quick Start

Install the Python dependencies:

```sh
pip install -r requirements.txt
```

Create or refresh model workspaces for a task:

```sh
python scripts/create_agent_workspaces.py experiments/frontend
```

Run a benchmark:

```sh
python -m bench.cli \
  --task-dir experiments/frontend \
  --prompt-file experiments/frontend/PRD.md \
  --models gpt claude gemini
```

Start the local dashboard:

```sh
uvicorn bench.web:app --port 4010
```

Open:

```text
http://127.0.0.1:4010
```

## Current Layout

Task workspaces live under `experiments/`:

```text
experiments/
  frontend/
    PRD.md
    features.yaml
    gpt-workspace/
      bench.toml
    claude-workspace/
      bench.toml
    gemini-workspace/
      bench.toml

  evaluator/
    PRD.md
    features.yaml

  nfcorpus-repro/
    PRD.md
```

Future benchmark tasks can live as sibling directories with the same `*-workspace/bench.toml` structure.

## Documentation

- [Getting Started](docs/getting-started.md): requirements, Pi auth, API keys, and task skills.
- [Workspaces](docs/workspaces.md): workspace layout, `bench.toml`, task files, isolation, and workspace creation.
- [Running Benchmarks](docs/running-benchmarks.md): CLI usage, dashboard, run flow, artifacts, and metrics.
- [Judging Runs](docs/judging.md): LLM judge, Codex judge, Pi judge, feature generation, and evaluation artifacts.
- [Deployments](docs/deployments.md): generic Render/GHCR deployment flow for benchmark demos.
- [NFCorpus Render Runbook](docs/nfcorpus-repro-deploy.md): task-specific deployment notes for the NFCorpus reproduction demos.

## Important Project Rules

Directories named `*-workspace/` contain one-shot benchmark implementations. Treat them as benchmark specimens. Do not patch agent implementation files after a run unless you explicitly intend to modify that workspace.

For judging and evaluation, prefer general harness improvements over app-specific fixes. If an implementation works manually but a judge reports failure, inspect the evaluation artifacts before changing code.

Useful artifact paths:

```text
runs/<run_id>/
evals/<eval_id>/
```

