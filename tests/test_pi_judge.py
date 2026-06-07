from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import bench.pi_judge.__main__ as pi_main
from bench.pi_judge.runner import (
    DEFAULT_PI_JUDGE_MODEL,
    DEFAULT_PI_JUDGE_PROVIDER,
    DEFAULT_PI_JUDGE_TOOLS,
    PiJudgeOptions,
    PiJudgeRunner,
    _build_pi_exec_command,
    _run_pi_command,
)
from bench.llm_judge.report import render_markdown
from bench.llm_judge.schemas import WebEvalSummary


class PiJudgeTests(unittest.TestCase):
    def test_build_pi_command_uses_json_print_no_session_and_model_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = PiJudgeOptions(
                project_path=root / "app",
                prd_path=root / "PRD.md",
                pi_command="pi",
                provider="anthropic",
                model="claude-opus-4-7",
                thinking="high",
                tools=["read", "bash", "write"],
            )
            command = _build_pi_exec_command(options=options, prompt="judge this app")
            self.assertEqual(command[:3], ["pi", "--mode", "json"])
            self.assertIn("--print", command)
            self.assertIn("--no-session", command)
            self.assertEqual(command[command.index("--provider") + 1], "anthropic")
            self.assertEqual(command[command.index("--model") + 1], "claude-opus-4-7")
            self.assertEqual(command[command.index("--thinking") + 1], "high")
            self.assertEqual(command[command.index("--tools") + 1], "read,bash,write")
            self.assertEqual(command[-1], "judge this app")

    def test_build_pi_command_uses_default_provider_model_and_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = PiJudgeOptions(project_path=root / "app", prd_path=root / "PRD.md")
            command = _build_pi_exec_command(options=options, prompt="judge this app")
            self.assertEqual(command[command.index("--provider") + 1], DEFAULT_PI_JUDGE_PROVIDER)
            self.assertEqual(command[command.index("--model") + 1], DEFAULT_PI_JUDGE_MODEL)
            self.assertEqual(command[command.index("--tools") + 1], ",".join(DEFAULT_PI_JUDGE_TOOLS))

    def test_pi_main_codex_fast_sets_low_thinking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "app"
            project.mkdir()
            prd = root / "PRD.md"
            prd.write_text("# PRD\n", encoding="utf-8")
            captured: dict[str, PiJudgeOptions] = {}

            class FakeRunner:
                def run(self, options: PiJudgeOptions) -> WebEvalSummary:
                    captured["options"] = options
                    return WebEvalSummary(
                        eval_id="pi-fast-test",
                        label=options.label,
                        started_at="2026-06-07T00:00:00Z",
                        ended_at="2026-06-07T00:00:01Z",
                        project_path=str(options.project_path),
                        features_path="",
                        prd_path=str(options.prd_path),
                        base_url="",
                        total_features=0,
                        passed=0,
                        failed=0,
                        uncertain=0,
                        correctness_pct=0.0,
                        judgments=[],
                        judge_model="pi:openai-codex/gpt-5.4-mini",
                    )

            with (
                mock.patch.object(pi_main, "ROOT_DIR", root),
                mock.patch.object(pi_main, "PiJudgeRunner", return_value=FakeRunner()),
                mock.patch.object(sys, "argv", ["pi-judge", "--project", str(project), "--prd", str(prd), "--codex-fast"]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(pi_main.main(), 0)

            options = captured["options"]
            self.assertEqual(options.provider, DEFAULT_PI_JUDGE_PROVIDER)
            self.assertEqual(options.model, DEFAULT_PI_JUDGE_MODEL)
            self.assertEqual(options.thinking, "low")

    def test_keep_workspace_defaults_inside_eval_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "evals" / "pi-test"
            output_dir.mkdir(parents=True)
            project = root / "gpt-workspace"
            project.mkdir()
            options = PiJudgeOptions(
                project_path=project,
                prd_path=root / "PRD.md",
                keep_judge_workspace=True,
            )
            workspace = PiJudgeRunner(root_dir=root)._create_judge_workspace(
                options,
                project,
                output_dir,
            )
            self.assertEqual(workspace, output_dir / "judge-workspace")

    def test_prompt_requires_final_file_and_reuses_web_judge_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            inputs.mkdir()
            prd = inputs / "PRD.md"
            prd.write_text("# PRD\n", encoding="utf-8")
            prompt = PiJudgeRunner(root_dir=root)._build_pi_prompt(
                features_copy=None,
                prd_copy=prd,
                base_url=None,
                no_start=False,
                schema_path=root / "pi-final-schema.json",
                final_path=root / "pi-final.json",
            )
            self.assertIn("You are the Pi judge", prompt)
            self.assertIn("Final structured response path: `pi-final.json`", prompt)
            self.assertIn("Write only JSON matching the provided output schema", prompt)
            self.assertIn("follow the judge skill for full safety, setup, speed, and evidence rules", prompt)
            self.assertIn("Do not inspect sibling agent workspaces", prompt)
            self.assertIn("mutate outside `./app`, `./work`, and `./artifacts`", prompt)
            self.assertIn("MUST use the Playwright helper", prompt)
            self.assertIn("Do not print full evidence JSON", prompt)
            self.assertIn("Use canonical feature ids verbatim", prompt)
            self.assertIn("at most one bounded follow-up per feature", prompt)
            self.assertIn("same-origin API request statuses", prompt)
            self.assertIn("UI remains in a loading state", prompt)
            self.assertIn("different temp workspace or wrong app root", prompt)
            self.assertNotIn("alternate free local port", prompt)
            self.assertNotIn("documented nested app directory", prompt)

    def test_report_title_uses_pi_judge_model_prefix(self) -> None:
        summary = WebEvalSummary(
            eval_id="pi-test",
            label="Pi Test",
            started_at="2026-06-06T00:00:00Z",
            ended_at="2026-06-06T00:00:01Z",
            project_path="/tmp/app",
            features_path="/tmp/features.yaml",
            prd_path=None,
            base_url="http://127.0.0.1:3000",
            total_features=0,
            passed=0,
            failed=0,
            uncertain=0,
            correctness_pct=0.0,
            judgments=[],
            judge_model="pi:openai-codex/gpt-5.4-mini",
        )
        self.assertTrue(render_markdown(summary, Path("/tmp/eval")).startswith("# Pi Judge Report: Pi Test"))

    def test_timeout_writes_logs_and_preserves_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "app"
            project.mkdir()
            (project / "README.md").write_text("# App\n", encoding="utf-8")
            prd = root / "PRD.md"
            prd.write_text("# PRD\n\nRun the app.\n", encoding="utf-8")
            evals_dir = root / "evals"

            timeout = subprocess.TimeoutExpired(
                ["pi", "judge"],
                timeout=3,
                output="partial stdout",
                stderr=b"partial stderr",
            )
            with (
                mock.patch.object(PiJudgeRunner, "preflight", return_value=[]),
                mock.patch("bench.pi_judge.runner.EVALS_DIR", evals_dir),
                mock.patch("bench.pi_judge.runner._run_pi_command", side_effect=timeout),
            ):
                with self.assertRaisesRegex(RuntimeError, "timed out after 3s"):
                    PiJudgeRunner(root_dir=root).run(
                        PiJudgeOptions(
                            project_path=project,
                            prd_path=prd,
                            eval_id="pi-timeout",
                            judge_timeout_seconds=3,
                        )
                    )

            output_dir = evals_dir / "pi-timeout"
            self.assertEqual((output_dir / "pi.stdout.log").read_text(encoding="utf-8"), "partial stdout")
            stderr = (output_dir / "pi.stderr.log").read_text(encoding="utf-8")
            self.assertIn("partial stderr", stderr)
            self.assertIn("Pi judge timed out after 3s", stderr)
            run_metadata = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_metadata["status"], "timed_out")
            self.assertTrue(Path(run_metadata["judge_workspace"]).exists())

    def test_pi_command_cleanup_stops_lingering_process_group_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "child.pid"
            script = root / "judge.py"
            script.write_text(
                "\n".join(
                    [
                        "import pathlib, subprocess, sys",
                        "pid_file = pathlib.Path(sys.argv[1])",
                        "child = subprocess.Popen(['sleep', '60'])",
                        "pid_file.write_text(str(child.pid), encoding='utf-8')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            _run_pi_command([sys.executable, str(script), str(pid_file)], cwd=root, env={}, timeout=10)
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            for _ in range(20):
                if not _pid_is_alive(child_pid):
                    break
                time.sleep(0.1)
            self.assertFalse(_pid_is_alive(child_pid))


def _pid_is_alive(pid: int) -> bool:
    try:
        subprocess.run(["kill", "-0", str(pid)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


if __name__ == "__main__":
    unittest.main()
