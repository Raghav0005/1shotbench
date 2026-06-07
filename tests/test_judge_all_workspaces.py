from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bench.llm_judge.schemas import WebEvalSummary
from bench.pi_judge.runner import DEFAULT_PI_JUDGE_MODEL, DEFAULT_PI_JUDGE_PROVIDER, PiJudgeOptions
from scripts import judge_all_workspaces


class JudgeAllWorkspacesTests(unittest.TestCase):
    def test_codex_fast_sets_pi_openai_codex_low_thinking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "frontend"
            workspace = project / "gpt-workspace"
            workspace.mkdir(parents=True)
            prd = project / "PRD.md"
            prd.write_text("# PRD\n", encoding="utf-8")
            target = judge_all_workspaces.WorkspaceTarget(
                project_name="frontend",
                workspace_name="gpt-workspace",
                workspace_path=workspace,
                prd_path=prd,
                features_path=None,
            )
            args = argparse.Namespace(
                judge="pi",
                judge_workspace_root=None,
                tools="read,bash",
                codex_fast=True,
                provider="anthropic",
                model=None,
                thinking=None,
                pi_command="pi",
                judge_timeout_seconds=900,
                keep_judge_workspace=False,
            )
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

            with mock.patch("bench.pi_judge.runner.PiJudgeRunner", return_value=FakeRunner()):
                judge_all_workspaces.run_target(args, target, label="all-pi-judge-frontend-gpt")

            options = captured["options"]
            self.assertEqual(options.provider, DEFAULT_PI_JUDGE_PROVIDER)
            self.assertEqual(options.model, DEFAULT_PI_JUDGE_MODEL)
            self.assertEqual(options.thinking, "low")


if __name__ == "__main__":
    unittest.main()
