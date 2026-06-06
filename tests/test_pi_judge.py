from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bench.pi_judge.runner import (
    DEFAULT_PI_JUDGE_MODEL,
    DEFAULT_PI_JUDGE_PROVIDER,
    DEFAULT_PI_JUDGE_TOOLS,
    PiJudgeOptions,
    PiJudgeRunner,
    _build_pi_exec_command,
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
            self.assertIn("Do not inspect source code to determine whether a feature passes", prompt)
            self.assertIn("Do not mutate files outside `./app`, `./work`, and `./artifacts`", prompt)
            self.assertIn("MUST use the Playwright helper", prompt)
            self.assertIn("Do not print full evidence JSON", prompt)

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


if __name__ == "__main__":
    unittest.main()
