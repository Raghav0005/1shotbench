from __future__ import annotations

import tempfile
import subprocess
import time
import unittest
from pathlib import Path

from bench.codex_judge.runner import (
    CodexJudgeOptions,
    CodexJudgeRunner,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    _build_codex_exec_command,
    _cleanup_judge_processes,
    _codex_result_schema,
    _detect_forbidden_mutations,
    _ignore_for_mutation,
    _snapshot_mutation_manifest,
)


class CodexJudgeMutationTests(unittest.TestCase):
    def test_detects_source_file_modification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "server.py"
            path.write_text("print('a')\n", encoding="utf-8")
            before = _snapshot_mutation_manifest(root)
            path.write_text("print('b')\n", encoding="utf-8")
            after = _snapshot_mutation_manifest(root)
            self.assertEqual(_detect_forbidden_mutations(before, after), ["server.py"])

    def test_ignores_runtime_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _snapshot_mutation_manifest(root)
            (root / "node_modules").mkdir()
            (root / "node_modules" / "pkg.json").write_text("{}", encoding="utf-8")
            (root / "artifacts" / "runs").mkdir(parents=True)
            (root / "artifacts" / "runs" / "run.cacm.recall_1000.txt").write_text("run\n", encoding="utf-8")
            (root / "artifacts" / "evals").mkdir(parents=True)
            (root / "artifacts" / "evals" / "eval.cacm.recall_1000.txt").write_text("eval\n", encoding="utf-8")
            (root / "run.cacm.recall_1000.txt").write_text("run\n", encoding="utf-8")
            (root / "eval.cacm.recall_1000.txt").write_text("eval\n", encoding="utf-8")
            (root / "server.log").write_text("hello\n", encoding="utf-8")
            (root / "package-lock.json").write_text("{}", encoding="utf-8")
            (root / ".next" / "cache" / "webpack").mkdir(parents=True)
            (root / ".next" / "cache" / "webpack" / "index.pack.gz").write_text("cache\n", encoding="utf-8")
            (root / ".next" / "build-manifest.json").write_text("{}", encoding="utf-8")
            (root / "work" / "browser-catalog" / "screenshots").mkdir(parents=True)
            (root / "work" / "browser-catalog" / "screenshots" / "catalog.png").write_text("png\n", encoding="utf-8")
            after = _snapshot_mutation_manifest(root)
            self.assertEqual(_detect_forbidden_mutations(before, after), [])

    def test_ignore_helper_matches_expected_paths(self) -> None:
        self.assertTrue(_ignore_for_mutation(Path("node_modules/react/index.js")))
        self.assertTrue(_ignore_for_mutation(Path("artifacts/runs/run.cacm.recall_1000.txt")))
        self.assertTrue(_ignore_for_mutation(Path("run.cacm.recall_1000.txt")))
        self.assertTrue(_ignore_for_mutation(Path("eval.cacm.recall_1000.txt")))
        self.assertTrue(_ignore_for_mutation(Path("package-lock.json")))
        self.assertTrue(_ignore_for_mutation(Path("server.log")))
        self.assertTrue(_ignore_for_mutation(Path(".next/build-manifest.json")))
        self.assertTrue(_ignore_for_mutation(Path("work/browser-catalog/screenshots/catalog.png")))
        self.assertFalse(_ignore_for_mutation(Path("src/work/worker.ts")))
        self.assertFalse(_ignore_for_mutation(Path("src/app/page.tsx")))

    def test_build_codex_command_places_approval_before_exec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = CodexJudgeOptions(
                project_path=root / "app",
                prd_path=root / "PRD.md",
                codex_command="codex",
                search=True,
                codex_model="gpt-5",
            )
            command = _build_codex_exec_command(
                options=options,
                judge_workspace=root / "judge",
                root_dir=root,
                schema_path=root / "schema.json",
                final_path=root / "final.json",
                prompt="judge this app",
            )
            self.assertEqual(command[:5], ["codex", "-a", "never", "--search", "exec"])
            self.assertNotIn("--ask-for-approval", command)
            self.assertIn("--ignore-user-config", command)
            self.assertIn("-c", command)
            self.assertIn(f'model_reasoning_effort="{DEFAULT_CODEX_REASONING_EFFORT}"', command)
            self.assertIn("--sandbox", command)
            self.assertEqual(command[command.index("--sandbox") + 1], "danger-full-access")

    def test_build_codex_command_uses_light_default_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = CodexJudgeOptions(
                project_path=root / "app",
                prd_path=root / "PRD.md",
                codex_command="codex",
            )
            command = _build_codex_exec_command(
                options=options,
                judge_workspace=root / "judge",
                root_dir=root,
                schema_path=root / "schema.json",
                final_path=root / "final.json",
                prompt="judge this app",
            )
            self.assertIn("--model", command)
            self.assertEqual(command[command.index("--model") + 1], DEFAULT_CODEX_MODEL)

    def test_keep_workspace_defaults_inside_eval_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "evals" / "codex-test"
            output_dir.mkdir(parents=True)
            project = root / "gpt-workspace"
            project.mkdir()
            options = CodexJudgeOptions(
                project_path=project,
                prd_path=root / "PRD.md",
                keep_judge_workspace=True,
            )
            workspace = CodexJudgeRunner(root_dir=root)._create_judge_workspace(
                options,
                project,
                output_dir,
            )
            self.assertEqual(workspace, output_dir / "judge-workspace")

    def test_codex_schema_disallows_additional_properties_on_all_objects(self) -> None:
        def walk(schema: object) -> None:
            if not isinstance(schema, dict):
                return
            if schema.get("type") == "object":
                self.assertIs(schema.get("additionalProperties"), False)
            for value in schema.get("properties", {}).values():
                walk(value)
            walk(schema.get("items"))
            for value in schema.get("anyOf", []):
                walk(value)

        walk(_codex_result_schema())

    def test_prompt_forbids_sibling_workspace_inspection_and_external_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            inputs.mkdir()
            prd = inputs / "PRD.md"
            prd.write_text("# PRD\n", encoding="utf-8")
            prompt = CodexJudgeRunner(root_dir=root)._build_prompt(
                features_copy=None,
                prd_copy=prd,
                base_url=None,
                no_start=False,
            )
            self.assertIn("Do not read, inspect, compare, or mention any other coding-agent workspace", prompt)
            self.assertIn("Do not mutate files outside `./app`, `./work`, and `./artifacts`", prompt)
            self.assertIn("allow the app to write documented runtime outputs", prompt)
            self.assertIn("Prefer `./work` and `./artifacts` for judge-created evidence", prompt)
            self.assertIn(".agents/skills", prompt)
            self.assertIn("only to understand documented setup/runtime commands", prompt)
            self.assertIn("Do not inspect source code to determine whether a feature passes", prompt)
            self.assertIn("Do not read app tests, e2e tests, or source files", prompt)
            self.assertIn("Do not read or use user Codex plugin skills", prompt)
            self.assertIn("MUST use the Playwright helper", prompt)
            self.assertIn("Do not write ad-hoc Python or Node Playwright scripts", prompt)
            self.assertIn("Do not run separate backend/evaluator smoke commands", prompt)
            self.assertIn("generate at most 5", prompt)
            self.assertIn("Do not rerun a successful end-to-end evaluation", prompt)
            self.assertIn("background children may be cleaned up", prompt)
            self.assertIn("long-lived foreground exec command", prompt)
            self.assertIn("Do not print full evidence JSON", prompt)
            self.assertIn("at most 30s", prompt)
            self.assertIn("wait_for_any_text", prompt)

    def test_cleanup_judge_processes_stops_pid_files_under_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            work.mkdir()
            proc = subprocess.Popen(["sleep", "60"], start_new_session=True)
            try:
                (work / "server.pid").write_text(str(proc.pid), encoding="utf-8")
                _cleanup_judge_processes(root)
                for _ in range(20):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                self.assertIsNotNone(proc.poll())
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
