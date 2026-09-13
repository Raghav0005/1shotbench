from __future__ import annotations

import tempfile
import subprocess
import sys
import time
import unittest
from pathlib import Path

from bench.codex_judge.runner import (
    CodexJudgeOptions,
    CodexJudgeRunner,
    CODEX_SKILL_DIR,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    _build_codex_exec_command,
    _cleanup_judge_processes,
    _codex_result_schema,
    _detect_forbidden_mutations,
    _ignore_for_mutation,
    _run_codex_command,
    _snapshot_mutation_manifest,
)
from bench.llm_judge.schemas import FeatureCheck


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

    def test_ignores_next_generated_env_file_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_env = root / "next-env.d.ts"
            next_env.write_text(
                '/// <reference types="next" />\n'
                '/// <reference types="next/image-types/global" />\n'
                'import "./.next/types/routes.d.ts";\n',
                encoding="utf-8",
            )
            before = _snapshot_mutation_manifest(root)
            next_env.write_text(
                '/// <reference types="next" />\n'
                '/// <reference types="next/image-types/global" />\n'
                'import "./.next/dev/types/routes.d.ts";\n',
                encoding="utf-8",
            )
            after = _snapshot_mutation_manifest(root)
            self.assertEqual(_detect_forbidden_mutations(before, after), [])

    def test_ignores_next_generated_agent_instruction_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _snapshot_mutation_manifest(root)
            (root / "AGENTS.md").write_text("<!-- BEGIN:nextjs-agent-rules -->\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
            after = _snapshot_mutation_manifest(root)
            self.assertEqual(_detect_forbidden_mutations(before, after), [])

    def test_ignore_helper_matches_expected_paths(self) -> None:
        self.assertTrue(_ignore_for_mutation(Path("node_modules/react/index.js")))
        self.assertTrue(_ignore_for_mutation(Path("artifacts/runs/run.cacm.recall_1000.txt")))
        self.assertTrue(_ignore_for_mutation(Path("run.cacm.recall_1000.txt")))
        self.assertTrue(_ignore_for_mutation(Path("eval.cacm.recall_1000.txt")))
        self.assertTrue(_ignore_for_mutation(Path("package-lock.json")))
        self.assertTrue(_ignore_for_mutation(Path("next-env.d.ts")))
        self.assertTrue(_ignore_for_mutation(Path("AGENTS.md")))
        self.assertTrue(_ignore_for_mutation(Path("CLAUDE.md")))
        self.assertFalse(_ignore_for_mutation(Path("src/AGENTS.md")))
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

    def test_prompt_contains_core_constraints_without_repeating_skill_details(self) -> None:
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
            self.assertIn("follow the judge skill for full safety, setup, speed, and evidence rules", prompt)
            self.assertIn("Do not inspect sibling agent workspaces", prompt)
            self.assertIn("mutate outside `./app`, `./work`, and `./artifacts`", prompt)
            self.assertIn("MUST use the Playwright helper", prompt)
            self.assertIn("same-origin API request statuses", prompt)
            self.assertIn("UI remains in a loading state", prompt)
            self.assertIn("Do not print full evidence JSON", prompt)
            self.assertNotIn("alternate free local port", prompt)
            self.assertNotIn("documented nested app directory", prompt)

    def test_web_judge_skill_contains_operational_recovery_guidance(self) -> None:
        skill = (CODEX_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not read, inspect, compare, or mention any other coding-agent workspace", skill)
        self.assertIn("Do not write ad-hoc Python or Node Playwright scripts", skill)
        self.assertIn("Do not run separate backend/evaluator smoke commands", skill)
        self.assertIn("generate at most 5", skill)
        self.assertIn("Do not rerun a successful end-to-end workflow", skill)
        self.assertIn("same-origin API request diagnostics", skill)
        self.assertIn("page remains in a loading state", skill)
        self.assertIn("background children may be cleaned up", skill)
        self.assertIn("long-lived foreground exec command", skill)
        self.assertIn("do not evaluate the unrelated existing listener", skill)
        self.assertIn("alternate free local port", skill)
        self.assertIn("A successful `curl` to an alternate port is not enough", skill)
        self.assertIn("documented nested app directory", skill)
        self.assertIn("conventional app-local artifact location", skill)
        self.assertIn("Missing runtime artifacts are setup work", skill)
        self.assertIn("missing local file/class/resource", skill)
        self.assertIn("Do not record final failure for missing runtime artifacts", skill)
        self.assertIn("fixture bundle", skill)
        self.assertIn("at most 30s", skill)
        self.assertIn("wait_for_any_text", skill)

    def test_materialize_results_normalizes_unambiguous_feature_id_typo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            features = [
                FeatureCheck("cacam-evaluable", "CACM", "CACM appears", "CACM visible"),
            ]
            raw_result = {
                "judgments": [
                    {
                        "feature_id": "cacm-evaluable",
                        "verdict": "pass",
                        "confidence": 0.9,
                        "reason": "CACM evidence was visible.",
                        "evidence_used": ["browser evidence"],
                        "evidence": {"visible_text": "Topics: cacm Qrels: cacm"},
                    }
                ]
            }

            judgments, evidence_by_feature, notes = CodexJudgeRunner()._materialize_results(
                raw_result=raw_result,
                features=features,
                output_dir=output_dir,
            )

            self.assertEqual(judgments[0].feature_id, "cacam-evaluable")
            self.assertEqual(judgments[0].verdict, "pass")
            self.assertEqual(evidence_by_feature["cacam-evaluable"].visible_text, "Topics: cacm Qrels: cacm")
            self.assertIn("Normalized judgment feature ids: cacm-evaluable -> cacam-evaluable", notes or "")

    def test_materialize_results_does_not_normalize_ambiguous_feature_id_typo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            features = [
                FeatureCheck("foo", "Foo", "Foo", "Foo"),
                FeatureCheck("fob", "Fob", "Fob", "Fob"),
            ]
            raw_result = {
                "judgments": [
                    {
                        "feature_id": "fo",
                        "verdict": "pass",
                        "confidence": 0.9,
                        "reason": "Ambiguous.",
                        "evidence": {"visible_text": "ambiguous"},
                    }
                ]
            }

            judgments, _, notes = CodexJudgeRunner()._materialize_results(
                raw_result=raw_result,
                features=features,
                output_dir=output_dir,
            )

            self.assertEqual([judgment.verdict for judgment in judgments], ["uncertain", "uncertain"])
            self.assertIn("Ignored judgments for unknown feature ids: fo", notes or "")

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

    def test_codex_command_cleanup_stops_lingering_process_group_children(self) -> None:
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

            _run_codex_command([sys.executable, str(script), str(pid_file)], cwd=root, env={}, timeout=10)
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
