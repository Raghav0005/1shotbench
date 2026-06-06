"""Pytest fixtures: boot the FastAPI app in a subprocess for browser tests."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("TEST_PORT", "18181"))
REST_PORT = int(os.environ.get("TEST_ANSERINI_REST_PORT", "18182"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="session")
def app_server():
    if not _free(PORT):
        raise RuntimeError(f"Test port {PORT} already in use; pick another via TEST_PORT.")
    env = os.environ.copy()
    env.update({
        "PORT": str(PORT),
        "HOST": "127.0.0.1",
        "ANSERINI_REST_PORT": str(REST_PORT),
    })
    log_path = ROOT / "cache" / "logs" / "e2e-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=str(ROOT),
        env=env,
        stdout=fh,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 300  # cold start may download fatjar + index
    last_phase = "?"
    try:
        while time.time() < deadline:
            try:
                r = httpx.get(f"{BASE_URL}/health", timeout=5.0)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    break
                last_phase = r.json().get("phase", "?") if r.status_code in (200, 503) else "?"
                if last_phase.startswith("failed"):
                    raise RuntimeError(f"App failed during setup: phase={last_phase}, body={r.text[:300]}")
            except httpx.RequestError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError(f"Workbench did not reach phase=ready (last phase={last_phase}).")
        yield BASE_URL
    finally:
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
        fh.close()
        # Belt and suspenders: shoot down any straggling Anserini REST subprocess.
        try:
            subprocess.run(
                ["bash", "-lc", f"PID=$(lsof -ti :{REST_PORT} 2>/dev/null); [ -n \"$PID\" ] && kill $PID || true"],
                check=False,
            )
        except Exception:
            pass


@pytest.fixture(scope="session")
def browser_ctx():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        yield ctx
        ctx.close()
        browser.close()


@pytest.fixture()
def page(browser_ctx):
    pg = browser_ctx.new_page()
    yield pg
    pg.close()
