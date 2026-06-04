"""Wrapper around io.anserini.api.RestServer for live NFCorpus search.

The Flask app boots this in the background, then proxies /api/search to it.
Keeping search inside the Anserini-provided REST endpoint avoids a per-query
JVM spawn and keeps live search backed by real Anserini code rather than a
custom search implementation (see anserini-cli skill).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from . import anserini


class RestServerProcess:
    def __init__(self, port: int, log_path: str) -> None:
        self.port = port
        self.host = "127.0.0.1"
        self.log_path = log_path
        self.process: Optional[subprocess.Popen] = None
        self.ready = False
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.ready_at: Optional[float] = None
        self.cmd: List[str] = []
        self._lock = threading.Lock()

    def cmd_string(self) -> str:
        return " ".join(shlex.quote(p) for p in self.cmd)

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                return
            self.cmd = anserini.java_cmd(
                "io.anserini.api.RestServer",
                ["--host", self.host, "--port", str(self.port)],
            )
            log_fh = open(self.log_path, "wb")
            self.process = subprocess.Popen(
                self.cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
            self.started_at = time.time()
        threading.Thread(target=self._wait_for_ready, daemon=True).start()

    def _wait_for_ready(self) -> None:
        deadline = time.time() + 120
        while time.time() < deadline:
            if self.process is None or self.process.poll() is not None:
                self.error = (
                    f"RestServer exited with code {self.process.returncode if self.process else 'n/a'}"
                )
                self.ready = False
                return
            try:
                # Hitting any /v1/{index}/search returns JSON quickly once
                # Jetty is ready. The first call may trigger index download,
                # which is fine -- we treat the JSON response as readiness.
                resp = requests.get(
                    self.base_url() + f"/v1/{anserini.NFCORPUS_INDEX}/search",
                    params={"query": "diet", "hits": 1},
                    timeout=60,
                )
                if resp.status_code in (200, 400):
                    self.ready = True
                    self.ready_at = time.time()
                    return
            except requests.RequestException:
                pass
            time.sleep(2)
        self.error = "RestServer did not become ready within 120s"

    def status(self) -> Dict[str, Any]:
        running = bool(self.process and self.process.poll() is None)
        return {
            "ready": self.ready,
            "running": running,
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url(),
            "cmd": self.cmd_string(),
            "started_at": self.started_at,
            "ready_at": self.ready_at,
            "error": self.error,
            "log_path": os.path.abspath(self.log_path),
        }

    def search(
        self,
        query: str,
        hits: int = 10,
        index: str = anserini.NFCORPUS_INDEX,
    ) -> Dict[str, Any]:
        url = self.base_url() + f"/v1/{index}/search"
        params = {"query": query, "hits": hits}
        t0 = time.time()
        resp = requests.get(url, params=params, timeout=120)
        elapsed = round(time.time() - t0, 3)
        resp.raise_for_status()
        return {
            "ok": True,
            "elapsed_seconds": elapsed,
            "request_url": resp.url,
            "payload": resp.json(),
        }

    def stop(self) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
