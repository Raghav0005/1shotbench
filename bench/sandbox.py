from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from bench.schemas import WorkspaceConfig


SANDBOX_PROFILE_NAME = "workspace.sb"
BWRAP_ARTIFACT_NAME = "workspace.bwrap.json"


def resolve_sandbox_backend() -> str | None:
    if shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if shutil.which("bwrap") and bwrap_is_functional():
        return "bwrap"
    return None


def sandbox_preflight_error() -> str | None:
    if resolve_sandbox_backend() is not None:
        return None
    if shutil.which("bwrap") and not bwrap_is_functional():
        return (
            "`bwrap` is installed but cannot create a sandbox "
            "(user namespaces or setuid bubblewrap may be unavailable)."
        )
    return (
        "`sandbox-exec` (macOS) or `bwrap` (Linux) is required; "
        "workspace isolation cannot be enforced."
    )


def _bwrap_base_args() -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return []
    return [
        bwrap,
        "--unshare-user-try",
        "--die-with-parent",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--bind",
        "/",
        "/",
    ]


def bwrap_is_functional() -> bool:
    args = _bwrap_base_args()
    if not args:
        return False
    proc = subprocess.run(
        [*args, "--", "true"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def denied_workspace_paths(
    *,
    root_dir: Path,
    workspaces: dict[str, WorkspaceConfig],
    workspace: WorkspaceConfig,
) -> list[Path]:
    workspace_path = Path(workspace.path).resolve()
    private_path = (root_dir / ".codex-private").resolve()
    private_path.mkdir(parents=True, exist_ok=True)
    allowed_paths = [workspace_path]

    local_skills = (root_dir / ".agents" / "skills").resolve()
    if local_skills.exists():
        allowed_paths.append(local_skills)

    denied_paths = _denied_project_paths(root_dir.resolve(), allowed_paths)
    if private_path not in denied_paths:
        denied_paths.append(private_path)
    return _dedupe_paths(denied_paths)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_allowed_or_contains_allowed(path: Path, allowed_paths: list[Path]) -> bool:
    return any(path == allowed or _is_relative_to(path, allowed) or _is_relative_to(allowed, path) for allowed in allowed_paths)


def _denied_project_paths(root_dir: Path, allowed_paths: list[Path]) -> list[Path]:
    denied: list[Path] = []

    def walk(path: Path) -> None:
        if not path.exists():
            return
        if not _is_allowed_or_contains_allowed(path, allowed_paths):
            denied.append(path.resolve())
            return
        if any(path == allowed or _is_relative_to(path, allowed) for allowed in allowed_paths):
            return
        if path.is_dir():
            for child in sorted(path.iterdir()):
                walk(child.resolve())

    for child in sorted(root_dir.iterdir()):
        walk(child.resolve())
    return denied


def apply_workspace_sandbox(
    *,
    root_dir: Path,
    workspaces: dict[str, WorkspaceConfig],
    workspace: WorkspaceConfig,
    model_dir: Path,
    command: list[str],
) -> list[str]:
    denied_paths = denied_workspace_paths(
        root_dir=root_dir,
        workspaces=workspaces,
        workspace=workspace,
    )
    if not denied_paths:
        return command

    backend = resolve_sandbox_backend()
    if backend == "sandbox-exec":
        return _wrap_with_sandbox_exec(
            denied_paths=denied_paths,
            model_dir=model_dir,
            command=command,
        )
    if backend == "bwrap":
        return _wrap_with_bwrap(
            denied_paths=denied_paths,
            model_dir=model_dir,
            command=command,
        )
    return command


def _wrap_with_sandbox_exec(
    *,
    denied_paths: list[Path],
    model_dir: Path,
    command: list[str],
) -> list[str]:
    sandbox_exe = shutil.which("sandbox-exec")
    if not sandbox_exe:
        return command

    profile_path = model_dir / SANDBOX_PROFILE_NAME
    lines = ["(version 1)", "(allow default)"]
    for denied_path in denied_paths:
        quoted = json.dumps(str(denied_path))
        selector = "subpath" if denied_path.is_dir() else "literal"
        lines.append(f"(deny file-read* ({selector} {quoted}))")
        lines.append(f"(deny file-write* ({selector} {quoted}))")
    profile_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [sandbox_exe, "-f", str(profile_path), *command]


def _wrap_with_bwrap(
    *,
    denied_paths: list[Path],
    model_dir: Path,
    command: list[str],
) -> list[str]:
    args = _bwrap_base_args()
    if not args:
        return command

    overlay_dir = Path(tempfile.mkdtemp(prefix=f"{model_dir.name}-sandbox-deny-overlay-")).resolve()
    empty_file = overlay_dir / "empty-file"
    empty_file.touch()
    for denied_path in denied_paths:
        if not denied_path.exists():
            denied_path.mkdir(parents=True, exist_ok=True)
        overlay_source = overlay_dir if denied_path.is_dir() else empty_file
        args.extend(["--ro-bind", str(overlay_source), str(denied_path)])

    wrapped = [*args, "--", *command]
    artifact_path = model_dir / BWRAP_ARTIFACT_NAME
    artifact_path.write_text(
        json.dumps(
            {
                "backend": "bwrap",
                "denied_paths": [str(path) for path in denied_paths],
                "overlay_dir": str(overlay_dir),
                "command": wrapped,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return wrapped
