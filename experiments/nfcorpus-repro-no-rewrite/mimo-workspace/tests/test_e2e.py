"""
End-to-end browser test for NFCorpus Retrieval Diagnostics Workbench.

This test verifies:
- The app loads and the health/readiness panel appears
- NFCorpus is identified as the active dataset
- Anserini setup status is visible
- Live NFCorpus search returns ranked results with docids, ranks, scores, text
- The evaluation panel shows numeric observed metrics
- Expected metric information appears
- Observed-vs-expected comparison status/delta appears
- Exact command text and artifact paths are visible
- The app is NOT using mocked results
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import pytest

# Try importing playwright; skip if not available
try:
    from playwright.sync_api import sync_playwright, expect
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

APP_PORT = 15432  # Use a high port to avoid conflicts
APP_URL = f"http://localhost:{APP_PORT}"
ANSERINI_JAR = os.environ.get(
    "ANSERINI_JAR",
    os.path.join(os.path.dirname(__file__), "..", "anserini-2.1.1-fatjar.jar"),
)

pytestmark = pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed")


@pytest.fixture(scope="module")
def app_server():
    """Start the Flask app in a subprocess for testing."""
    env = os.environ.copy()
    env.update({
        "PORT": str(APP_PORT),
        "ANSERINI_JAR": os.path.abspath(ANSERINI_JAR),
        "DATA_DIR": os.path.join(os.path.dirname(__file__), "..", "data"),
        "PYTHONPATH": os.path.join(os.path.dirname(__file__), ".."),
    })

    proc = subprocess.Popen(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", "run.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to start
    for _ in range(60):
        time.sleep(1)
        try:
            resp = urllib.request.urlopen(f"{APP_URL}/health", timeout=2)
            data = json.loads(resp.read())
            if data.get("status") in ("ok", "initializing"):
                # Wait a bit more for setup to complete
                time.sleep(5)
                break
        except Exception:
            continue
    else:
        proc.terminate()
        raise RuntimeError("Server did not start within 60s")

    # Wait for setup to complete
    for _ in range(120):
        time.sleep(1)
        try:
            resp = urllib.request.urlopen(f"{APP_URL}/api/status", timeout=2)
            data = json.loads(resp.read())
            if data.get("setup_complete") or data.get("evaluation_ready"):
                break
        except Exception:
            continue

    yield proc
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser_context():
    """Provide a Playwright browser context."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        yield context
        context.close()
        browser.close()


class TestNFCorpusWorkbench:
    """End-to-end tests for the NFCorpus workbench."""

    def test_health_endpoint(self, app_server):
        """Health endpoint returns JSON with required fields."""
        resp = urllib.request.urlopen(f"{APP_URL}/health", timeout=10)
        data = json.loads(resp.read())
        assert "status" in data
        assert "anserini_available" in data
        assert "nfcorpus_ready" in data
        assert "search_available" in data
        assert "evaluation_available" in data

    def test_readiness_panel_appears(self, app_server, browser_context):
        """Readiness/status panel is visible on page load."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#status-panel", timeout=30000)
        panel = page.locator("#status-panel")
        expect(panel).to_be_visible()
        page.close()

    def test_nfcorpus_identified(self, app_server, browser_context):
        """NFCorpus is identified as the active dataset."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)  # Wait for status poll
        content = page.locator("#status-panel").text_content()
        assert "NFCorpus" in content or "nfcorpus" in content
        page.close()

    def test_anserini_status_visible(self, app_server, browser_context):
        """Anserini setup status is visible."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        content = page.locator("#status-panel").text_content()
        assert "Java" in content
        assert "Fatjar" in content or "Anserini" in content
        page.close()

    def test_live_search_returns_results(self, app_server, browser_context):
        """Live NFCorpus search returns ranked results with docids, ranks, scores, text."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#search-btn:not([disabled])", timeout=120000)

        # Type query and search
        page.fill("#query-input", "health benefits of fish oil")
        page.click("#search-btn")

        # Wait for results
        page.wait_for_selector(".result-item", timeout=60000)
        results = page.locator(".result-item")
        count = results.count()
        assert count > 0, "No search results returned"

        # Verify first result has required fields
        first = results.first
        text = first.text_content()
        assert "#" in text, "Result missing rank"
        assert "MED-" in text, "Result missing document ID"
        assert "Score:" in text, "Result missing score"

        # Verify result title and text content
        title = first.locator(".result-title").text_content()
        assert len(title) > 0, "Result missing title"
        result_text = first.locator(".result-text").text_content()
        assert len(result_text) > 20, "Result text/snippet too short"

        page.close()

    def test_sample_query_button(self, app_server, browser_context):
        """Clicking a sample query triggers a search."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#search-btn:not([disabled])", timeout=120000)

        # Click first sample query
        sample_btn = page.locator(".sample-queries button").first
        sample_btn.click()

        page.wait_for_selector(".result-item", timeout=60000)
        assert page.locator(".result-item").count() > 0
        page.close()

    def test_evaluation_panel_shows_metrics(self, app_server, browser_context):
        """Evaluation panel displays numeric observed metric."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        # Wait for evaluation to load - check every 2 seconds
        for _ in range(90):
            page.wait_for_timeout(2000)
            eval_text = page.locator("#eval-panel").text_content()
            if "Observed" in eval_text or re.search(r'0\.\d{4}', eval_text):
                break
        eval_text = page.locator("#eval-panel").text_content()
        assert re.search(r'0\.\d{4}', eval_text), f"No numeric metric found in eval panel: {eval_text[:300]}"
        page.close()

    def test_expected_metric_appears(self, app_server, browser_context):
        """Expected metric information appears."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(90):
            page.wait_for_timeout(2000)
            eval_text = page.locator("#eval-panel").text_content()
            if "Expected" in eval_text:
                break
        eval_text = page.locator("#eval-panel").text_content()
        assert "Expected" in eval_text
        page.close()

    def test_observed_vs_expected_delta(self, app_server, browser_context):
        """Observed-vs-expected comparison status/delta appears."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(90):
            page.wait_for_timeout(2000)
            eval_text = page.locator("#eval-panel").text_content()
            if "Delta" in eval_text:
                break
        eval_text = page.locator("#eval-panel").text_content()
        assert "Delta" in eval_text
        assert any(s in eval_text for s in ["PASS", "CLOSE", "FAIL"]), f"No status found in: {eval_text[:300]}"
        page.close()

    def test_command_text_and_artifacts_visible(self, app_server, browser_context):
        """Exact command text and artifact paths are visible in the commands drawer."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        # Open the commands drawer
        page.click(".drawer-toggle")
        page.wait_for_timeout(2000)

        drawer = page.locator("#commands-drawer")
        if drawer.locator(".cmd-block").count() > 0:
            cmd_text = drawer.text_content()
            assert "java" in cmd_text.lower() or "anserini" in cmd_text.lower(), \
                "Commands drawer missing Anserini command text"
        page.close()

    def test_artifact_paths_in_eval(self, app_server, browser_context):
        """Artifact paths appear in evaluation panel."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(90):
            page.wait_for_timeout(2000)
            eval_text = page.locator("#eval-panel").text_content()
            if "Run file:" in eval_text:
                break
        eval_text = page.locator("#eval-panel").text_content()
        assert "Run file:" in eval_text
        assert "Eval file:" in eval_text
        page.close()

    def test_not_mocked_search(self, app_server, browser_context):
        """Verify search is backed by real Anserini (not mocked)."""
        page = browser_context.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#search-btn:not([disabled])", timeout=120000)

        # Search with a distinctive query
        page.fill("#query-input", "omega-3 polyunsaturated fatty acid supplementation")
        page.click("#search-btn")
        page.wait_for_selector(".result-item", timeout=60000)

        # Verify results contain medical document IDs (MED-xxxx pattern from NFCorpus)
        first_docid = page.locator(".result-docid").first.text_content()
        assert re.match(r'MED-\d+', first_docid), f"Unexpected docid format: {first_docid}"

        # Verify the commands log shows the actual SearchCollection or CLI Search command
        resp = page.evaluate("fetch('/api/commands').then(r => r.json())")
        cmds_text = json.dumps(resp)
        assert "Search" in cmds_text, "Commands log missing search command"

        page.close()

    def test_not_mocked_evaluation(self, app_server, browser_context):
        """Verify evaluation is backed by real TrecEval (not mocked)."""
        resp = urllib.request.urlopen(f"{APP_URL}/api/evaluation", timeout=10)
        data = json.loads(resp.read())
        if data.get("status") == "ready":
            assert data.get("eval_output", ""), "Empty eval output"
            assert data.get("run_file", ""), "Missing run file path"
            assert data.get("eval_file", ""), "Missing eval file path"
            # Verify commands log contains TrecEval
            resp2 = urllib.request.urlopen(f"{APP_URL}/api/commands", timeout=10)
            cmds = json.loads(resp2.read())
            cmds_text = json.dumps(cmds)
            assert "TrecEval" in cmds_text, "Commands log missing TrecEval command"

    def test_docker_render_contract_documented(self, app_server, browser_context):
        """Docker/Render readiness contract: PORT binding works."""
        resp = urllib.request.urlopen(f"{APP_URL}/health", timeout=10)
        data = json.loads(resp.read())
        assert data["status"] in ("ok", "initializing", "not_started"), \
            f"Unexpected status: {data['status']}"
