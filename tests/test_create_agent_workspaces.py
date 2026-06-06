from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.create_agent_workspaces import WORKSPACES, create_workspaces


class CreateAgentWorkspacesTests(unittest.TestCase):
    def test_workspaces_include_current_deepseek_model(self) -> None:
        deepseek = next((spec for spec in WORKSPACES if spec.key == "deepseek"), None)

        self.assertIsNotNone(deepseek)
        assert deepseek is not None
        self.assertEqual(deepseek.provider, "deepseek")
        self.assertEqual(deepseek.model, "deepseek-v4-pro")

    def test_workspaces_include_current_minimax_and_mimo_models(self) -> None:
        specs = {spec.key: spec for spec in WORKSPACES}

        self.assertEqual(specs["minimax"].provider, "minimax")
        self.assertEqual(specs["minimax"].model, "MiniMax-M3")
        self.assertEqual(specs["mimo"].provider, "xiaomi")
        self.assertEqual(specs["mimo"].model, "mimo-v2.5-pro")

    def test_create_workspaces_writes_deepseek_bench_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "task"
            (task_dir).mkdir()
            (task_dir / "PRD.md").write_text("Build the app.\n", encoding="utf-8")

            create_workspaces(task_dir, force=False)

            bench_toml = task_dir / "deepseek-workspace" / "bench.toml"
            self.assertTrue(bench_toml.is_file())
            text = bench_toml.read_text(encoding="utf-8")
            self.assertIn('provider = "deepseek"', text)
            self.assertIn('model = "deepseek-v4-pro"', text)
            prd_copy = task_dir / "deepseek-workspace" / "PRD.md"
            self.assertTrue(prd_copy.is_file())
            self.assertFalse(prd_copy.is_symlink())
            self.assertEqual(prd_copy.read_text(encoding="utf-8"), "Build the app.\n")


if __name__ == "__main__":
    unittest.main()
