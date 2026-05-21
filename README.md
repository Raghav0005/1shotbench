# Pi Bench

Pi Bench runs the same task prompt through multiple Pi agent workspaces so you can compare how different models behave under the same harness.

The old Codex proxy path has been removed. Each model now runs through the `pi` CLI directly, using a small `bench.toml` file inside its workspace.

## Workspace Layout

Model workspaces live under:

```text
agent-workspaces/
  gpt-workspace/
    bench.toml
  claude-workspace/
    bench.toml
  gemini-workspace/
    bench.toml
```

Each workspace config supports:

```toml
name = "GPT workspace"
provider = "openai-codex"
model = "gpt-5.4"
thinking = "high"
tools = ["read", "bash", "edit", "write", "grep", "find", "ls"]
required_skills = ["install-anserini-fatjar", "anserini-cli", "anserini-reproduction"]

# Optional:
# system_prompt = "Custom system prompt"
# append_system_prompt = ["extra instructions", "path/to/file.md"]
```

The runner executes Pi from the workspace directory with:

```text
pi --print --no-session --provider <provider> --model <model> [prompt]
```

Root-level task files matching `PRD*.md`, `TASK*.md`, `task*.md`, or `prompt*.md` are symlinked into every model workspace before each run. For example, `PRDv2.md` is available to every agent as `./PRDv2.md` from inside its workspace.

## Workspace Isolation

Pi Bench runs each model from its own workspace directory and, on macOS, wraps each Pi subprocess with `sandbox-exec`. The generated sandbox profile allows normal process behavior but denies file reads and writes against the other configured model workspace directories.

That means a run from `glm-workspace` cannot inspect or modify `kimi-workspace`, `gpt-workspace`, and the other sibling model workspaces. If `sandbox-exec` is unavailable, preflight fails because that isolation cannot be enforced.

This is workspace isolation, not a full container. Agents can still use allowed tools and the network according to the host environment and Pi configuration.

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

`PRDv2.md` asks the agent to use the public `anserini-fatjar` skill and to install it automatically if it is missing and the source is reachable. For fully reproducible runs, preinstall the same skill for every model before benchmarking, or include the exact install source in the task prompt.

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

## CLI

Run one prompt against multiple model workspaces:

```sh
python -m bench.cli --prompt "Your task prompt" --models gpt claude gemini
```

Useful options:

- `--prompt-file path/to/prompt.txt`
- `--mode sequential|parallel`
- `--max-concurrency 2`
- `--timeout-seconds 1800`
- `--retries 1`
- `--warmup`
- `--label e2e-bench-1`

Artifacts are written to:

```text
runs/<run_id>/
```

Each run includes per-model stdout/stderr logs, per-model result JSON, and `summary.json`, `summary.csv`, and `summary.md`.

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

Pi Bench records wall-clock duration and process status for every model. Token fields are populated only when Pi or a provider prints a line matching:

```text
Token usage: total=<n> input=<n> output=<n> (reasoning <n>)
```

If that line is absent, token and cost fields remain zero. This keeps the benchmark agent-agnostic and avoids the previous provider proxy.

## Requirements

- Python 3.11+
- Pi coding agent available on `PATH`
- provider API keys configured for the models you run
- any task-specific Pi skills installed or installable by the agent. `PRDv2.md` currently asks agents to use an `anserini-fatjar` skill.

Install Python server dependencies:

```sh
pip install -r requirements.txt
```
