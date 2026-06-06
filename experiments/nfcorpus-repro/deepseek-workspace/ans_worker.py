"""
Anserini worker module - executes real Anserini commands via the fatjar.
All commands use subprocess with the downloaded fatjar.
"""

import os
import re
import json
import subprocess
import shlex
import time
from pathlib import Path

class AnseriniWorker:
    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)
        self.cache_dir = self.workspace / "cache"
        self.cache_dir.mkdir(exist_ok=True)

        # Discover fatjar
        jars = sorted(self.workspace.glob("anserini-*-fatjar.jar"))
        if not jars:
            self.fatjar = None
            self.fatjar_version = None
        else:
            self.fatjar = str(jars[-1])
            m = re.search(r'anserini-([\d.]+)-fatjar\.jar', os.path.basename(self.fatjar))
            self.fatjar_version = m.group(1) if m else None

        # State tracking
        self.cmd_history = []          # list of {cmd, output_preview, exit_code, elapsed_ms}
        self.artifact_paths = {}       # artifact_name -> path
        self.eval_results = None       # cached eval results
        self.eval_elapsed = None

        # NFCorpus constants (from beir.core reproduction config)
        self.nfcorpus_index_name = "beir-v1.0.0-nfcorpus.flat"
        self.nfcorpus_topics_name = "beir-nfcorpus"
        self.nfcorpus_eval_key = "beir-v1.0.0-nfcorpus.test"
        self.nfcorpus_expected_ndcg10 = 0.3218
        self.nfcorpus_expected_map = None  # Not in beir.core config

    def _run(self, cmd: list[str], timeout_sec: int = 600) -> dict:
        """Run a command and return result dict. Always logs to cmd_history."""
        cmd_str = " ".join(shlex.quote(str(x)) for x in cmd)
        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=str(self.workspace),
                env={**os.environ}
            )
            elapsed_ms = int((time.time() - start) * 1000)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            output = (stdout + stderr).strip()
            preview = output[:2000] if len(output) > 2000 else output
            result = {
                "cmd": cmd_str,
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "elapsed_ms": elapsed_ms,
                "output_preview": preview,
                "success": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start) * 1000)
            result = {
                "cmd": cmd_str,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout_sec}s",
                "elapsed_ms": elapsed_ms,
                "output_preview": f"Command timed out after {timeout_sec}s",
                "success": False,
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            result = {
                "cmd": cmd_str,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "elapsed_ms": elapsed_ms,
                "output_preview": str(e),
                "success": False,
            }
        self.cmd_history.append(result)
        return result

    # ------------------------------------------------------------------ #
    # Status / Discovery
    # ------------------------------------------------------------------ #

    def check_java(self) -> dict:
        r = self._run(["java", "-version"], timeout_sec=30)
        version = ""
        combined = r["stdout"] + r["stderr"]
        m = re.search(r'version "([^"]+)"', combined)
        if m:
            version = m.group(1)
        m2 = re.search(r'openjdk version "([^"]+)"', combined)
        if m2:
            version = m2.group(1)
        java_ok = r["success"] and "21" in version
        return {
            "available": r["success"],
            "version": version,
            "is_java21": java_ok,
        }

    def check_fatjar(self) -> dict:
        if self.fatjar and Path(self.fatjar).exists():
            return {"available": True, "path": self.fatjar, "version": self.fatjar_version}
        return {"available": False, "path": None, "version": None}

    def check_nfcorpus_index(self) -> dict:
        """Check if NFCorpus prebuilt index is available locally.
        The index is cached under ~/.cache/anserini/indexes/<name>"""
        cache_base = Path.home() / ".cache" / "anserini" / "indexes" / self.nfcorpus_index_name
        if cache_base.exists() and any(cache_base.iterdir()):
            return {"available": True, "path": str(cache_base), "index_name": self.nfcorpus_index_name}
        # Also check for lucene index at the same path
        return {"available": False, "path": str(cache_base), "index_name": self.nfcorpus_index_name,
                "note": "Index will be auto-downloaded on first use."}

    # ------------------------------------------------------------------ #
    # Smoke test (CACM)
    # ------------------------------------------------------------------ #

    def run_smoke_test(self) -> dict:
        """Run the CACM smoke test to verify fatjar works."""
        run_path = self.workspace / "run.cacm.bm25.txt"
        r = self._run([
            "java", "-cp", self.fatjar,
            "io.anserini.search.SearchCollection",
            "-threads", "1",
            "-index", "cacm",
            "-topics", "cacm",
            "-output", str(run_path),
            "-hits", "1000",
            "-bm25",
        ], timeout_sec=120)
        run_ok = r["success"] and run_path.exists()

        eval_ok = False
        if run_ok:
            ev = self._run([
                "java", "-cp", self.fatjar,
                "io.anserini.eval.TrecEval",
                "-c", "-m", "map", "-m", "P.30",
                "cacm", str(run_path),
            ], timeout_sec=60)
            combined = ev["stdout"] + ev["stderr"]
            map_match = "map" in combined and "0.3123" in combined
            p30_match = "P_30" in combined and "0.1942" in combined
            eval_ok = ev["success"] and map_match and p30_match
            self.artifact_paths["cacm_run"] = str(run_path)

        return {
            "search_ok": run_ok,
            "eval_ok": eval_ok,
            "run_path": str(run_path) if run_ok else None,
        }

    # ------------------------------------------------------------------ #
    # Live Search
    # ------------------------------------------------------------------ #

    def search(self, query: str, hits: int = 10) -> dict:
        """Run a live search against the NFCorpus prebuilt index."""
        r = self._run([
            "java", "-cp", self.fatjar,
            "io.anserini.cli.Search",
            "--index", self.nfcorpus_index_name,
            "--query", query,
            "--hits", str(hits),
            "--json",
        ], timeout_sec=120)

        results = []
        raw_output = r["stdout"]
        if r["success"]:
            # Anserini --json output is a single JSON object with "candidates" array
            try:
                data = json.loads(raw_output.strip())
                if isinstance(data, dict):
                    candidates = data.get("candidates", [])
                elif isinstance(data, list):
                    candidates = data
                else:
                    candidates = []
                for cand in candidates:
                    # Flatten nested structure for easier frontend consumption
                    doc = cand.get("doc", {})
                    results.append({
                        "docid": cand.get("docid", "?"),
                        "score": cand.get("score"),
                        "title": doc.get("title", ""),
                        "text": doc.get("text", ""),
                        "contents": doc.get("title", "") + " " + doc.get("text", ""),
                        "metadata": doc.get("metadata", {}),
                    })
            except json.JSONDecodeError:
                pass

        return {
            "query": query,
            "hits": hits,
            "results": results,
            "elapsed_ms": r["elapsed_ms"],
            "exit_code": r["exit_code"],
            "raw_output": r["output_preview"] if not r["success"] else None,
        }

    # ------------------------------------------------------------------ #
    # Batch Evaluation
    # ------------------------------------------------------------------ #

    def run_evaluation(self, force: bool = False) -> dict:
        """Run the BM25 batch search + evaluation for NFCorpus.
        Uses cached results unless force=True.
        """
        run_path = self.cache_dir / "run.nfcorpus.bm25.flat.txt"
        run_path_str = str(run_path)

        need_search = force or not run_path.exists()

        if need_search:
            search_r = self._run([
                "java", "-cp", self.fatjar,
                "io.anserini.search.SearchCollection",
                "-threads", "8",
                "-index", self.nfcorpus_index_name,
                "-topics", self.nfcorpus_topics_name,
                "-output", run_path_str,
                "-bm25",
                "-removeQuery",
            ], timeout_sec=600)
            if not search_r["success"]:
                return {
                    "status": "error",
                    "stage": "search",
                    "error": search_r["stderr"][:500],
                    "search_result": search_r,
                }
            self.artifact_paths["nfcorpus_run"] = run_path_str

        # Now evaluate
        eval_r = self._run([
            "java", "-cp", self.fatjar,
            "io.anserini.eval.TrecEval",
            "-c", "-m", "ndcg_cut.10",
            self.nfcorpus_eval_key,
            run_path_str,
        ], timeout_sec=120)

        # Parse eval output
        observed = self._parse_trec_eval(eval_r["stdout"])
        expected = {"ndcg_cut_10": self.nfcorpus_expected_ndcg10}
        comparison = self._compare_metrics(observed, expected)

        self.eval_results = {
            "observed": observed,
            "expected": expected,
            "comparison": comparison,
            "run_path": run_path_str,
            "eval_raw": eval_r["stdout"],
            "search_elapsed_ms": search_r["elapsed_ms"] if need_search else 0,
            "eval_elapsed_ms": eval_r["elapsed_ms"],
            "was_cached": not need_search,
        }
        self.artifact_paths["nfcorpus_eval"] = run_path_str
        return {"status": "ok", **self.eval_results}

    def _parse_trec_eval(self, output: str) -> dict:
        """Parse trec_eval output into a dict of metric_name -> value."""
        metrics = {}
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 3:
                metric_name = parts[0].replace(".", "_")
                try:
                    value = float(parts[2])
                    metrics[metric_name] = value
                except ValueError:
                    pass
        return metrics

    def _compare_metrics(self, observed: dict, expected: dict) -> list[dict]:
        comparisons = []
        for key, exp_val in expected.items():
            obs_val = observed.get(key)
            if obs_val is None:
                comparisons.append({
                    "metric": key, "expected": exp_val, "observed": None,
                    "delta": None, "status": "missing",
                })
            else:
                delta = obs_val - exp_val
                abs_delta = abs(delta)
                if abs_delta < 0.0001:
                    status = "match"
                elif abs_delta < 0.01:
                    status = "close"
                else:
                    status = "fail"
                comparisons.append({
                    "metric": key, "expected": exp_val, "observed": obs_val,
                    "delta": round(delta, 6), "status": status,
                })
        return comparisons

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def get_commands(self) -> list[dict]:
        return [
            {
                "category": c["cmd"].split()[0] if c["cmd"] else "",
                "command": c["cmd"],
                "output_preview": c["output_preview"],
                "exit_code": c["exit_code"],
                "elapsed_ms": c["elapsed_ms"],
            }
            for c in self.cmd_history
        ]

    def get_artifacts(self) -> dict:
        artifacts = {}
        for name, path in self.artifact_paths.items():
            p = Path(path)
            if p.exists():
                size = p.stat().st_size
                try:
                    with open(p, "r") as f:
                        preview = f.read(2000)
                except Exception:
                    preview = "[binary or cannot read]"
            else:
                size = 0
                preview = "[file not found]"
            artifacts[name] = {"path": path, "size": size, "preview": preview}
        return artifacts

    def full_readiness(self) -> dict:
        java = self.check_java()
        fatjar = self.check_fatjar()
        index = self.check_nfcorpus_index()
        smoke = None
        eval_ready = False
        search_ready = fatjar["available"] and java["is_java21"]

        # Only run smoke if fatjar exists and not already run
        if fatjar["available"]:
            smoke = self.run_smoke_test()
            search_ready = smoke["search_ok"]
            eval_ready = smoke["eval_ok"]

        # If we have evaluation cached, include it
        eval_info = None
        if self.eval_results:
            eval_info = {
                "observed": self.eval_results["observed"],
                "expected": self.eval_results["expected"],
                "comparison": self.eval_results["comparison"],
                "was_cached": self.eval_results["was_cached"],
            }

        return {
            "app_status": "ready" if search_ready else "initializing",
            "java": java,
            "fatjar": fatjar,
            "nfcorpus_index": index,
            "smoke_test": smoke,
            "search_available": search_ready,
            "evaluation_available": eval_ready,
            "evaluation": eval_info,
        }
