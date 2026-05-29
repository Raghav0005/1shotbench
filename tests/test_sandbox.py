from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bench.runner import BenchmarkRunner
from bench.sandbox import (
    BWRAP_ARTIFACT_NAME,
    SANDBOX_PROFILE_NAME,
    apply_workspace_sandbox,
    bwrap_is_functional,
    denied_workspace_paths,
    resolve_sandbox_backend,
    sandbox_preflight_error,
)
from bench.schemas import WorkspaceConfig


class SandboxPathTests(unittest.TestCase):
    def test_denied_paths_include_sibling_workspaces_and_private_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "task"
            alpha = task_dir / "alpha-workspace"
            beta = task_dir / "beta-workspace"
            alpha.mkdir(parents=True)
            beta.mkdir(parents=True)
            workspaces = {
                "alpha": WorkspaceConfig("alpha", "Alpha", str(alpha), "model-a"),
                "beta": WorkspaceConfig("beta", "Beta", str(beta), "model-b"),
            }

            denied = denied_workspace_paths(
                root_dir=root,
                workspaces=workspaces,
                workspace=workspaces["alpha"],
            )

            self.assertEqual(denied, [beta.resolve(), (root / ".codex-private").resolve()])
            self.assertTrue((root / ".codex-private").exists())


class SandboxWrapTests(unittest.TestCase):
    def test_wrap_with_sandbox_exec_writes_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "task"
            alpha = task_dir / "alpha-workspace"
            beta = task_dir / "beta-workspace"
            alpha.mkdir(parents=True)
            beta.mkdir(parents=True)
            model_dir = root / "run" / "alpha"
            model_dir.mkdir(parents=True)
            workspaces = {
                "alpha": WorkspaceConfig("alpha", "Alpha", str(alpha), "model-a"),
                "beta": WorkspaceConfig("beta", "Beta", str(beta), "model-b"),
            }

            with mock.patch("bench.sandbox.shutil.which", return_value="/usr/bin/sandbox-exec"):
                wrapped = apply_workspace_sandbox(
                    root_dir=root,
                    workspaces=workspaces,
                    workspace=workspaces["alpha"],
                    model_dir=model_dir,
                    command=["pi", "hello"],
                )

            self.assertEqual(wrapped[:3], ["/usr/bin/sandbox-exec", "-f", str(model_dir / SANDBOX_PROFILE_NAME)])
            profile = (model_dir / SANDBOX_PROFILE_NAME).read_text(encoding="utf-8")
            self.assertIn("(allow default)", profile)
            self.assertIn(str(beta.resolve()), profile)
            self.assertIn(str((root / ".codex-private").resolve()), profile)

    def test_wrap_with_bwrap_overlays_denied_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "task"
            alpha = task_dir / "alpha-workspace"
            beta = task_dir / "beta-workspace"
            alpha.mkdir(parents=True)
            beta.mkdir(parents=True)
            (beta / "secret.txt").write_text("secret", encoding="utf-8")
            model_dir = root / "run" / "alpha"
            model_dir.mkdir(parents=True)
            workspaces = {
                "alpha": WorkspaceConfig("alpha", "Alpha", str(alpha), "model-a"),
                "beta": WorkspaceConfig("beta", "Beta", str(beta), "model-b"),
            }

            def fake_which(name: str) -> str | None:
                if name == "sandbox-exec":
                    return None
                if name == "bwrap":
                    return "/usr/bin/bwrap"
                return None

            with (
                mock.patch("bench.sandbox.shutil.which", side_effect=fake_which),
                mock.patch("bench.sandbox.bwrap_is_functional", return_value=True),
            ):
                wrapped = apply_workspace_sandbox(
                    root_dir=root,
                    workspaces=workspaces,
                    workspace=workspaces["alpha"],
                    model_dir=model_dir,
                    command=["pi", "hello"],
                )

            overlay_dir = model_dir / "sandbox-deny-overlay"
            self.assertTrue(overlay_dir.is_dir())
            self.assertEqual(wrapped[0], "/usr/bin/bwrap")
            self.assertIn("--ro-bind", wrapped)
            self.assertIn(str(overlay_dir), wrapped)
            self.assertIn(str(beta.resolve()), wrapped)
            self.assertEqual(wrapped[-3:], ["--", "pi", "hello"])

            artifact = json.loads((model_dir / BWRAP_ARTIFACT_NAME).read_text(encoding="utf-8"))
            self.assertEqual(artifact["backend"], "bwrap")
            self.assertIn(str(beta.resolve()), artifact["denied_paths"])

    def test_preflight_requires_functional_sandbox_backend(self) -> None:
        with mock.patch("bench.sandbox.shutil.which", return_value=None):
            self.assertIsNone(resolve_sandbox_backend())
            self.assertIn("sandbox-exec", sandbox_preflight_error() or "")

        with (
            mock.patch(
                "bench.sandbox.shutil.which",
                side_effect=lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
            ),
            mock.patch("bench.sandbox.bwrap_is_functional", return_value=False),
        ):
            self.assertIsNone(resolve_sandbox_backend())
            self.assertIn("cannot create a sandbox", sandbox_preflight_error() or "")


@unittest.skipUnless(bwrap_is_functional(), "functional bwrap is unavailable")
class BwrapIsolationIntegrationTests(unittest.TestCase):
    def test_bwrap_hides_denied_directory_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "task"
            alpha = task_dir / "alpha-workspace"
            beta = task_dir / "beta-workspace"
            alpha.mkdir(parents=True)
            beta.mkdir(parents=True)
            (beta / "secret.txt").write_text("secret", encoding="utf-8")
            model_dir = root / "run" / "alpha"
            model_dir.mkdir(parents=True)
            workspaces = {
                "alpha": WorkspaceConfig("alpha", "Alpha", str(alpha), "model-a"),
                "beta": WorkspaceConfig("beta", "Beta", str(beta), "model-b"),
            }

            wrapped = apply_workspace_sandbox(
                root_dir=root,
                workspaces=workspaces,
                workspace=workspaces["alpha"],
                model_dir=model_dir,
                command=["/bin/sh", "-c", f"test -f {beta / 'secret.txt'} && echo visible || echo hidden"],
            )

            proc = subprocess.run(wrapped, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("hidden", proc.stdout)


class RunnerPreflightTests(unittest.TestCase):
    def test_preflight_reports_missing_sandbox_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()
            workspace = WorkspaceConfig("fake", "Fake", str(workspace_dir), "fake-model")
            runner = BenchmarkRunner(root, {"fake": workspace})

            with (
                mock.patch("bench.runner.shutil.which", return_value="/usr/bin/pi"),
                mock.patch("bench.runner.sandbox_preflight_error", return_value="sandbox missing"),
            ):
                errors = runner.preflight(["fake"])

            self.assertIn("sandbox missing", errors)


if __name__ == "__main__":
    unittest.main()
