from __future__ import annotations

import os
import tomllib
from pathlib import Path

from bench.schemas import WorkspaceConfig


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TASK_DIR_NAME = "anserini-frontend"
RUNS_DIR = ROOT_DIR / "runs"
WORKSPACE_CONFIG_NAME = "bench.toml"
SHARED_TASK_GLOBS = ("PRD*.md", "TASK*.md", "task*.md", "prompt*.md")


def resolve_workspaces_dir(task_dir: str | Path | None = None) -> Path:
    selected = task_dir or os.environ.get("PI_BENCH_TASK_DIR") or DEFAULT_TASK_DIR_NAME
    path = Path(selected)
    return path if path.is_absolute() else ROOT_DIR / path


WORKSPACES_DIR = resolve_workspaces_dir()


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def load_workspace_configs(task_dir: str | Path | None = None) -> dict[str, WorkspaceConfig]:
    configs: dict[str, WorkspaceConfig] = {}
    workspaces_dir = resolve_workspaces_dir(task_dir)
    if not workspaces_dir.exists():
        return configs

    for workspace in sorted(workspaces_dir.iterdir()):
        if not workspace.is_dir() or not workspace.name.endswith("-workspace"):
            continue
        config_path = workspace / WORKSPACE_CONFIG_NAME
        if not config_path.exists():
            continue

        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
        key = workspace.name.removesuffix("-workspace")
        configs[key] = WorkspaceConfig(
            key=key,
            name=parsed.get("name", workspace.name),
            path=str(workspace),
            model=parsed.get("model", ""),
            provider=parsed.get("provider"),
            thinking=parsed.get("thinking"),
            system_prompt=parsed.get("system_prompt"),
            append_system_prompt=_as_str_list(parsed.get("append_system_prompt")),
            tools=_as_str_list(parsed.get("tools")),
            required_skills=_as_str_list(parsed.get("required_skills")),
        )
    return configs


def discover_shared_task_files(task_dir: str | Path | None = None) -> list[Path]:
    files: dict[str, Path] = {}
    workspaces_dir = resolve_workspaces_dir(task_dir)
    for pattern in SHARED_TASK_GLOBS:
        for path in workspaces_dir.glob(pattern):
            if path.is_file():
                files[path.name] = path
    return [files[name] for name in sorted(files)]


def load_project_env() -> dict[str, str]:
    env = dict(os.environ)
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return env
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env[key] = value
    return env
