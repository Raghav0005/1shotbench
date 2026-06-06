import unittest

from fastapi import HTTPException

from bench.web import _discover_experiments, _relative_task_dir


class BenchmarkWebTests(unittest.TestCase):
    def test_discovers_experiment_directories(self) -> None:
        experiments = {item["path"]: item for item in _discover_experiments()}

        self.assertIn("experiments/frontend", experiments)
        self.assertIn("experiments/evaluator", experiments)
        self.assertIn("experiments/nfcorpus-repro", experiments)
        self.assertGreaterEqual(experiments["experiments/frontend"]["model_count"], 1)

    def test_rejects_task_dirs_outside_repo(self) -> None:
        with self.assertRaises(HTTPException):
            _relative_task_dir("/tmp")


if __name__ == "__main__":
    unittest.main()
