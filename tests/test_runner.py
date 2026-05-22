from __future__ import annotations

import contextlib
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from bench.runner import BenchmarkRunner
from bench.schemas import WorkspaceConfig


class RunnerLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_preserves_live_stdout_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            workspace_dir = root / "workspace"
            run_dir = root / "runs" / "live-timeout"
            bin_dir.mkdir()
            workspace_dir.mkdir()
            run_dir.mkdir(parents=True)

            fake_pi = bin_dir / "pi"
            fake_pi.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json, time",
                        "event = {",
                        "    'type': 'message_update',",
                        "    'assistantMessageEvent': {'type': 'text_delta', 'delta': 'live-log\\n'},",
                        "}",
                        "print(json.dumps(event), flush=True)",
                        "time.sleep(60)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_pi.chmod(fake_pi.stat().st_mode | stat.S_IXUSR)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
            try:
                workspace = WorkspaceConfig(
                    key="fake",
                    name="Fake",
                    path=str(workspace_dir),
                    model="fake-model",
                    provider="fake-provider",
                )
                runner = BenchmarkRunner(root, {"fake": workspace})
                runner._apply_workspace_sandbox = lambda command, workspace, model_dir: command

                result = await runner._run_single(
                    run_dir=run_dir,
                    workspace=workspace,
                    prompt="hello",
                    prompt_hash="hash",
                    timeout_seconds=1,
                    retries=0,
                    event_callback=None,
                    warmup=False,
                )
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(result.status, "timeout")
            self.assertIn("live-log", (run_dir / "fake" / "stdout.log").read_text())
            self.assertIn("message_update", (run_dir / "fake" / "events.jsonl").read_text())

    async def test_completed_process_cleans_lingering_process_group_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            workspace_dir = root / "workspace"
            run_dir = root / "runs" / "group-cleanup"
            child_pid_file = root / "child.pid"
            bin_dir.mkdir()
            workspace_dir.mkdir()
            run_dir.mkdir(parents=True)

            fake_pi = bin_dir / "pi"
            fake_pi.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json, os, subprocess",
                        "child = subprocess.Popen(",
                        "    ['sleep', '60'],",
                        "    stdin=subprocess.DEVNULL,",
                        "    stdout=subprocess.DEVNULL,",
                        "    stderr=subprocess.DEVNULL,",
                        ")",
                        "with open(os.environ['CHILD_PID_FILE'], 'w') as f:",
                        "    f.write(str(child.pid))",
                        "event = {",
                        "    'type': 'message_update',",
                        "    'assistantMessageEvent': {'type': 'text_delta', 'delta': 'done\\n'},",
                        "}",
                        "print(json.dumps(event), flush=True)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_pi.chmod(fake_pi.stat().st_mode | stat.S_IXUSR)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
            os.environ["CHILD_PID_FILE"] = str(child_pid_file)
            try:
                workspace = WorkspaceConfig(
                    key="fake",
                    name="Fake",
                    path=str(workspace_dir),
                    model="fake-model",
                    provider="fake-provider",
                )
                runner = BenchmarkRunner(root, {"fake": workspace})
                runner._apply_workspace_sandbox = lambda command, workspace, model_dir: command

                result = await runner._run_single(
                    run_dir=run_dir,
                    workspace=workspace,
                    prompt="hello",
                    prompt_hash="hash",
                    timeout_seconds=10,
                    retries=0,
                    event_callback=None,
                    warmup=False,
                )
            finally:
                os.environ["PATH"] = old_path
                os.environ.pop("CHILD_PID_FILE", None)

            self.assertEqual(result.status, "completed")
            child_pid = int(child_pid_file.read_text(encoding="utf-8"))
            for _ in range(20):
                if not _pid_is_alive(child_pid):
                    break
                time.sleep(0.1)
            self.assertFalse(_pid_is_alive(child_pid))


def _pid_is_alive(pid: int) -> bool:
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, 0)
        return True
    return False


if __name__ == "__main__":
    unittest.main()
