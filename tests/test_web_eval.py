from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bench.web_eval.features import load_features, write_features
from bench.web_eval.judge import JudgeClient, compute_correctness, _features_from_json, _parse_judge_json
from bench.web_eval.prd import load_prd_context
from bench.web_eval.profile import resolve_app_profile
from bench.web_eval.report import render_markdown
from bench.web_eval.runner import WebEvalOptions, WebEvalRunner
from bench.web_eval.setup import PlannedSetupCommand, collect_setup_context, discover_readme_setup_commands, run_project_setup
from bench.web_eval.schemas import EvidencePacket, FeatureCheck, FeatureJudgment, WebEvalSummary


class WebEvalSchemaTests(unittest.TestCase):
    def test_load_features_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.json"
            path.write_text(
                json.dumps(
                    {
                        "features": [
                            {
                                "id": "f1",
                                "title": "Feature 1",
                                "steps": [{"action": "open", "path": "/"}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            features = load_features(path)
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0].id, "f1")
            self.assertEqual(features[0].steps[0].action, "open")


    def test_generated_features_from_json(self) -> None:
        features = _features_from_json(
            {
                "features": [
                    {
                        "id": "Search Works",
                        "title": "Search works",
                        "description": "Users can search",
                        "acceptance": "A query produces results",
                        "steps": [{"action": "open", "path": "/"}, {"action": "snapshot"}],
                    }
                ]
            },
            max_features=4,
        )
        self.assertEqual(features[0].id, "search-works")
        self.assertEqual(features[0].steps[1].action, "snapshot")

    def test_write_features_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.yaml"
            write_features(path, [FeatureCheck("f1", "Title", "desc", "accept")])
            loaded = load_features(path)
            self.assertEqual(loaded[0].id, "f1")

    def test_discover_readme_setup_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "## Setup\n```sh\nnpm install\nnode setup/install-fatjar.js\nrm -rf bad\n```\n",
                encoding="utf-8",
            )
            commands = [command for command, _ in discover_readme_setup_commands(root)]
            self.assertIn("npm install", commands)
            self.assertIn("node setup/install-fatjar.js", commands)
            self.assertNotIn("rm -rf bad", commands)


    def test_setup_applies_generic_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            root = Path(tmp)
            results = run_project_setup(
                root,
                Path(out),
                timeout_seconds=1,
                planned_commands=[PlannedSetupCommand("APP_CONFIG=$PWD/config.json")],
            )
            self.assertEqual(results[0].status, "completed")
            self.assertEqual(results[0].reason, "set APP_CONFIG")

    def test_setup_expands_env_vars_in_allowed_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            root = Path(tmp)
            target = root / "artifact.txt"
            target.write_text("ok", encoding="utf-8")
            results = run_project_setup(
                root,
                Path(out),
                timeout_seconds=2,
                planned_commands=[
                    PlannedSetupCommand("ARTIFACT=$PWD/artifact.txt"),
                    PlannedSetupCommand("test -f $ARTIFACT"),
                ],
            )
            self.assertEqual([result.status for result in results], ["completed", "completed"])

    def test_setup_allows_combined_curl_output_flag(self) -> None:
        from bench.web_eval.setup import _is_allowed_setup_command

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed, reason = _is_allowed_setup_command(
                ["curl", "-fLo", "download.bin", "https://example.test/download.bin"],
                root,
                root,
            )
            self.assertTrue(allowed, reason)

    def test_setup_supports_project_local_stdout_redirection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            root = Path(tmp)
            setup_dir = root / "setup"
            setup_dir.mkdir()
            script = setup_dir / "print_result.py"
            script.write_text('print("map\tall\t0.3123")\n', encoding="utf-8")
            results = run_project_setup(
                root,
                Path(out),
                timeout_seconds=2,
                planned_commands=[PlannedSetupCommand("python setup/print_result.py > eval.txt")],
            )
            self.assertEqual(results[0].status, "completed")
            self.assertEqual((root / "eval.txt").read_text(encoding="utf-8"), "map\tall\t0.3123\n")

    def test_setup_allows_grep_q_project_file_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            root = Path(tmp)
            (root / "eval.txt").write_text("map\tall\t0.3123\n", encoding="utf-8")
            results = run_project_setup(
                root,
                Path(out),
                timeout_seconds=2,
                planned_commands=[PlannedSetupCommand(r"grep -q $'map\tall\t0.3123' eval.txt")],
            )
            self.assertEqual(results[0].status, "completed")

    def test_setup_grep_verification_tolerates_metric_padding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            root = Path(tmp)
            (root / "eval.txt").write_text("map                  \tall\t0.3123\n", encoding="utf-8")
            results = run_project_setup(
                root,
                Path(out),
                timeout_seconds=2,
                planned_commands=[PlannedSetupCommand(r"grep -q $'map\tall\t0.3123' eval.txt")],
            )
            self.assertEqual(results[0].status, "completed")

    def test_setup_allows_playwright_browser_install_command(self) -> None:
        from bench.web_eval.setup import _is_allowed_setup_command

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed, reason = _is_allowed_setup_command(
                ["npx", "playwright", "install", "chromium"],
                root,
                root,
            )
            self.assertTrue(allowed, reason)

    def test_setup_normalizes_npx_playwright_install_to_yes(self) -> None:
        from bench.web_eval.setup import _is_allowed_setup_command, _normalize_setup_argv

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = _normalize_setup_argv(["npx", "playwright", "install", "chromium"])
            self.assertEqual(argv, ["npx", "--yes", "playwright", "install", "chromium"])
            allowed, reason = _is_allowed_setup_command(argv, root, root)
            self.assertTrue(allowed, reason)

    def test_setup_derives_maven_metadata_recovery_plan(self) -> None:
        from bench.web_eval.setup import _maven_download_recovery_plan, _rewrite_maven_download_argv

        argv = [
            "curl",
            "-fL",
            "-o",
            "anserini-0.37.1-fatjar.jar",
            "https://repo1.maven.org/maven2/io/anserini/anserini/0.37.1/anserini-0.37.1-fatjar.jar",
        ]
        plan = _maven_download_recovery_plan(argv)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(
            plan["metadata_url"],
            "https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml",
        )
        rewritten = _rewrite_maven_download_argv(argv, "0.37.1", "2.1.1")
        self.assertIn("anserini-2.1.1-fatjar.jar", rewritten)
        self.assertTrue(rewritten[-1].endswith("/2.1.1/anserini-2.1.1-fatjar.jar"))

    def test_setup_maven_recovery_updates_only_matching_version_env(self) -> None:
        from bench.web_eval.setup import _update_version_env_after_recovery

        env = {"ANSERINI_VERSION": "0.37.1", "NODE_VERSION": "20", "OTHER": "0.37.1"}
        _update_version_env_after_recovery(env, "2.1.1", "0.37.1")
        self.assertEqual(env["ANSERINI_VERSION"], "2.1.1")
        self.assertEqual(env["NODE_VERSION"], "20")
        self.assertEqual(env["OTHER"], "0.37.1")

    def test_setup_extracts_java_classpath_jar(self) -> None:
        from bench.web_eval.setup import _java_classpath_jar

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                _java_classpath_jar(["java", "-cp", "lib/example-1.0.jar", "example.Main"], root),
                (root / "lib/example-1.0.jar").resolve(),
            )

    def test_setup_context_includes_nested_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "app"
            nested.mkdir()
            (nested / "package.json").write_text('{"scripts":{"start":"node server.js"}}', encoding="utf-8")
            context = collect_setup_context(root)
            manifest_paths = [item["path"] for item in context["manifests"]]
            self.assertTrue(any(path.endswith("/app/package.json") for path in manifest_paths))

    def test_setup_repairs_npm_install_cwd_to_nested_manifest(self) -> None:
        from bench.web_eval.setup import commands_from_json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "app"
            nested.mkdir()
            (nested / "package.json").write_text('{"scripts":{"start":"node server.js"}}', encoding="utf-8")
            commands = commands_from_json([{"command": "npm install", "cwd": str(root)}], root)
            self.assertEqual(Path(commands[0].cwd), nested)

    def test_setup_rejects_java_usage_only_success(self) -> None:
        from bench.web_eval.setup import _looks_like_usage_only_success

        self.assertTrue(
            _looks_like_usage_only_success(
                ["java", "-cp", "x.jar", "example.Main"],
                "",
                "Usage: SearchCollection -index [path] -output [file]\nOptions:\n -index VAL",
            )
        )
        self.assertFalse(
            _looks_like_usage_only_success(
                ["java", "-cp", "x.jar", "example.Main"],
                "Total run time: 00:00:02",
                "Index folder already exists!\nOptions were parsed",
            )
        )

    def test_setup_rejects_java_error_output_success(self) -> None:
        from bench.web_eval.setup import _post_command_failure_reason

        reason = _post_command_failure_reason(
            ["java", "-cp", "x.jar", "example.Main", "-output", "missing.txt"],
            Path("/tmp"),
            "Total run time: 00:00:00",
            'Error: "cacm" does not refer to valid topics.',
        )
        self.assertIsNotNone(reason)
        self.assertIn("error", reason.lower())

    def test_profile_repairs_invalid_configured_cwd_to_nested_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "app"
            nested.mkdir()
            (nested / "package.json").write_text(
                json.dumps({"scripts": {"start": "node server.js"}}),
                encoding="utf-8",
            )
            (nested / "server.js").write_text("", encoding="utf-8")
            profile = resolve_app_profile(
                root,
                base_url=None,
                profile_data={"port": 3123, "start_command": ["npm", "start"], "cwd": ".", "env": {"PORT": "3123"}},
                no_start=False,
            )
            self.assertEqual(Path(profile.cwd), nested)
            self.assertEqual(profile.env["PORT"], "3123")
            self.assertEqual(profile.base_url, "http://127.0.0.1:3123")

    def test_profile_avoids_occupied_local_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps({"scripts": {"start": "node server.js"}}),
                encoding="utf-8",
            )
            (root / "server.js").write_text("", encoding="utf-8")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                occupied = sock.getsockname()[1]
                profile = resolve_app_profile(
                    root,
                    base_url=None,
                    profile_data={"port": occupied, "start_command": ["npm", "start"], "cwd": ".", "env": {"PORT": str(occupied)}},
                    no_start=False,
                )
            self.assertNotEqual(profile.base_url, f"http://127.0.0.1:{occupied}")
            self.assertNotEqual(profile.env["PORT"], str(occupied))

    def test_setup_context_includes_referenced_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Use `install-anserini-fatjar` before running.\n", encoding="utf-8")
            context = collect_setup_context(root)
            names = [skill["name"] for skill in context["referenced_skills"]]
            self.assertIn("install-anserini-fatjar", names)
            hint_commands = [
                command
                for hint in context["setup_hints"]
                for command in hint.get("commands", [])
            ]
            self.assertIn("java -version", hint_commands)

    def test_compute_correctness(self) -> None:
        judgments = [
            FeatureJudgment("a", "pass", 0.9, "ok"),
            FeatureJudgment("b", "fail", 0.8, "no"),
            FeatureJudgment("c", "uncertain", 0.4, "maybe"),
        ]
        passed, failed, uncertain, pct = compute_correctness(judgments)
        self.assertEqual((passed, failed, uncertain), (1, 1, 1))
        self.assertAlmostEqual(pct, 33.333, places=2)

    def test_parse_judge_json(self) -> None:
        parsed = _parse_judge_json(
            '{"verdict":"pass","confidence":0.95,"reason":"works","evidence_used":["visible_text"]}'
        )
        self.assertEqual(parsed["verdict"], "pass")

    def test_dry_run_judge(self) -> None:
        judge = JudgeClient(dry_run=True)
        feature = FeatureCheck("f1", "Title", "desc", "accept")
        evidence = EvidencePacket(feature_id="f1", visible_text="hello")
        result = judge.judge_feature(feature, evidence, None)
        self.assertEqual(result.verdict, "pass")

    def test_prd_context_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prd = Path(tmp) / "PRD.md"
            prd.write_text(
                "## Goals\n- Goal one\n\n## Success Criteria\n- Users can search\n",
                encoding="utf-8",
            )
            context = load_prd_context(prd)
            self.assertIn("Success Criteria", context or "")
            self.assertIn("search", context or "")

    def test_report_render(self) -> None:
        summary = WebEvalSummary(
            eval_id="test-id",
            label="test",
            started_at="t0",
            ended_at="t1",
            project_path="/tmp/project",
            features_path="/tmp/features.yaml",
            prd_path=None,
            base_url="http://127.0.0.1:3000",
            total_features=1,
            passed=1,
            failed=0,
            uncertain=0,
            correctness_pct=100.0,
            judgments=[FeatureJudgment("f1", "pass", 1.0, "ok")],
        )
        md = render_markdown(summary, Path("/tmp/evals/test-id"))
        self.assertIn("100.0%", md)
        self.assertIn("f1", md)

    def test_runner_records_startup_failure_as_zero_percent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            (project / "package.json").write_text(
                json.dumps({"scripts": {"start": "node server.js"}}),
                encoding="utf-8",
            )
            (project / "server.js").write_text("console.error('boom')\n", encoding="utf-8")
            features_path = root / "features.yaml"
            write_features(
                features_path,
                [
                    FeatureCheck("search", "Search", "Users can search", "Search returns results"),
                    FeatureCheck("filters", "Filters", "Users can filter", "Filtering narrows results"),
                ],
            )

            runner = WebEvalRunner(root_dir=root)
            options = WebEvalOptions(
                project_path=project,
                features_path=features_path,
                label="startup-failure",
                eval_id="eval-startup-failure",
                dry_run=True,
                agentic_evidence=False,
            )

            startup_error = (
                "App process failed before becoming ready at http://127.0.0.1:3000/. "
                "start command exited with code 1:\n"
                "npm ERR! Missing script: \"start\""
            )

            with mock.patch.object(WebEvalRunner, "preflight", return_value=[]), \
                mock.patch("bench.web_eval.runner.EVALS_DIR", root / "evals"), \
                mock.patch("bench.web_eval.runner.collect_setup_context", return_value={}), \
                mock.patch("bench.web_eval.runner.run_project_setup", return_value=[]), \
                mock.patch("bench.web_eval.runner.load_project_env", return_value={}), \
                mock.patch("bench.web_eval.runner.JudgeClient.plan_setup_commands", return_value=[]), \
                mock.patch("bench.web_eval.runner.AppServer.start", side_effect=RuntimeError(startup_error)):
                summary = runner.run(options)

            self.assertEqual(summary.correctness_pct, 0.0)
            self.assertEqual(summary.failed, 2)
            self.assertEqual(summary.passed, 0)
            self.assertTrue(all(j.verdict == "fail" for j in summary.judgments))
            self.assertIn("Application startup/readiness failed", summary.notes or "")

            output_dir = root / "evals" / "eval-startup-failure"
            run_artifact = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_artifact["app_start"]["status"], "failed")
            self.assertEqual(run_artifact["app_start"]["error"], startup_error)

            summary_artifact = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_artifact["correctness_pct"], 0.0)

            for feature_id in ("search", "filters"):
                evidence = json.loads((output_dir / "evidence" / f"{feature_id}.json").read_text(encoding="utf-8"))
                judgment = json.loads((output_dir / "judgments" / f"{feature_id}.json").read_text(encoding="utf-8"))
                self.assertTrue(evidence["checks"]["app_startup_failed"])
                self.assertEqual(evidence["error"], startup_error)
                self.assertEqual(judgment["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
