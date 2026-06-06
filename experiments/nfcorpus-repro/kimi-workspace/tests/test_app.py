"""
Browser-driven end-to-end verification for the NFCorpus Diagnostics Workbench.

This test:
- Starts the Flask app on a local port.
- Opens the app in a headless browser.
- Verifies the health/readiness panel appears.
- Verifies NFCorpus is identified as the active dataset.
- Verifies Anserini setup status is visible.
- Runs a live NFCorpus query.
- Verifies ranked search results appear with doc ids, ranks, scores, and text.
- Verifies the evaluation panel displays numeric observed metrics.
- Verifies expected metric information appears.
- Verifies observed-vs-expected comparison appears.
- Verifies exact command text and artifact paths are visible.
- Verifies Docker/Render readiness contract is documented.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

APP_PORT = 18765
APP_URL = f"http://localhost:{APP_PORT}"


@pytest.fixture(scope="session")
def app_process():
    """Start the Flask app as a subprocess for the test session."""
    workspace = Path(__file__).parent.parent
    env = {
        **dict(subprocess.os.environ),
        "PORT": str(APP_PORT),
        "CACHE_DIR": str(workspace / ".cache"),
        "DATA_DIR": str(workspace / "data"),
        "INDEX_DIR": str(workspace / "indexes"),
        "RUNS_DIR": str(workspace / "runs"),
    }
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=workspace,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Wait for health endpoint to respond
    for _ in range(120):
        try:
            import urllib.request
            with urllib.request.urlopen(f"{APP_URL}/health", timeout=2) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        stdout, stderr = proc.stdout.read(), proc.stderr.read()
        proc.kill()
        raise RuntimeError(f"App did not start. stdout:\n{stdout}\nstderr:\n{stderr}")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_health_endpoint(app_process):
    import urllib.request
    with urllib.request.urlopen(f"{APP_URL}/health", timeout=10) as resp:
        assert resp.status == 200
        data = json.loads(resp.read())
        assert "status" in data
        assert data.get("java_ok") is True
        assert data.get("nfcorpus_ready") is True
        assert data.get("search_available") is True
        assert data.get("evaluation_available") is True


def test_dashboard_loads_and_shows_status(page: Page, app_process):
    page.goto(APP_URL)
    # Wait for the readiness panel to show Ready or at least contain status rows
    expect(page.locator("#status-content")).to_be_visible()
    # Verify dataset name appears in the footer/info area
    expect(page.locator("text=Dataset: NFCorpus")).to_be_visible()
    # Verify Anserini setup status is visible
    expect(page.locator("#java-status")).to_be_visible()
    expect(page.locator("#fatjar-status")).to_be_visible()


def test_live_search_returns_results(page: Page, app_process):
    page.goto(APP_URL)
    # Wait until search is available
    page.wait_for_selector("#search-btn:enabled", timeout=120_000)

    # Type a live query
    page.fill("#search-input", "statin breast cancer")
    page.click("#search-btn")

    # Wait for results to appear
    page.wait_for_selector(".result-item", timeout=30_000)

    # Verify results contain rank, docid, score, and text
    first = page.locator(".result-item").first
    expect(first).to_contain_text("Rank 1")
    expect(first).to_contain_text("DocID:")
    expect(first).to_contain_text("Score:")
    expect(first).to_contain_text("Statin")

    # Verify the search command is shown
    expect(page.locator("#search-results code")).to_contain_text("io.anserini.cli.Search")


def test_evaluation_panel_shows_metrics(page: Page, app_process):
    page.goto(APP_URL)
    # Wait until evaluation is ready
    page.wait_for_selector("#rerun-btn:enabled", timeout=120_000)

    # Verify numeric observed metrics appear inside the evaluation panel
    eval_panel = page.locator("#eval-content")
    expect(eval_panel).to_contain_text("0.3218")
    expect(eval_panel).to_contain_text("0.2457")

    # Verify expected metrics appear
    expect(page.locator("th:has-text('Expected')")).to_be_visible()

    # Verify status column with Pass/Close/Fail
    expect(eval_panel).to_contain_text("Pass")


def test_commands_and_artifacts_visible(page: Page, app_process):
    page.goto(APP_URL)
    page.wait_for_selector("#rerun-btn:enabled", timeout=120_000)

    # Verify exact command text is visible inside the commands panel
    commands_panel = page.locator("#commands-content")
    expect(commands_panel).to_contain_text("io.anserini.search.SearchCollection")
    expect(commands_panel).to_contain_text("io.anserini.eval.TrecEval")
    expect(commands_panel).to_contain_text("io.anserini.index.IndexCollection")

    # Verify artifact paths are visible
    expect(commands_panel).to_contain_text("run.nfcorpus.bm25.txt")
    expect(commands_panel).to_contain_text("eval.nfcorpus.bm25.txt")


def test_render_readiness_documented(page: Page, app_process):
    page.goto(APP_URL)
    # Verify Docker/Render readiness contract is documented in the UI footer
    expect(page.locator("text=Render Docker Ready")).to_be_visible()
    expect(page.locator("text=0.0.0.0")).to_be_visible()
    expect(page.locator("code:has-text('PORT')")).to_be_visible()
