from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.backfill_token_metrics import backfill_run, metrics_from_events


class TokenBackfillTests(unittest.TestCase):
    def test_metrics_from_events_includes_cache_write_and_prompt_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "events.jsonl"
            events = [
                {"type": "message_end", "message": {"role": "user"}},
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "usage": {
                            "input": 6,
                            "output": 104,
                            "cacheRead": 0,
                            "cacheWrite": 4458,
                            "totalTokens": 4568,
                            "cost": {"total": 0.0304925},
                        },
                    },
                },
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "usage": {
                            "input": 1,
                            "output": 62,
                            "cacheRead": 4458,
                            "cacheWrite": 2997,
                            "totalTokens": 7518,
                            "cost": {"total": 0.02251525},
                        },
                    },
                },
            ]
            events_path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )

            metrics = metrics_from_events(events_path)

            self.assertIsNotNone(metrics)
            assert metrics is not None
            self.assertEqual(metrics["input_tokens"], 7)
            self.assertEqual(metrics["output_tokens"], 166)
            self.assertEqual(metrics["cache_read_tokens"], 4458)
            self.assertEqual(metrics["cache_write_tokens"], 7455)
            self.assertEqual(metrics["prompt_tokens"], 11920)
            self.assertEqual(metrics["total_tokens"], 12086)
            self.assertEqual(metrics["requests"], 2)

    def test_backfill_run_updates_result_summary_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "20260606-test"
            model_dir = run_dir / "claude"
            model_dir.mkdir(parents=True)
            events_path = model_dir / "events.jsonl"
            result_path = model_dir / "result.json"
            summary_path = run_dir / "summary.json"

            events_path.write_text(
                json.dumps(
                    {
                        "type": "message_end",
                        "message": {
                            "role": "assistant",
                            "usage": {
                                "input": 1,
                                "output": 2,
                                "cacheRead": 3,
                                "cacheWrite": 4,
                                "totalTokens": 10,
                                "cost": {"total": 0.5},
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = {
                "model_key": "claude",
                "status": "completed",
                "duration_ms": 123,
                "exit_code": 0,
                "events_path": str(events_path),
                "metrics": {"input_tokens": 1, "output_tokens": 2, "cache_read_tokens": 3},
            }
            result_path.write_text(json.dumps(result), encoding="utf-8")
            summary_path.write_text(
                json.dumps({"results": [result], "totals": {}}),
                encoding="utf-8",
            )

            changed = backfill_run(run_dir, dry_run=False)

            self.assertEqual(changed, ["20260606-test/claude"])
            repaired_result = json.loads(result_path.read_text(encoding="utf-8"))
            repaired_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            metrics = repaired_result["metrics"]
            self.assertEqual(metrics["cache_write_tokens"], 4)
            self.assertEqual(metrics["prompt_tokens"], 8)
            self.assertEqual(repaired_summary["totals"]["cache_write_tokens"], 4)
            self.assertEqual(repaired_summary["totals"]["prompt_tokens"], 8)

            with (run_dir / "summary.csv").open(encoding="utf-8", newline="") as file_obj:
                rows = list(csv.DictReader(file_obj))
            self.assertEqual(rows[0]["cache_write_tokens"], "4")
            self.assertEqual(rows[0]["prompt_tokens"], "8")


if __name__ == "__main__":
    unittest.main()
