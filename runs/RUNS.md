# Run Directory Index

The raw run directory names are immutable runner IDs. Use this index for the
human-readable names.

| Descriptive name | Run directory | Status |
| --- | --- | --- |
| `frontend-rewrite-initial-partial-20260606` | `20260606-022816-a9c30e71` | committed; initial frontend rerun with `gpt`, `claude`, `gemini` |
| `frontend-rewrite-retry-20260606` | `20260606-025317-bf2a16d6` | committed; retry from `deepseek` onward, 5 completed |
| `evaluator-rewrite-20260606` | `20260606-034617-89c17fd6` | committed; 8 completed |
| `nfcorpus-repro-rewrite-20260606` | `20260606-052357-45367bb5` | committed; 5 completed, 3 timed out |
| `frontend-no-rewrite-20260606` | `20260606-075935-8c97f66a` | committed; 8 completed |
| `evaluator-no-rewrite-20260606` | `20260606-090331-45565310` | committed; retry run, 6 completed, 2 timed out |
| `nfcorpus-repro-no-rewrite-20260606` | `20260606-110743-25a0f9b9` | committed; 6 completed, 2 timed out |

## Timeout Analysis

All committed timeout records were inspected in `stdout.log`, `stderr.log`,
and `events.jsonl`. None showed evidence of a runner crash, provider crash,
port collision, stale subprocess, or cleanup failure. The shared stderr across
the timeout records was only the expected sandbox warning that repo-root
`AGENTS.md` could not be read.

| Run directory | Model | Last observed activity | Assessment |
| --- | --- | --- | --- |
| `20260606-052357-45367bb5` | `claude` | Passed local tests, then started `docker build -t nfcorpus-workbench:local .` | Agent-side over-validation; Docker build consumed remaining run budget |
| `20260606-052357-45367bb5` | `minimax` | Ran NFCorpus evaluation successfully, then continued fixing metric-name comparison logic | Agent-side overrun after core reproduction work |
| `20260606-052357-45367bb5` | `mimo` | Had app/server checks working, then continued Playwright/browser test debugging | Agent-side test loop |
| `20260606-090331-45565310` | `claude` | Searched globally with `find / -maxdepth 6 -name "anserini-*-fatjar.jar"` | Agent-side path search mistake |
| `20260606-090331-45565310` | `minimax` | Completed CACM checks, then tried a large MS MARCO validation/download | Agent-side over-validation |
| `20260606-110743-25a0f9b9` | `minimax` | Rewrote Dockerfile and ran `docker build -t nfcorpus-workbench:dev` | Agent-side Docker build overrun |
| `20260606-110743-25a0f9b9` | `mimo` | Debugged local API/evaluation flow on port `15432` | Agent-side debugging loop |

The `1800s` timeout is the runner's per-model wall-clock cap, not a per-command
cap. Docker builds are especially risky inside that budget because cold images,
network downloads, JDK/Node installs, platform emulation, and BuildKit startup
can consume the remaining time after implementation and tests have already run.
