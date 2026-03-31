from __future__ import annotations

import tomllib
from pathlib import Path

from bench.schemas import WorkspaceConfig


ROOT_DIR = Path(__file__).resolve().parent.parent
WORKSPACES_DIR = ROOT_DIR / "agent-workspaces"
RUNS_DIR = ROOT_DIR / "runs"
USAGE_LOG_PATH = ROOT_DIR / "usage_logs" / "usage.jsonl"


def load_workspace_configs() -> dict[str, WorkspaceConfig]:
    configs: dict[str, WorkspaceConfig] = {}
    if not WORKSPACES_DIR.exists():
        return configs

    for workspace in sorted(WORKSPACES_DIR.iterdir()):
        if not workspace.is_dir() or not workspace.name.endswith("-workspace"):
            continue
        config_path = workspace / ".codex" / "config.toml"
        if not config_path.exists():
            continue

        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
        key = workspace.name.removesuffix("-workspace")
        configs[key] = WorkspaceConfig(
            key=key,
            name=workspace.name,
            path=str(workspace),
            model=parsed.get("model", ""),
            provider=parsed.get("model_provider"),
        )
    return configs
