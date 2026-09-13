from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from scripts.trajectory_parser import (
    SCHEMA_VERSION,
    discover_event_files,
    parse_events,
    process_run,
    semantic_action,
    shell_files_touched,
)


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def _single_call_events(model: str, call_id: str = "call-1") -> list[dict]:
    return [
        {
            "type": "session",
            "cwd": f"/repo/experiments/frontend/{model}-workspace",
            "timestamp": "2026-06-06T00:00:00Z",
        },
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "model": f"{model}-model",
                "timestamp": 1_780_713_325_000,
                "usage": {"input": 2, "output": 3, "cacheRead": 5, "cacheWrite": 7, "totalTokens": 17},
                "content": [
                    {"type": "toolCall", "id": call_id, "name": "read", "arguments": {"path": "PRD.md"}}
                ],
            },
        },
        {"type": "tool_execution_start", "toolCallId": call_id, "toolName": "read", "args": {"path": "PRD.md"}},
        {
            "type": "tool_execution_end",
            "toolCallId": call_id,
            "toolName": "read",
            "result": {"content": [{"type": "text", "text": "contents"}]},
            "isError": False,
        },
        {
            "type": "message_end",
            "message": {
                "role": "toolResult",
                "toolCallId": call_id,
                "toolName": "read",
                "timestamp": 1_780_713_326_250,
                "content": [{"type": "text", "text": "contents"}],
                "isError": False,
            },
        },
    ]


class TrajectoryParserTests(unittest.TestCase):
    def test_parse_parallel_calls_attributes_tokens_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "run-1" / "gpt" / "events.jsonl"
            events = _single_call_events("gpt")
            assistant = events[1]["message"]
            assistant["content"].append(
                {"type": "toolCall", "id": "call-2", "name": "write", "arguments": {"path": "app.py", "content": "pass"}}
            )
            events.extend(
                [
                    {"type": "tool_execution_start", "toolCallId": "call-2", "toolName": "write", "args": {"path": "app.py"}},
                    {"type": "tool_execution_end", "toolCallId": "call-2", "toolName": "write", "result": {}, "isError": True},
                    {
                        "type": "message_end",
                        "message": {
                            "role": "toolResult",
                            "toolCallId": "call-2",
                            "timestamp": 1_780_713_327_000,
                            "content": [{"type": "text", "text": "permission denied"}],
                            "isError": True,
                        },
                    },
                    {
                        "type": "message_end",
                        "message": {
                            "role": "assistant",
                            "model": "gpt-model",
                            "timestamp": 1_780_713_328_000,
                            "usage": {"input": 1, "output": 2, "totalTokens": 3},
                            "content": [{"type": "text", "text": "Finished."}],
                        },
                    },
                ]
            )
            _write_events(events_path, events)

            rows = parse_events(events_path)

            self.assertEqual([row["step"] for row in rows], [1, 2, 3])
            self.assertEqual(rows[0]["parallel_count"], 2)
            self.assertEqual(rows[1]["parallel_index"], 1)
            self.assertEqual(rows[0]["tokens"]["total"], 17)
            self.assertIsNone(rows[1]["tokens"])
            self.assertEqual(rows[0]["duration_ms"], 1250)
            self.assertTrue(rows[0]["success"])
            self.assertFalse(rows[1]["success"])
            self.assertEqual(rows[1]["error"], "permission denied")
            self.assertEqual(rows[1]["files_touched"], ["app.py"])
            self.assertEqual(rows[1]["semantic_action"], "edit")
            self.assertEqual(rows[2]["record_type"], "assistant")
            self.assertEqual(rows[2]["command_action"], "Finished.")
            self.assertEqual(rows[2]["tokens"]["total"], 3)
            self.assertEqual(rows[0]["task"], "frontend")
            self.assertEqual(rows[0]["model"], "gpt-model")

    def test_summary_metadata_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "run-1" / "gpt" / "events.jsonl"
            _write_events(events_path, _single_call_events("gpt"))
            summary = {
                "results": [
                    {
                        "model_key": "gpt",
                        "model_name": "preferred-model",
                        "workspace_path": "/repo/experiments/evaluator/gpt-workspace",
                    }
                ]
            }

            row = parse_events(events_path, summary)[0]

            self.assertEqual(row["task"], "evaluator")
            self.assertEqual(row["model"], "preferred-model")

    def test_incomplete_call_has_unknown_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "run-1" / "gpt" / "events.jsonl"
            _write_events(events_path, _single_call_events("gpt")[:3])

            row = parse_events(events_path)[0]

            self.assertIsNone(row["success"])
            self.assertIsNone(row["duration_ms"])

    def test_semantic_action_categories(self) -> None:
        cases = [
            ("ls", ".", [], "inspect"),
            ("find", "*.py", [], "search"),
            ("read", "README.md", [], "read"),
            ("write", "app.py", ["app.py"], "edit"),
            ("bash", "python server.py", [], "execute"),
            ("bash", "lsof -i :3000", [], "debug"),
            ("bash", "java TrecEval run.txt", [], "evaluate"),
            ("bash", "pytest", [], "validate"),
        ]
        for tool, action, touched, expected in cases:
            with self.subTest(tool=tool, action=action):
                self.assertEqual(semantic_action(tool, action, touched), expected)

    def test_semantic_action_ignores_keywords_in_workspace_paths(self) -> None:
        workspace = "/repo/experiments/evaluator-no-rewrite/gpt-workspace"
        cases = [
            (f"cd {workspace} && npm install", "edit"),
            (f"ls {workspace}/benchmark-results", "inspect"),
            (f"cat {workspace}/test-output.txt", "read"),
            (f"npm --prefix {workspace} install", "edit"),
            (f"git -C {workspace}/test-output status", "inspect"),
            ('node -e "test(items)"', "execute"),
            ('python -c "print(benchmark)"', "execute"),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(
                    semantic_action("bash", command, shell_files_touched(command)),
                    expected,
                )

    def test_shell_files_touched_is_conservative_and_deduplicated(self) -> None:
        command = "cat input > output.txt && touch marker > marker.log\ncp source target && echo bad 2>/dev/null"
        self.assertEqual(shell_files_touched(command), ["output.txt", "marker.log", "marker", "target"])

    def test_shell_files_touched_ignores_quoted_greater_than_signs_and_arrows(self) -> None:
        command = 'node -e "items.map(x => x.name)" && echo "a > b" && cp "a>b" target'
        self.assertEqual(shell_files_touched(command), ["target"])

    def test_shell_files_touched_ignores_heredoc_body(self) -> None:
        command = """python - <<'PY'
items = [x for x in values if x > 0]
print(items)
PY
echo done > output.txt
"""
        self.assertEqual(shell_files_touched(command), ["output.txt"])

    def test_process_run_adds_only_missing_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            gpt_events = run_dir / "gpt" / "events.jsonl"
            claude_events = run_dir / "claude" / "events.jsonl"
            _write_events(gpt_events, _single_call_events("gpt", "gpt-call"))
            _write_events(claude_events, _single_call_events("claude", "claude-call"))

            first = process_run(run_dir, [gpt_events])
            second = process_run(run_dir, [gpt_events, claude_events])
            third = process_run(run_dir, [gpt_events, claude_events])

            self.assertEqual(first, (1, 0, 1))
            self.assertEqual(second, (1, 1, 1))
            self.assertEqual(third, (0, 2, 0))
            rows = [json.loads(line) for line in (run_dir / "trajectory.jsonl").read_text().splitlines()]
            self.assertEqual([row["model_key"] for row in rows], ["gpt", "claude"])
            self.assertTrue(all(row["schema_version"] == SCHEMA_VERSION for row in rows))

    def test_existing_output_with_wrong_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            events_path = run_dir / "gpt" / "events.jsonl"
            _write_events(events_path, _single_call_events("gpt"))
            (run_dir / "trajectory.jsonl").write_text(
                json.dumps({"schema_version": 999, "run_id": "run-1", "model_key": "gpt"}) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported schema_version"):
                process_run(run_dir, [events_path])

    def test_malformed_source_line_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "run-1" / "gpt" / "events.jsonl"
            _write_events(events_path, _single_call_events("gpt"))
            original = events_path.read_text(encoding="utf-8")
            events_path.write_text("not-json\n" + original, encoding="utf-8")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                rows = parse_events(events_path)

            self.assertEqual(len(rows), 1)
            self.assertIn("skipping malformed JSON", stderr.getvalue())

    def test_discovery_accepts_direct_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "run-1" / "gpt" / "events.jsonl"
            second = root / "run-2" / "claude" / "events.jsonl"
            _write_events(first, [])
            _write_events(second, [])

            from_directory = discover_event_files([root])
            from_mixed_inputs = discover_event_files([first, root / "run-2"])

            self.assertEqual(from_directory, sorted([first.resolve(), second.resolve()], key=str))
            self.assertEqual(from_mixed_inputs, sorted([first.resolve(), second.resolve()], key=str))


if __name__ == "__main__":
    unittest.main()
