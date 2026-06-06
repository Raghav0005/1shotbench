"""
Anserini integration: fatjar management, smoke test, search, evaluation.
All commands are real Anserini CLI invocations — no mocking.
"""

import json
import os
import re
import subprocess
import time
import threading
from typing import Any

from .config import Config


class AnseriniManager:
    """Manages Anserini fatjar lifecycle, NFCorpus search, and evaluation."""

    def __init__(self):
        self.jar_path: str = Config.ANSERINI_JAR
        self.version: str = Config.ANSERINI_VERSION
        self.java_ok: bool = False
        self.java_version: str = ""
        self.fatjar_ok: bool = False
        self.smoke_test_passed: bool = False
        self.smoke_test_log: str = ""
        self.nfcorpus_index_ready: bool = False
        self.nfcorpus_topics_ready: bool = False
        self.reproduction_discovered: bool = False
        self.reproduction_config: dict = {}
        self.expected_metrics: dict = {}
        self.commands_log: list = []
        self.artifacts: dict = {}
        self._setup_lock = threading.Lock()
        self._setup_done = False
        self._setup_error: str = ""
        self._eval_result: dict = {}
        self._eval_log: str = ""
        self._eval_cached: bool = False

    def run_command(self, cmd: list[str], timeout: int = 600, cwd: str = None) -> dict:
        """Execute a command, capture output, and log it."""
        cmd_str = " ".join(cmd)
        self.commands_log.append({
            "command": cmd_str,
            "cwd": cwd or os.getcwd(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "status": "running"
        })
        entry = self.commands_log[-1]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )
            entry["status"] = "success" if result.returncode == 0 else "error"
            entry["returncode"] = result.returncode
            entry["stdout"] = result.stdout[-5000:] if result.stdout else ""
            entry["stderr"] = result.stderr[-5000:] if result.stderr else ""
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            entry["status"] = "timeout"
            entry["error"] = f"Command timed out after {timeout}s"
            return {"ok": False, "error": f"Timeout after {timeout}s"}
        except FileNotFoundError as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            return {"ok": False, "error": str(e)}

    def check_java(self) -> bool:
        """Check Java availability and version."""
        result = self.run_command(["java", "-version"])
        if not result["ok"]:
            self.java_ok = False
            self.java_version = "not found"
            return False
        # Java prints version to stderr
        output = result.get("stderr", "") or result.get("stdout", "")
        self.java_version = output.strip().split("\n")[0] if output else "unknown"
        # Check for Java 21
        match = re.search(r'"(\d+)', output)
        if match:
            major = int(match.group(1))
            self.java_ok = major >= 17  # Accept 17+ for compatibility
        else:
            self.java_ok = True  # Assume OK if we can't parse
        return self.java_ok

    def discover_latest_version(self) -> str:
        """Discover latest Anserini version from Maven Central."""
        result = self.run_command([
            "curl", "-sS",
            "https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml"
        ])
        if result["ok"]:
            match = re.search(r"<release>(.*?)</release>", result["stdout"])
            if match:
                self.version = match.group(1)
                return self.version
        return ""

    def download_fatjar(self, version: str = None) -> bool:
        """Download Anserini fatjar from Maven Central."""
        ver = version or self.version
        if not ver:
            ver = self.discover_latest_version()
        if not ver:
            return False

        jar_name = f"anserini-{ver}-fatjar.jar"
        jar_path = os.path.join(Config.CACHE_DIR, jar_name)

        if os.path.exists(jar_path) and os.path.getsize(jar_path) > 1_000_000:
            self.jar_path = jar_path
            self.version = ver
            Config.ANSERINI_JAR = jar_path
            self.fatjar_ok = True
            self.artifacts["fatjar"] = jar_path
            return True

        url = f"https://repo1.maven.org/maven2/io/anserini/anserini/{ver}/{jar_name}"
        result = self.run_command([
            "curl", "-fL", "-o", jar_path, url
        ], timeout=300)

        if result["ok"] and os.path.exists(jar_path):
            self.jar_path = jar_path
            self.version = ver
            Config.ANSERINI_JAR = jar_path
            self.fatjar_ok = True
            self.artifacts["fatjar"] = jar_path
            return True
        return False

    def run_smoke_test(self) -> bool:
        """Run the CACM smoke test to verify the fatjar works."""
        if not self.fatjar_ok:
            return False

        run_file = os.path.join(Config.RUNS_DIR, "run.cacm.bm25.txt")
        cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.search.SearchCollection",
            "-threads", "1",
            "-index", "cacm",
            "-topics", "cacm",
            "-output", run_file,
            "-hits", "1000",
            "-bm25"
        ]
        result = self.run_command(cmd, timeout=120)
        self.smoke_test_log = f"Command: {' '.join(cmd)}\n"

        if not result["ok"]:
            self.smoke_test_passed = False
            self.smoke_test_log += f"FAILED: {result.get('stderr', '')}"
            return False

        # Evaluate
        eval_cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.eval.TrecEval",
            "-c", "-m", "map", "-m", "P.30",
            "cacm", run_file
        ]
        eval_result = self.run_command(eval_cmd, timeout=60)
        self.smoke_test_log += f"\nEval command: {' '.join(eval_cmd)}\n"
        self.smoke_test_log += f"\nEval output:\n{eval_result.get('stdout', '')}"

        if eval_result["ok"]:
            output = eval_result["stdout"]
            if "0.3123" in output and "0.1942" in output:
                self.smoke_test_passed = True
                self.smoke_test_log += "\n✅ Smoke test PASSED: MAP=0.3123, P30=0.1942"
                return True

        self.smoke_test_passed = False
        self.smoke_test_log += "\n❌ Smoke test FAILED: expected scores not found"
        return False

    def discover_reproduction(self) -> dict:
        """Discover NFCorpus reproduction config using Anserini's reproduction tool."""
        if not self.fatjar_ok:
            return {}

        # Try listing reproduction configs for prebuilt indexes
        list_cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
            "--list"
        ]
        result = self.run_command(list_cmd, timeout=60)

        nfcorpus_config = None
        if result["ok"]:
            try:
                configs = json.loads(result["stdout"])
                # Look for NFCorpus config
                for cfg in configs:
                    if "nfcorpus" in str(cfg).lower():
                        nfcorpus_config = cfg if isinstance(cfg, str) else str(cfg)
                        break
            except json.JSONDecodeError:
                # Try grep for nfcorpus
                for line in result["stdout"].split("\n"):
                    if "nfcorpus" in line.lower():
                        nfcorpus_config = line.strip()
                        break

        if nfcorpus_config:
            # Try --show to get details
            show_cmd = [
                "java", "-cp", self.jar_path,
                "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
                "--config", nfcorpus_config,
                "--show"
            ]
            show_result = self.run_command(show_cmd, timeout=60)
            if show_result["ok"]:
                try:
                    self.reproduction_config = json.loads(show_result["stdout"])
                    self.reproduction_discovered = True
                except json.JSONDecodeError:
                    self.reproduction_config = {"raw": show_result["stdout"]}
                    self.reproduction_discovered = True

            # Try --dry-run for expected metrics
            dry_cmd = [
                "java", "-cp", self.jar_path,
                "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
                "--config", nfcorpus_config,
                "--dry-run"
            ]
            dry_result = self.run_command(dry_cmd, timeout=60)
            if dry_result["ok"]:
                self._parse_expected_metrics(dry_result["stdout"])

        self.artifacts["reproduction_config"] = nfcorpus_config
        return self.reproduction_config

    def _parse_expected_metrics(self, output: str):
        """Parse expected metrics from dry-run output."""
        # Look for patterns like: metric_name expected_value
        for line in output.split("\n"):
            line = line.strip()
            # Common patterns in Anserini reproduction output
            match = re.match(r"(\w[\w.]*)\s+.*?(\d+\.\d+)", line)
            if match and "expected" in line.lower():
                self.expected_metrics[match.group(1)] = float(match.group(2))

    def setup_nfcorpus(self) -> bool:
        """Set up NFCorpus index by triggering a small search to download the prebuilt index."""
        if not self.fatjar_ok:
            return False

        # Run a small search to trigger index download if needed
        # Uses the beir.core reproduction command format:
        # io.anserini.search.SearchCollection -threads $threads -index beir-v1.0.0-nfcorpus.flat
        #   -topics beir-nfcorpus -output $output -bm25 -removeQuery
        test_output = os.path.join(Config.RUNS_DIR, "nfcorpus.setup.test.txt")
        cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.search.SearchCollection",
            "-threads", "1",
            "-index", Config.NFCORPUS_INDEX,
            "-topics", Config.NFCORPUS_TOPICS,
            "-output", test_output,
            "-hits", "10",
            "-bm25",
            "-removeQuery"
        ]
        result = self.run_command(cmd, timeout=600)
        if result["ok"]:
            self.nfcorpus_index_ready = True
            self.nfcorpus_topics_ready = True
            self.artifacts["setup_run_file"] = test_output
            return True
        return False

    def run_bm25_evaluation(self, force: bool = False) -> dict:
        """Run full BM25 evaluation and compare with expected metrics."""
        if not force and self._eval_result and self._eval_cached:
            return self._eval_result

        if not self.fatjar_ok:
            return {"error": "Fatjar not available"}

        # Use config expected metrics if not discovered dynamically
        if not self.expected_metrics:
            self.expected_metrics = Config.EXPECTED_METRICS.copy()

        start_time = time.time()

        # Step 1: Run BM25 retrieval
        # Uses the beir.core reproduction command format
        run_file = os.path.join(Config.RUNS_DIR, "run.nfcorpus.bm25.txt")
        search_cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.search.SearchCollection",
            "-threads", "4",
            "-index", Config.NFCORPUS_INDEX,
            "-topics", Config.NFCORPUS_TOPICS,
            "-output", run_file,
            "-hits", "1000",
            "-bm25",
            "-removeQuery"
        ]
        search_result = self.run_command(search_cmd, timeout=900)

        if not search_result["ok"]:
            self._eval_result = {
                "error": "BM25 retrieval failed",
                "stderr": search_result.get("stderr", ""),
                "elapsed": time.time() - start_time
            }
            return self._eval_result

        self.artifacts["bm25_run_file"] = run_file

        # Step 2: Evaluate with multiple metrics
        eval_metrics = ["ndcg_cut.10", "map", "recall.100", "P.30"]
        eval_cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.eval.TrecEval",
            "-c"
        ]
        for m in eval_metrics:
            eval_cmd.extend(["-m", m])
        eval_cmd.extend([Config.NFCORPUS_EVAL_KEY, run_file])

        eval_result = self.run_command(eval_cmd, timeout=120)

        observed = {}
        eval_output = ""
        if eval_result["ok"]:
            eval_output = eval_result["stdout"]
            # Parse trec_eval output: metric \t all \t value
            for line in eval_output.strip().split("\n"):
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    metric_name = parts[0].strip()
                    try:
                        value = float(parts[2].strip())
                        observed[metric_name] = value
                    except ValueError:
                        pass

        eval_file = os.path.join(Config.EVALS_DIR, "eval.nfcorpus.bm25.txt")
        with open(eval_file, "w") as f:
            f.write(eval_output)

        self.artifacts["bm25_eval_file"] = eval_file

        # Step 3: Compare with expected metrics
        # Normalize metric names for comparison (trec_eval uses ndcg_cut_10, config uses nDCG@10)
        def normalize_metric(name: str) -> str:
            """Normalize metric name for comparison."""
            # Convert ndcg_cut_10 -> ndcg@10, P_30 -> p@30, etc.
            name = name.lower().replace("_cut", "").replace("_", "@")
            return name

        comparison = {}
        for metric, obs_val in observed.items():
            # Try exact match first, then normalized match
            exp_val = self.expected_metrics.get(metric)
            if exp_val is None:
                norm = normalize_metric(metric)
                for k, v in self.expected_metrics.items():
                    if normalize_metric(k) == norm:
                        exp_val = v
                        break
            entry = {"observed": obs_val, "expected": exp_val}
            if exp_val is not None:
                delta = obs_val - exp_val
                entry["delta"] = round(delta, 6)
                entry["delta_pct"] = round((delta / exp_val) * 100, 4) if exp_val != 0 else 0
                # Tolerance: pass if within 0.5%
                if abs(entry["delta_pct"]) < 0.5:
                    entry["status"] = "pass"
                elif abs(entry["delta_pct"]) < 2.0:
                    entry["status"] = "close"
                else:
                    entry["status"] = "fail"
            else:
                entry["status"] = "no_expected"
            comparison[metric] = entry

        elapsed = time.time() - start_time
        self._eval_result = {
            "observed": observed,
            "expected": self.expected_metrics,
            "comparison": comparison,
            "elapsed": round(elapsed, 2),
            "run_file": run_file,
            "eval_file": eval_file,
            "search_command": " ".join(search_cmd),
            "eval_command": " ".join(eval_cmd),
            "cached": False
        }
        self._eval_log = eval_output
        self._eval_cached = True

        # Save result for caching
        result_path = os.path.join(Config.EVALS_DIR, "eval_result.json")
        with open(result_path, "w") as f:
            json.dump(self._eval_result, f, indent=2, default=str)

        return self._eval_result

    def search(self, query: str, hits: int = 10) -> dict:
        """Run a live search query against NFCorpus."""
        if not self.fatjar_ok:
            return {"error": "Fatjar not available"}
        if not (self.nfcorpus_index_ready or self.smoke_test_passed):
            return {"error": "NFCorpus index not ready"}

        # Use Anserini CLI Search for single queries
        cmd = [
            "java", "-cp", self.jar_path,
            "io.anserini.cli.Search",
            "--index", Config.NFCORPUS_INDEX,
            "--query", query,
            "--hits", str(hits),
            "--json"
        ]

        result = self.run_command(cmd, timeout=120)

        if not result["ok"]:
            return {"error": result.get("stderr", "Search failed")}

        # Parse JSON results
        try:
            search_results = json.loads(result["stdout"])
            return {
                "query": query,
                "results": search_results.get("results", search_results) if isinstance(search_results, dict) else search_results,
                "command": " ".join(cmd)
            }
        except json.JSONDecodeError:
            # Fall back to parsing text output
            results = []
            for line in result["stdout"].strip().split("\n"):
                if not line.strip():
                    continue
                results.append({"raw": line})
            return {
                "query": query,
                "results": results,
                "raw_output": result["stdout"][:2000],
                "command": " ".join(cmd)
            }

    def get_status(self) -> dict:
        """Return current status of all components."""
        return {
            "java": {
                "ok": self.java_ok,
                "version": self.java_version
            },
            "fatjar": {
                "ok": self.fatjar_ok,
                "path": self.jar_path,
                "version": self.version
            },
            "smoke_test": {
                "passed": self.smoke_test_passed,
                "log": self.smoke_test_log[:2000] if self.smoke_test_log else ""
            },
            "nfcorpus": {
                "index_ready": self.nfcorpus_index_ready,
                "topics_ready": self.nfcorpus_topics_ready,
                "index_name": Config.NFCORPUS_INDEX
            },
            "reproduction": {
                "discovered": self.reproduction_discovered,
                "config": self.reproduction_config
            },
            "search_available": self.fatjar_ok and (self.nfcorpus_index_ready or self.smoke_test_passed),
            "evaluation_available": self.fatjar_ok and self.nfcorpus_index_ready,
            "artifacts": self.artifacts
        }


# Singleton
manager = AnseriniManager()


def initialize_async():
    """Run setup in background thread."""
    Config.ensure_dirs()

    with manager._setup_lock:
        if manager._setup_done:
            return

        # Step 1: Check Java
        manager.check_java()

        # Step 2: Download fatjar
        if not manager.jar_path or not os.path.exists(manager.jar_path):
            manager.download_fatjar()
        elif os.path.exists(manager.jar_path):
            manager.fatjar_ok = True

        # Step 3: Smoke test
        if manager.fatjar_ok:
            manager.run_smoke_test()

        # Step 4: Discover reproduction
        if manager.fatjar_ok:
            manager.discover_reproduction()

        # Step 5: Setup NFCorpus (download index)
        if manager.fatjar_ok:
            manager.setup_nfcorpus()

        # Step 6: Run evaluation (cached)
        if manager.fatjar_ok and manager.nfcorpus_index_ready:
            manager.run_bm25_evaluation()

        manager._setup_done = True
