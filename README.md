# Pi Bench

Pi Bench runs the same task prompt through multiple Pi agent workspaces so you can compare how different models behave under the same harness.

The old Codex proxy path has been removed. Each model now runs through the `pi` CLI directly, using a small `bench.toml` file inside its workspace.

## Workspace Layout

Task workspaces live in task-specific directories. The current task is:

```text
anserini-frontend/
  PRDv2.md
  gpt-workspace/
    PRDv2.md -> ../PRDv2.md
    bench.toml
  claude-workspace/
    PRDv2.md -> ../PRDv2.md
    bench.toml
  gemini-workspace/
    PRDv2.md -> ../PRDv2.md
    bench.toml

anserini-evaluator/
  PRD-anserini-evaluator.md
  gpt-workspace/
    PRD-anserini-evaluator.md -> ../PRD-anserini-evaluator.md
    bench.toml
```

Future benchmark tasks can live as sibling directories with the same `*-workspace/bench.toml` structure.

Each workspace config supports:

```toml
name = "GPT workspace"
provider = "openai-codex"
model = "gpt-5.5"
thinking = "high"
tools = ["read", "bash", "edit", "write", "grep", "find", "ls"]
required_skills = ["install-anserini-fatjar", "anserini-cli", "anserini-reproduction"]

# Optional:
# system_prompt = "Custom system prompt"
# append_system_prompt = ["extra instructions", "path/to/file.md"]
```

The runner executes Pi from the workspace directory with:

```text
pi --mode json --print --no-session --provider <provider> --model <model> [prompt]
```

Task files matching `PRD*.md`, `TASK*.md`, `task*.md`, or `prompt*.md` should live in the task directory, not the repo root. They are symlinked into every model workspace before each run. For example, `anserini-frontend/PRDv2.md` is available to every Anserini frontend agent as `./PRDv2.md` from inside its workspace.

## Workspace Isolation

Pi Bench runs each model from its own workspace directory and wraps each Pi subprocess in a platform sandbox. On macOS it uses `sandbox-exec`; on Linux it uses `bwrap` (bubblewrap). The sandbox allows normal process behavior but denies file reads and writes against the other configured model workspace directories.

That means a run from `glm-workspace` cannot inspect or modify `kimi-workspace`, `gpt-workspace`, and the other sibling model workspaces for the same task. Preflight fails if neither `sandbox-exec` nor a functional `bwrap` is available, because that isolation cannot be enforced.

This is workspace isolation, not a full container. Agents can still use allowed tools and the network according to the host environment and Pi configuration.

## Codex-Private Notes

Use `.codex-private/` for notes intended for Codex but not Pi benchmark agents. The directory is gitignored, and Pi Bench adds it to every generated sandbox profile as a denied read/write path.

Do not put benchmark instructions for Pi agents there. Use task-local files such as `anserini-frontend/PRDv2.md` for agent-visible task prompts.

## Pi Auth And Keys

Pi supports subscription logins and API-key providers.

For subscriptions, run Pi interactively and use `/login`:

```sh
pi
# then type /login and choose ChatGPT Plus/Pro (Codex), Claude Pro/Max, or GitHub Copilot
```

Pi stores login credentials in:

```text
~/.pi/agent/auth.json
```

For API keys, either use Pi's `/login` flow and choose the provider, edit `~/.pi/agent/auth.json`, export environment variables in your shell, or put them in this project's gitignored `.env` file. Pi Bench loads `.env` before starting each agent process.

Common `.env` entries:

```sh
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ZAI_API_KEY=...
MINIMAX_API_KEY=...
MOONSHOT_API_KEY=...
KIMI_API_KEY=...
```

Auth file example:

```json
{
  "anthropic": { "type": "api_key", "key": "sk-ant-..." },
  "openai": { "type": "api_key", "key": "sk-..." },
  "google": { "type": "api_key", "key": "..." },
  "zai": { "type": "api_key", "key": "..." },
  "minimax": { "type": "api_key", "key": "..." },
  "moonshotai": { "type": "api_key", "key": "..." }
}
```

Pi resolves credentials from `~/.pi/agent/auth.json` before environment variables. The `key` value in `auth.json` can also name an environment variable or start with `!` to run a shell command such as a password-manager lookup.

## Skills And Web Access

Pi's built-in tools are coding tools: `read`, `bash`, `edit`, `write`, `grep`, `find`, and `ls`. The Pi CLI help for version `0.75.1` does not list a built-in web-search tool. Agents can still use `bash` for commands and skill installers when network access is available, and Pi supports installing packages with:

```sh
pi install <source>
```

The Anserini task PRDs ask the agent to use the public `anserini-fatjar` skill and to install it automatically if it is missing and the source is reachable. For fully reproducible runs, preinstall the same skill for every model before benchmarking, or include the exact install source in the task prompt.

Preinstalling skills is usually the fairer benchmark setup. It removes skill discovery, installation time, network variability, and “who found the right package first?” from the model comparison. Letting agents install missing skills is useful for testing agent autonomy, but it changes the benchmark from task implementation to task implementation plus environment bootstrap.

## Benchmark Tracks

The default track is a prepared-environment benchmark. Required task skills and docs are installed before the run, and preflight fails if they are missing. This keeps the comparison focused on whether each model can use the same resources to complete the same implementation task.

A future bootstrap/autonomy track should evaluate skill discovery separately. In that mode, agents would start without the Anserini skills, receive the same web-search or package-discovery capability, and be scored on whether they can find, install, and correctly use the relevant skills before implementing the app.

Keep these tracks separate in run labels and result tables. Mixing them would confound implementation quality with web search, network reliability, package installation, and documentation discovery.

For the current Anserini PRD, preinstall the Anserini skill set into the project before running:

```sh
scripts/install_anserini_skills.sh
```

This copies Anserini's `.agents/skills` directory into this repo's `.agents/skills`. Pi discovers `.agents/skills` from the current workspace and ancestor directories, so every model workspace sees the same local copies. The workspace configs declare these required skills:

- `install-anserini-fatjar`
- `anserini-cli`
- `anserini-reproduction`

Preflight fails if any declared `required_skills` are missing from `.agents/skills`, `.pi/skills`, `~/.pi/agent/skills`, or `~/.agents/skills`.

## Creating Workspaces

Create or refresh the standard model workspace folders for a task with:

```sh
python scripts/create_agent_workspaces.py anserini-frontend
```

By default, the script creates:

- `gpt-workspace`
- `claude-workspace`
- `gemini-workspace`
- `glm-workspace`
- `kimi-workspace`
- `minimax-workspace`

It writes missing `bench.toml` files using the current benchmark defaults and symlinks task-local files such as `PRDv2.md` into each workspace. It does not overwrite existing `bench.toml` files unless you pass `--force`.

Run a non-default task directory with:

```sh
python -m bench.cli --task-dir anserini-frontend --prompt "..." --models gpt claude
```

The web server uses `anserini-frontend` by default. To point it at another sibling task directory:

```sh
PI_BENCH_TASK_DIR=other-task uvicorn bench.web:app --port 4010
```

## Web app feature evaluation

Judge agent-built web apps with PRD-derived feature checks, Playwright evidence, and an LLM judge. The evaluator can either read a checked-in `features.yaml` or ask the judge model to generate feature checks from the PRD before running the browser layer.

One-time setup for the browser layer:

```sh
cd bench/web_eval && npm install && npx playwright install chromium
pip install -r requirements.txt
```

Run a full evaluation with a curated feature file:

```sh
python3 -m bench.web_eval \
  --project anserini-evaluator/gpt-workspace \
  --features anserini-evaluator/features.yaml \
  --prd anserini-evaluator/PRD-anserini-evaluator.md \
  --label gpt-evaluator
```

Or generate the feature file from the PRD at evaluation time:

```sh
python3 -m bench.web_eval \
  --project anserini-evaluator/gpt-workspace \
  --prd anserini-evaluator/PRD-anserini-evaluator.md \
  --label gpt-evaluator-generated
```

Before starting the app, the evaluator builds setup context from the PRD, implementation README files, manifests, and any repo-local skills referenced there. The judge model can propose concrete setup commands from that context. The runner then executes only general allowlisted setup commands, such as package installs, project-local setup scripts, explicit environment assignments, downloads with project-local output paths, and smoke-check commands. There are no task-specific installers in `web_eval`; skipped commands are recorded with a reason.

For each feature, the browser layer first runs the scripted evidence steps, captures page text, ARIA, screenshots, errors, and visible interactive elements, then optionally asks the judge model for a short follow-up browser plan. This lightweight agentic pass helps avoid false negatives when the UI uses different labels or layouts. The final verdict receives the collected browser evidence plus setup context/results, but it must still judge from evidence rather than assume success.

Useful options:

- `--base-url http://127.0.0.1:3000` and `--no-start` when the app is already running
- `--dry-run` to skip LLM calls for judging/planning/generation where possible
- `--judge-model` or env `WEB_EVAL_JUDGE_MODEL`
- `--setup never` to skip README setup commands
- `--no-agentic-evidence` to use only scripted Playwright steps
- `--max-generated-features 8` to cap PRD-generated feature checks

Artifacts are written to `evals/<eval_id>/`:

- `summary.json`, `report.md`, `run.json`, `setup.json`, `setup-context.json`
- `generated-features.yaml` when `--features` is omitted
- `evidence/<feature>.json` plus raw scripted/agentic browser packets
- `judgments/<feature>.json`
- `screenshots/` and `jobs/` (browser layer)

Correctness is `passed / total * 100`; **uncertain** counts as not passed.

## CLI

Run one prompt against multiple model workspaces:

```sh
python -m bench.cli --prompt "Your task prompt" --models gpt claude gemini
```

Or read the prompt from a file:

```sh
python -m bench.cli --task-dir anserini-frontend --prompt-file anserini-frontend/PRDv2.md --models gpt claude gemini glm kimi minimax
```

Useful options:

- `--task-dir anserini-frontend`
- `--prompt-file path/to/prompt.txt`
- `--mode sequential|parallel`
- `--max-concurrency 2`
- `--timeout-seconds 1800` or `--timeout-seconds 0` for no per-model timeout
- `--retries 1`
- `--warmup`
- `--label e2e-bench-1`

The CLI flow is:

1. It reads the prompt from `--prompt` or `--prompt-file`.
2. It loads `*-workspace/bench.toml` files from `--task-dir`, `PI_BENCH_TASK_DIR`, or the default `anserini-frontend`.
3. It runs preflight checks for the selected model keys, the workspace folders, the `pi` executable, a sandbox backend (`sandbox-exec` or `bwrap`), and any declared `required_skills`.
4. It symlinks task-local files matching `PRD*.md`, `TASK*.md`, `task*.md`, or `prompt*.md` into every configured workspace.
5. It creates a fresh `runs/<run_id>/` directory and writes the exact prompt to `prompt.txt`.
6. It starts one Pi subprocess per selected workspace, either sequentially or in parallel with `--max-concurrency`.
7. It writes per-model logs and a combined summary when the run finishes.

For each selected model, `bench.toml` is converted into Pi CLI flags. This config:

```toml
provider = "anthropic"
model = "claude-sonnet-4-6"
thinking = "high"
tools = ["read", "bash", "edit", "write", "grep", "find", "ls"]
```

becomes:

```text
pi --mode json --print --no-session --provider anthropic --model claude-sonnet-4-6 --thinking high --tools read,bash,edit,write,grep,find,ls <prompt>
```

The runner sets the subprocess working directory to that model's workspace, so task files such as `./PRDv2.md` or `./PRD-anserini-evaluator.md` and any files the agent creates are local to that model. It also loads this project's `.env` into the subprocess environment before launching Pi.

On macOS, each subprocess is wrapped with `sandbox-exec`. On Linux, each subprocess is wrapped with `bwrap`. The generated sandbox profile denies reads and writes to the other configured model workspaces plus `.codex-private/`.

Artifacts are written to:

```text
runs/<run_id>/
```

Each run includes:

- `prompt.txt`: the prompt used for the run
- `<model>/stdout.log`: readable assistant output and tool markers
- `<model>/stderr.log`: Pi stderr
- `<model>/events.jsonl`: raw Pi JSON events
- `<model>/result.json`: status, timing, command, paths, attempts, and token metrics for that model
- `<model>/workspace.sb`: generated macOS sandbox profile (when using `sandbox-exec`)
- `<model>/workspace.bwrap.json`: generated Linux sandbox command metadata (when using `bwrap`)
- `summary.json`: full machine-readable benchmark summary
- `summary.csv`: compact table for spreadsheets
- `summary.md`: compact Markdown summary

Statuses are process-level statuses. `completed` means Pi exited with code `0`; `failed` means a non-zero exit; `timeout` means the process exceeded `--timeout-seconds`. `--retries` reruns only failed or timed-out model subprocesses, and the final artifact files contain the last attempt's logs.

`--warmup` performs a short, unreported pre-run for each selected model before the measured run. Warmup logs are saved as `warmup.*` files inside each model artifact directory, but the benchmark summary uses the measured run.

## Web UI

Start the GUI server:

```sh
uvicorn bench.web:app --port 4010
```

Open:

```text
http://127.0.0.1:4010
```

The UI can:

- pick configured model workspaces
- run models sequentially or in parallel
- stream stdout/stderr side by side
- show final duration and any parsed token metrics
- load recent run history

## Metrics

Pi Bench records wall-clock duration and process status for every model. New runs execute Pi in JSON event mode and parse final assistant `usage` fields from `message_end` events. Raw Pi events are saved per model as `events.jsonl`, while readable output remains in `stdout.log`.

Older runs made before JSON event parsing may show zero token and cost fields because they were run with `--no-session` and text output did not include usage.

## Requirements

- Python 3.11+
- Pi coding agent available on `PATH`
- workspace sandbox support: `sandbox-exec` on macOS or `bwrap` (bubblewrap) on Linux
- provider API keys configured for the models you run
- any task-specific Pi skills installed or installable by the agent. The current Anserini PRDs ask agents to use an `anserini-fatjar` skill.

Install Python server dependencies:

```sh
pip install -r requirements.txt
```
