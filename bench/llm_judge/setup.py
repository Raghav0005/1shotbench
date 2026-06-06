from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bench.config import ROOT_DIR, load_project_env


@dataclass
class SetupCommandResult:
    command: str
    cwd: str
    status: str
    returncode: int | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None
    reason: str | None = None


@dataclass
class PlannedSetupCommand:
    command: str
    cwd: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreparedCommand:
    argv: list[str]
    stdout_path: Path | None = None
    stdout_append: bool = False
    error: str | None = None


@dataclass
class DownloadRecovery:
    argv: list[str]
    proc: subprocess.CompletedProcess[str]
    old_version: str
    release: str
    metadata_url: str


@dataclass
class MavenDownloadRecord:
    argv: list[str]
    version: str
    output_path: Path
    metadata_url: str


def collect_setup_context(project_path: Path, prd_path: Path | None = None, *, max_chars: int = 36000) -> dict[str, Any]:
    project_path = project_path.resolve()
    context: dict[str, Any] = {
        "project_path": str(project_path),
        "prd_path": str(prd_path.resolve()) if prd_path else None,
        "readmes": [],
        "manifests": [],
        "referenced_skills": [],
        "setup_hints": [],
    }
    text_for_skill_refs: list[str] = []

    if prd_path and prd_path.exists():
        text = _read_limited(prd_path, max_chars=12000)
        context["prd"] = {"path": str(prd_path.resolve()), "text": text}
        context["setup_hints"].extend(_setup_hints_from_text("prd", prd_path, text))
        text_for_skill_refs.append(text)

    for readme in _find_readmes(project_path):
        text = _read_limited(readme, max_chars=12000)
        context["readmes"].append({"path": str(readme.resolve()), "text": text})
        context["setup_hints"].extend(_setup_hints_from_text("readme", readme, text))
        text_for_skill_refs.append(text)

    for manifest in _find_manifests(project_path):
        text = _read_limited(manifest, max_chars=8000)
        context["manifests"].append({"path": str(manifest.resolve()), "text": text})
        text_for_skill_refs.append(text)

    skill_names = _extract_skill_names("\n".join(text_for_skill_refs))
    for skill_name in skill_names:
        skill_path = _resolve_skill_path(skill_name)
        if skill_path:
            skill_text = _read_limited(skill_path, max_chars=16000)
            context["referenced_skills"].append(
                {"name": skill_name, "path": str(skill_path), "text": skill_text}
            )
            context["setup_hints"].extend(_setup_hints_from_text(f"skill:{skill_name}", skill_path, skill_text))

    return _truncate_context(context, max_chars=max_chars)


def run_project_setup(
    project_path: Path,
    output_dir: Path,
    *,
    mode: str = "auto",
    timeout_seconds: int = 900,
    planned_commands: list[PlannedSetupCommand] | None = None,
    setup_context: dict[str, Any] | None = None,
) -> list[SetupCommandResult]:
    """Run general setup commands inferred from project-visible instructions.

    The evaluator should not contain task-specific installers. It can run common
    dependency setup automatically and execute explicit or LLM-planned setup
    commands only after a general allowlist check.
    """
    project_path = project_path.resolve()
    output_dir = output_dir.resolve()
    results: list[SetupCommandResult] = []
    if mode == "never":
        _write_setup_artifact(output_dir, results, planned_commands or [], setup_context)
        return results
    if mode not in {"auto"}:
        raise ValueError("setup mode must be 'auto' or 'never'")

    env = load_project_env()
    original_process_env = {key: os.environ.get(key) for key in env}
    exported_keys: set[str] = set()
    invalid_export_keys: set[str] = set()
    setup_created_files: set[Path] = set()
    maven_downloads: dict[Path, MavenDownloadRecord] = {}

    dep_result = _ensure_node_dependencies(project_path, env=env, timeout_seconds=timeout_seconds)
    if dep_result:
        results.append(dep_result)

    commands = planned_commands if planned_commands is not None else [
        PlannedSetupCommand(command, str(cwd)) for command, cwd in discover_readme_setup_commands(project_path)
    ]

    for planned in commands:
        cwd = _resolve_cwd(project_path, planned.cwd)
        command = planned.command.strip()
        if not command:
            continue
        export_result = _apply_supported_export(command, cwd, env)
        if export_result:
            exported_key = _export_key(command)
            if exported_key:
                exported_keys.add(exported_key)
            results.append(export_result)
            continue
        prepared = _prepare_command(command, cwd, env, project_path)
        if prepared.error:
            results.append(SetupCommandResult(command, str(cwd), "skipped", reason=prepared.error))
            continue
        argv = _normalize_setup_argv(prepared.argv)
        allowed, reason = _is_allowed_setup_command(argv, project_path, cwd)
        if not allowed:
            results.append(SetupCommandResult(command, str(cwd), "skipped", reason=reason))
            continue
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                SetupCommandResult(
                    command=command,
                    cwd=str(cwd),
                    status="failed",
                    reason=f"timed out after {timeout_seconds}s",
                    stdout_tail=_tail(exc.stdout if isinstance(exc.stdout, str) else None),
                    stderr_tail=_tail(exc.stderr if isinstance(exc.stderr, str) else None),
                )
            )
            continue
        if proc.returncode == 0 and prepared.stdout_path:
            _write_redirected_stdout(prepared.stdout_path, proc.stdout or "", append=prepared.stdout_append)
        if proc.returncode != 0 and _grep_verification_matches(argv, cwd):
            proc = subprocess.CompletedProcess(argv, 0, proc.stdout, proc.stderr)
        if proc.returncode != 0:
            recovery = _recover_maven_download(argv, cwd, env, proc, timeout_seconds)
            if recovery:
                proc = recovery.proc
                argv = recovery.argv
                if proc.returncode == 0:
                    _update_version_env_after_recovery(env, recovery.release, recovery.old_version)
        if proc.returncode != 0:
            recovery = _recover_maven_java_classpath(argv, cwd, env, proc, timeout_seconds, maven_downloads)
            if recovery:
                proc = recovery.proc
                argv = recovery.argv
                if proc.returncode == 0:
                    _update_version_env_after_recovery(env, recovery.release, recovery.old_version)
        status = "completed" if proc.returncode == 0 else "failed"
        failure_reason = planned.reason
        if status == "completed":
            post_failure = _post_command_failure_reason(argv, cwd, proc.stdout, proc.stderr)
            if post_failure:
                status = "failed"
                failure_reason = post_failure
        if status == "completed":
            downloaded = _download_output_path(argv, cwd)
            if downloaded:
                setup_created_files.add(downloaded)
                _record_maven_download(argv, cwd, downloaded, maven_downloads)
        else:
            invalid_export_keys.update(_invalidated_export_keys(command, cwd, env, setup_created_files))
        results.append(
            SetupCommandResult(
                command=command,
                cwd=str(cwd),
                status=status,
                returncode=proc.returncode,
                stdout_tail=_tail(proc.stdout),
                stderr_tail=_tail(proc.stderr),
                reason=failure_reason,
            )
        )
    _commit_setup_exports(exported_keys, invalid_export_keys, env, original_process_env, setup_created_files)
    _write_setup_artifact(output_dir, results, commands, setup_context)
    return results


def discover_readme_setup_commands(project_path: Path) -> list[tuple[str, Path]]:
    commands: list[tuple[str, Path]] = []
    for readme in _find_readmes(project_path):
        text = readme.read_text(encoding="utf-8", errors="replace")
        for command in _extract_setup_commands(text):
            commands.append((command, readme.parent))
    return _dedupe_commands(commands)


def commands_from_json(raw_commands: Any, project_path: Path) -> list[PlannedSetupCommand]:
    commands: list[PlannedSetupCommand] = []
    if not isinstance(raw_commands, list):
        return commands
    for item in raw_commands:
        if isinstance(item, str):
            command = item
            cwd = None
            reason = None
        elif isinstance(item, dict):
            command = str(item.get("command") or "")
            cwd = str(item.get("cwd")) if item.get("cwd") else None
            reason = str(item.get("reason")) if item.get("reason") else None
        else:
            continue
        if not command.strip():
            continue
        resolved = _resolve_cwd(project_path.resolve(), cwd)
        try:
            resolved.relative_to(project_path.resolve())
        except ValueError:
            continue
        command = command.strip()
        resolved = _repair_setup_cwd(project_path.resolve(), command, resolved)
        commands.append(PlannedSetupCommand(command=command, cwd=str(resolved), reason=reason))
    return commands


def _repair_setup_cwd(project_path: Path, command: str, cwd: Path) -> Path:
    argv = _split_command(command)
    if not argv:
        return cwd
    exe = argv[0]
    if exe in {"npm", "pnpm", "yarn"} and len(argv) >= 2 and argv[1] in {"install", "ci"}:
        if (cwd / "package.json").is_file():
            return cwd
        package_dirs = _package_dirs(project_path)
        if len(package_dirs) == 1:
            return package_dirs[0]
    return cwd


def _package_dirs(project_path: Path) -> list[Path]:
    dirs: list[Path] = []
    for path in sorted(project_path.glob("**/package.json")):
        if any(part in {"node_modules", ".git", "dist", "build"} for part in path.parts):
            continue
        dirs.append(path.parent.resolve())
    return dirs


def _ensure_node_dependencies(project_path: Path, *, env: dict[str, str], timeout_seconds: int) -> SetupCommandResult | None:
    package_json = project_path / "package.json"
    node_modules = project_path / "node_modules"
    if not package_json.exists() or node_modules.exists():
        return None
    if (project_path / "package-lock.json").exists():
        argv = ["npm", "ci"]
        command = "npm ci"
    else:
        argv = ["npm", "install"]
        command = "npm install"
    proc = subprocess.run(
        argv,
        cwd=str(project_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return SetupCommandResult(
        command=command,
        cwd=str(project_path),
        status="completed" if proc.returncode == 0 else "failed",
        returncode=proc.returncode,
        stdout_tail=_tail(proc.stdout),
        stderr_tail=_tail(proc.stderr),
    )


def _apply_supported_export(command: str, cwd: Path, env: dict[str, str]) -> SetupCommandResult | None:
    match = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.+)$", command.strip())
    if not match:
        return None
    key = match.group(1)
    raw_value = match.group(2).split("#", 1)[0].strip().strip('"').strip("'")
    value = _expand_env_value(raw_value, cwd, env)
    candidate_path = (cwd / value).resolve()
    if value and not Path(value).is_absolute() and candidate_path.exists():
        value = str(candidate_path)
    env[key] = value
    return SetupCommandResult(command, str(cwd), "completed", reason=f"set {key}")


def _expand_env_value(value: str, cwd: Path, env: dict[str, str]) -> str:
    value = value.replace("$PWD", str(cwd)).replace("${PWD}", str(cwd))
    for key, env_value in env.items():
        value = value.replace(f"${key}", env_value).replace(f"${{{key}}}", env_value)
    return value


def _export_key(command: str) -> str | None:
    match = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", command.strip())
    return match.group(1) if match else None


def _referenced_env_keys(command: str) -> set[str]:
    keys = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", command))
    keys.update(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", command))
    return keys


def _invalidated_export_keys(command: str, cwd: Path, env: dict[str, str], setup_created_files: set[Path]) -> set[str]:
    invalid: set[str] = set()
    for key in _referenced_env_keys(command):
        raw_value = env.get(key)
        if not raw_value:
            continue
        path = (cwd / raw_value).resolve() if not Path(raw_value).is_absolute() else Path(raw_value).resolve()
        if path in setup_created_files:
            invalid.add(key)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
    return invalid


def _commit_setup_exports(
    exported_keys: set[str],
    invalid_export_keys: set[str],
    env: dict[str, str],
    original_process_env: dict[str, str | None],
    setup_created_files: set[Path],
) -> None:
    for key in exported_keys:
        if key in invalid_export_keys:
            original = original_process_env.get(key)
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
            continue
        if key in env:
            os.environ[key] = env[key]


def _download_output_path(argv: list[str], cwd: Path) -> Path | None:
    output_path = None
    for index, part in enumerate(argv):
        if part in {"-o", "-O", "--output", "--output-document"} and index + 1 < len(argv):
            output_path = argv[index + 1]
            break
        if part.startswith("--output=") or part.startswith("--output-document="):
            output_path = part.split("=", 1)[1]
            break
        if argv and argv[0] == "curl" and part.startswith("-") and "o" in part[1:] and index + 1 < len(argv):
            output_path = argv[index + 1]
            break
    if not output_path:
        return None
    return (cwd / output_path).resolve()


def _remove_setup_created_files(paths: set[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _looks_like_usage_only_success(argv: list[str], stdout: str | None, stderr: str | None) -> bool:
    if not argv or argv[0] != "java":
        return False
    output = ((stdout or "") + "\n" + (stderr or "")).strip()
    if not output:
        return False
    lowered = output.lower()
    usage_markers = ("usage:", "example:", "options:", "required option")
    has_usage = any(marker in lowered for marker in usage_markers)
    has_completion_signal = any(
        marker in lowered
        for marker in (
            "total run time",
            "completed",
            "success",
            "wrote",
            "written",
            "downloaded",
            "index folder already exists",
        )
    )
    return has_usage and not has_completion_signal


def _post_command_failure_reason(argv: list[str], cwd: Path, stdout: str | None, stderr: str | None) -> str | None:
    if _looks_like_usage_only_success(argv, stdout, stderr):
        return "command exited 0 but appeared to print CLI usage/help instead of completing setup"
    if argv and argv[0] == "java":
        output = ((stdout or "") + "\n" + (stderr or "")).strip()
        if re.search(r"(^|\n)\s*(error|exception):\s", output, flags=re.IGNORECASE):
            return "command exited 0 but emitted an error message"
        declared_output = _declared_output_path(argv, cwd)
        if declared_output and (not declared_output.is_file() or declared_output.stat().st_size == 0):
            return f"command exited 0 but did not create non-empty output file: {declared_output}"
    return None


def _declared_output_path(argv: list[str], cwd: Path) -> Path | None:
    for index, part in enumerate(argv):
        if part in {"-output", "--output", "-o"} and index + 1 < len(argv):
            candidate = Path(argv[index + 1])
            return candidate if candidate.is_absolute() else (cwd / candidate).resolve()
    return None


def _extract_setup_commands(markdown: str) -> list[str]:
    commands: list[str] = []
    active_heading = ""
    in_setup_section = False
    in_fence = False
    fence_lines: list[str] = []
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading and not in_fence:
            active_heading = heading.group(2).strip().lower()
            in_setup_section = any(
                token in active_heading
                for token in (
                    "install",
                    "setup",
                    "getting started",
                    "quickstart",
                    "prerequisite",
                    "run",
                    "runtime",
                    "download",
                    "smoke",
                    "verify",
                    "workflow",
                    "completion",
                )
            )
            continue
        if line.strip().startswith("```"):
            if in_fence:
                if in_setup_section:
                    commands.extend(_commands_from_block("\n".join(fence_lines)))
                fence_lines = []
                in_fence = False
            else:
                in_fence = True
                fence_lines = []
            continue
        if in_fence:
            fence_lines.append(line)
    return commands


def _commands_from_block(block: str) -> list[str]:
    commands: list[str] = []
    pending = ""
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("$"):
            line = line[1:].strip()
        if pending:
            line = f"{pending} {line}"
        if line.endswith("\\"):
            pending = line[:-1].strip()
            continue
        pending = ""
        if not _looks_like_setup_command(line):
            continue
        if _command_has_unsupported_setup_syntax(line):
            continue
        if _looks_destructive(line):
            continue
        commands.append(line)
    return commands


def _setup_hints_from_text(source_type: str, path: Path, text: str) -> list[dict[str, Any]]:
    commands = _extract_setup_commands(text)
    if not commands:
        return []
    return [
        {
            "source_type": source_type,
            "path": str(path.resolve()),
            "commands": commands[:12],
        }
    ]


def _is_allowed_setup_command(argv: list[str], project_path: Path, cwd: Path) -> tuple[bool, str | None]:
    if not argv:
        return False, "could not parse command"
    exe = argv[0]
    if exe in {"npm", "pnpm", "yarn"}:
        if len(argv) >= 2 and argv[1] in {"install", "ci"}:
            return True, None
        if len(argv) >= 3 and argv[1] == "run" and _setup_script_name(argv[2]):
            return True, None
        return False, "npm/pnpm/yarn command is not an install or setup script"
    if exe == "npx":
        args = _npx_args_without_yes(argv)
        if 3 <= len(args) <= 4 and args[1:3] == ["playwright", "install"]:
            if len(args) == 3 or args[3] in {"chromium", "firefox", "webkit"}:
                return True, None
        return False, "npx command is not an allowed Playwright browser install"
    if exe in {"pip", "pip3"}:
        if len(argv) >= 4 and argv[1] == "install" and argv[2] == "-r":
            return _path_stays_in_project(argv[3], project_path, cwd)
        return False, "pip command is not a requirements install"
    if exe in {"python", "python3"}:
        if len(argv) >= 5 and argv[1:4] == ["-m", "pip", "install"] and "-r" in argv:
            req_index = argv.index("-r") + 1
            if req_index < len(argv):
                return _path_stays_in_project(argv[req_index], project_path, cwd)
        if len(argv) >= 2 and _setup_script_path(argv[1], project_path, cwd, suffixes={".py"}):
            return True, None
        return False, "python command is not an allowed setup/install command"
    if exe in {"bash", "sh"}:
        if len(argv) >= 2 and _setup_script_path(argv[1], project_path, cwd, suffixes={".sh"}):
            return True, None
        return False, "shell command does not target an allowed setup script"
    if exe == "node":
        if len(argv) >= 2 and _setup_script_path(argv[1], project_path, cwd, suffixes={".js", ".mjs", ".cjs"}):
            return True, None
        return False, "node command does not target an allowed setup script"
    if exe in {"curl", "wget"}:
        return _is_allowed_download_command(argv, project_path, cwd)
    if exe == "grep":
        return _is_allowed_grep_command(argv, project_path, cwd)
    if exe in {"java", "test"}:
        return True, None
    if exe.startswith("./") and _setup_script_path(exe, project_path, cwd, suffixes={".sh", ".py", ".js", ".mjs", ".cjs"}):
        return True, None
    return False, "command is outside the setup allowlist"


def _is_allowed_download_command(argv: list[str], project_path: Path, cwd: Path) -> tuple[bool, str | None]:
    output_path = None
    for index, part in enumerate(argv):
        if part in {"-o", "-O", "--output", "--output-document"} and index + 1 < len(argv):
            output_path = argv[index + 1]
            break
        if part.startswith("--output=") or part.startswith("--output-document="):
            output_path = part.split("=", 1)[1]
            break
        if argv[0] == "curl" and part.startswith("-") and "o" in part[1:] and index + 1 < len(argv):
            output_path = argv[index + 1]
            break
    if output_path:
        return _path_stays_in_project(output_path, project_path, cwd)
    if argv[0] == "wget":
        return True, None
    return False, "download command must specify an output path"


def _is_allowed_grep_command(argv: list[str], project_path: Path, cwd: Path) -> tuple[bool, str | None]:
    if len(argv) != 4 or argv[1] != "-q":
        return False, "grep is only allowed as grep -q PATTERN FILE for setup verification"
    return _path_stays_in_project(argv[3], project_path, cwd)


def _grep_verification_matches(argv: list[str], cwd: Path) -> bool:
    if len(argv) != 4 or argv[0] != "grep" or argv[1] != "-q":
        return False
    file_path = (cwd / argv[3]).resolve()
    if not file_path.is_file():
        return False
    expected = _normalize_verification_text(_decode_shell_pattern(argv[2]))
    if not expected:
        return False
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    return any(expected in _normalize_verification_text(line) for line in lines)


def _normalize_verification_text(value: str) -> str:
    return " ".join(value.split())


def _record_maven_download(
    argv: list[str],
    cwd: Path,
    downloaded: Path,
    maven_downloads: dict[Path, MavenDownloadRecord],
) -> None:
    plan = _maven_download_recovery_plan(argv)
    if not plan:
        return
    maven_downloads[downloaded.resolve()] = MavenDownloadRecord(
        argv=list(argv),
        version=plan["version"],
        output_path=downloaded.resolve(),
        metadata_url=plan["metadata_url"],
    )


def _recover_maven_java_classpath(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    proc: subprocess.CompletedProcess[str],
    timeout_seconds: int,
    maven_downloads: dict[Path, MavenDownloadRecord],
) -> DownloadRecovery | None:
    if not argv or argv[0] != "java":
        return None
    output = ((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if "ClassNotFoundException" not in output and "Could not find or load main class" not in output:
        return None
    jar_path = _java_classpath_jar(argv, cwd)
    if not jar_path:
        return None
    record = maven_downloads.get(jar_path.resolve())
    if not record:
        return None
    metadata_proc = subprocess.run(
        ["curl", "-fsSL", record.metadata_url],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=min(timeout_seconds, 60),
        check=False,
    )
    if metadata_proc.returncode != 0:
        return None
    release = _release_from_maven_metadata(metadata_proc.stdout)
    if not release or release == record.version:
        return None
    download_argv = _rewrite_maven_download_argv(record.argv, record.version, release)
    download_proc = subprocess.run(
        download_argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if download_proc.returncode != 0:
        return None
    recovered_argv = _rewrite_maven_download_argv(argv, record.version, release)
    retry_proc = subprocess.run(
        recovered_argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    recovered_path = _download_output_path(download_argv, cwd)
    if recovered_path:
        maven_downloads[recovered_path.resolve()] = MavenDownloadRecord(
            argv=download_argv,
            version=release,
            output_path=recovered_path.resolve(),
            metadata_url=record.metadata_url,
        )
    return DownloadRecovery(
        argv=recovered_argv,
        proc=retry_proc,
        old_version=record.version,
        release=release,
        metadata_url=record.metadata_url,
    )


def _java_classpath_jar(argv: list[str], cwd: Path) -> Path | None:
    for index, part in enumerate(argv):
        if part in {"-cp", "-classpath", "--class-path"} and index + 1 < len(argv):
            first = argv[index + 1].split(os.pathsep, 1)[0]
            if first.endswith(".jar"):
                path = Path(first)
                return path.resolve() if path.is_absolute() else (cwd / path).resolve()
    return None


def _recover_maven_download(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    proc: subprocess.CompletedProcess[str],
    timeout_seconds: int,
) -> DownloadRecovery | None:
    if not argv or argv[0] not in {"curl", "wget"}:
        return None
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).lower()
    if "404" not in output and "not found" not in output:
        return None
    plan = _maven_download_recovery_plan(argv)
    if not plan:
        return None
    metadata_proc = subprocess.run(
        ["curl", "-fsSL", plan["metadata_url"]],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=min(timeout_seconds, 60),
        check=False,
    )
    if metadata_proc.returncode != 0:
        return None
    release = _release_from_maven_metadata(metadata_proc.stdout)
    if not release or release == plan["version"]:
        return None
    recovered_argv = _rewrite_maven_download_argv(argv, plan["version"], release)
    if recovered_argv == argv:
        return None
    retry_proc = subprocess.run(
        recovered_argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return DownloadRecovery(
        argv=recovered_argv,
        proc=retry_proc,
        old_version=plan["version"],
        release=release,
        metadata_url=plan["metadata_url"],
    )


def _maven_download_recovery_plan(argv: list[str]) -> dict[str, str] | None:
    url = _download_url_arg(argv)
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "repo1.maven.org":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[0] != "maven2":
        return None
    artifact = parts[-3]
    version = parts[-2]
    filename = parts[-1]
    if not version or version not in filename:
        return None
    metadata_path = "/" + "/".join(parts[:-2] + ["maven-metadata.xml"])
    metadata_url = f"{parsed.scheme}://{parsed.netloc}{metadata_path}"
    return {"metadata_url": metadata_url, "version": version, "artifact": artifact, "filename": filename}


def _download_url_arg(argv: list[str]) -> str | None:
    for part in reversed(argv):
        if part.startswith("http://") or part.startswith("https://"):
            return part
    return None


def _release_from_maven_metadata(metadata: str) -> str | None:
    release = re.search(r"<release>([^<]+)</release>", metadata)
    if release:
        return release.group(1).strip()
    latest = re.search(r"<latest>([^<]+)</latest>", metadata)
    if latest:
        return latest.group(1).strip()
    versions = re.findall(r"<version>([^<]+)</version>", metadata)
    return versions[-1].strip() if versions else None


def _rewrite_maven_download_argv(argv: list[str], old_version: str, new_version: str) -> list[str]:
    rewritten = list(argv)
    for index, part in enumerate(rewritten):
        if old_version in part:
            rewritten[index] = part.replace(old_version, new_version)
    return rewritten


def _update_version_env_after_recovery(env: dict[str, str], release: str, old_version: str) -> None:
    for key, value in list(env.items()):
        if key.endswith("_VERSION") and value == old_version:
            env[key] = release
            continue
        if old_version in value and ".jar" in value:
            env[key] = value.replace(old_version, release)


def _find_readmes(project_path: Path) -> list[Path]:
    return [path for path in sorted(project_path.glob("README*")) + sorted(project_path.glob("*/README*")) if path.is_file()]


def _find_manifests(project_path: Path) -> list[Path]:
    names = {"package.json", "requirements.txt", "pyproject.toml", "bench.toml", "vite.config.js", "next.config.js"}
    manifests: list[Path] = []
    for path in sorted(project_path.glob("**/*")):
        if not path.is_file() or path.name not in names:
            continue
        if any(part in {"node_modules", ".git", "dist", "build"} for part in path.parts):
            continue
        manifests.append(path)
        if len(manifests) >= 20:
            break
    return manifests


def _extract_skill_names(text: str) -> list[str]:
    names = set(re.findall(r"\$([A-Za-z0-9_.-]+)", text))
    names.update(re.findall(r"`([A-Za-z0-9_.-]+)`", text))
    names.update(re.findall(r'"([A-Za-z0-9_.-]+)"', text))
    return sorted(name for name in names if _resolve_skill_path(name))


def _resolve_skill_path(name: str) -> Path | None:
    candidates = [
        ROOT_DIR / ".agents" / "skills" / name / "SKILL.md",
        ROOT_DIR / ".pi" / "skills" / name / "SKILL.md",
        Path.home() / ".pi" / "agent" / "skills" / name / "SKILL.md",
        Path.home() / ".agents" / "skills" / name / "SKILL.md",
        Path.home() / ".codex" / "skills" / name / "SKILL.md",
        Path.home() / ".codex" / "skills" / ".system" / name / "SKILL.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _read_limited(path: Path, *, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def _truncate_context(context: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    encoded = json.dumps(context)
    if len(encoded) <= max_chars:
        return context
    context = dict(context)
    for key in ("readmes", "referenced_skills", "manifests"):
        items = []
        for item in context.get(key, []):
            item = dict(item)
            if "text" in item:
                item["text"] = item["text"][:3000] + "..."
            items.append(item)
        context[key] = items
    return context


def _resolve_cwd(project_path: Path, raw_cwd: str | None) -> Path:
    if not raw_cwd:
        return project_path
    cwd = Path(raw_cwd)
    if not cwd.is_absolute():
        cwd = project_path / cwd
    return cwd.resolve()


def _setup_script_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ("setup", "install", "prepare", "bootstrap", "postinstall"))


def _setup_script_path(raw_path: str, project_path: Path, cwd: Path, *, suffixes: set[str]) -> bool:
    ok, _ = _path_stays_in_project(raw_path, project_path, cwd)
    if not ok:
        return False
    path = (cwd / raw_path).resolve()
    lowered = str(path.relative_to(project_path.resolve())).lower()
    if path.suffix not in suffixes:
        return False
    return any(token in lowered for token in ("setup", "install", "script", "bootstrap", "prepare"))


def _path_stays_in_project(raw_path: str, project_path: Path, cwd: Path) -> tuple[bool, str | None]:
    path = (cwd / raw_path).resolve()
    try:
        path.relative_to(project_path.resolve())
    except ValueError:
        return False, "path escapes project workspace"
    return True, None


def _has_disallowed_shell_syntax(command: str) -> bool:
    return any(op in command for op in ("&&", "||", ";", "|", ">", "<", "$(", "`"))


def _command_has_unsupported_setup_syntax(command: str) -> bool:
    split = _split_stdout_redirect(command)
    if split.error:
        return True
    return _has_disallowed_shell_syntax(split.command)


def _looks_like_setup_command(command: str) -> bool:
    if re.match(r"(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*=", command):
        return True
    argv = _split_command(command)
    if not argv:
        return False
    exe = Path(argv[0]).name
    return exe in {
        "bash",
        "sh",
        "node",
        "npm",
        "pnpm",
        "yarn",
        "python",
        "python3",
        "pip",
        "pip3",
        "curl",
        "wget",
        "java",
        "test",
        "grep",
        "npx",
    } or argv[0].startswith("./")


def _looks_destructive(command: str) -> bool:
    argv = _split_command(command)
    if not argv:
        return True
    return argv[0] in {"rm", "mv", "cp", "chmod", "chown", "sudo", "git"}


def _normalize_setup_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] == "npx" and "-y" not in argv[1:3] and "--yes" not in argv[1:3]:
        args = _npx_args_without_yes(argv)
        if len(args) >= 3 and args[1:3] == ["playwright", "install"]:
            return ["npx", "--yes", *argv[1:]]
    return argv


def _npx_args_without_yes(argv: list[str]) -> list[str]:
    if not argv or argv[0] != "npx":
        return argv
    return [argv[0], *[part for part in argv[1:] if part not in {"-y", "--yes"}]]


def _prepare_command(command: str, cwd: Path, env: dict[str, str], project_path: Path) -> PreparedCommand:
    split = _split_stdout_redirect(command)
    if split.error:
        return PreparedCommand([], error=split.error)
    command_part = split.command
    if _has_disallowed_shell_syntax(command_part):
        return PreparedCommand([], error="command uses unsupported shell syntax")
    argv = _expand_argv(_split_command(command_part), cwd, env)
    if not argv:
        return PreparedCommand([], error="could not parse command")
    if argv[0] == "grep" and len(argv) >= 3:
        argv[2] = _decode_shell_pattern(argv[2])
    stdout_path = None
    if split.stdout_target:
        raw_target = _expand_env_value(split.stdout_target, cwd, env)
        ok, reason = _path_stays_in_project(raw_target, project_path, cwd)
        if not ok:
            return PreparedCommand([], error=reason)
        stdout_path = (cwd / raw_target).resolve()
    return PreparedCommand(argv=argv, stdout_path=stdout_path, stdout_append=split.stdout_append)


@dataclass
class _RedirectSplit:
    command: str
    stdout_target: str | None = None
    stdout_append: bool = False
    error: str | None = None


def _split_stdout_redirect(command: str) -> _RedirectSplit:
    index, append = _find_stdout_redirect(command)
    if index is None:
        return _RedirectSplit(command=command)
    left = command[:index].strip()
    right = command[index + (2 if append else 1):].strip()
    if not left or not right:
        return _RedirectSplit(command=command, error="stdout redirection is incomplete")
    if _find_stdout_redirect(right)[0] is not None:
        return _RedirectSplit(command=command, error="multiple stdout redirections are unsupported")
    try:
        targets = shlex.split(right)
    except ValueError:
        return _RedirectSplit(command=command, error="could not parse stdout redirection target")
    if len(targets) != 1:
        return _RedirectSplit(command=command, error="stdout redirection target must be one project-local file")
    return _RedirectSplit(command=left, stdout_target=targets[0], stdout_append=append)


def _find_stdout_redirect(command: str) -> tuple[int | None, bool]:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\" and not in_single:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == ">" and not in_single and not in_double:
            return index, index + 1 < len(command) and command[index + 1] == ">"
    return None, False


def _write_redirected_stdout(path: Path, stdout: str, *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        handle.write(stdout)


def _decode_shell_pattern(value: str) -> str:
    if len(value) >= 3 and value.startswith("$'") and value.endswith("'"):
        inner = value[2:-1]
        return bytes(inner, "utf-8").decode("unicode_escape")
    if value.startswith("$") and "\\t" in value:
        return value[1:].replace("\\t", "\t")
    return value


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _expand_argv(argv: list[str], cwd: Path, env: dict[str, str]) -> list[str]:
    return [_expand_env_value(part, cwd, env) for part in argv]


def _dedupe_commands(commands: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, Path]] = []
    for command, cwd in commands:
        key = (command, str(cwd))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((command, cwd))
    return deduped


def _tail(value: str | None, *, max_chars: int = 4000) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _write_setup_artifact(
    output_dir: Path,
    results: list[SetupCommandResult],
    planned_commands: list[PlannedSetupCommand],
    setup_context: dict[str, Any] | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "planned_commands": [command.to_dict() for command in planned_commands],
        "results": [asdict(result) for result in results],
    }
    (output_dir / "setup.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    if setup_context is not None:
        (output_dir / "setup-context.json").write_text(json.dumps(setup_context, indent=2) + "\n", encoding="utf-8")
