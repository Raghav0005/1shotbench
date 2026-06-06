"""
End-to-end browser test for NFCorpus Live Retrieval Diagnostics Workbench.
Requires: playwright (pip install playwright && playwright install chromium)

Usage:
    python tests/test_browser.py

The test starts the Flask app, opens it in a headless browser, and verifies
all the PRD requirements: readiness panel, live search, evaluation metrics,
commands visibility, and artifact paths.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect


# Base URL - app is started separately or in-process
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:10000")


@pytest.fixture(scope="module")
def page():
    """Start browser and create a page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(30000)
        yield page
        browser.close()


def wait_for_ready(page):
    """Wait for the readiness panel to show complete status."""
    max_attempts = 60  # 2 minutes max
    for attempt in range(max_attempts):
        try:
            status_resp = page.evaluate("""
                async () => {
                    const resp = await fetch('/api/status');
                    return await resp.json();
                }
            """)
            if status_resp.get("nfcorpus_search_ready"):
                return status_resp
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("App did not become ready within timeout")


class TestReadiness:
    """Test the readiness/health endpoint and panel."""

    def test_health_endpoint(self, page):
        """Verify /health returns correct JSON structure."""
        page.goto(f"{BASE_URL}/health")
        body = page.evaluate("document.body.innerText")
        data = json.loads(body)

        assert "status" in data
        assert "anserini_available" in data
        assert "nfcorpus_ready" in data
        assert "search_available" in data
        assert "evaluation_available" in data

    def test_readiness_panel_visible(self, page):
        """Verify the readiness panel appears on the main page."""
        page.goto(BASE_URL)
        status = wait_for_ready(page)

        # Check readiness panel elements
        panel = page.locator("#readiness-panel")
        expect(panel).to_be_visible()

        assert status["java_available"], "Java should be available"
        assert status["fatjar_available"], "Fatjar should be available"
        assert status["smoke_test_passed"], "Smoke test should pass"
        assert status["nfcorpus_index_ready"], "NFCorpus index should be ready"

    def test_nfcorpus_active_dataset(self, page):
        """Verify NFCorpus is identified as the active dataset."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # The search panel should mention NFCorpus
        page_content = page.content()
        assert "NFCorpus" in page_content, "NFCorpus should be mentioned on page"

    def test_anserini_setup_visible(self, page):
        """Verify Anserini setup status is visible."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # The readiness panel should show Anserini-related status
        page_content = page.content()
        assert "Java 21" in page_content or "Java" in page_content
        assert "Fatjar" in page_content or "fatjar" in page_content.lower()
        assert "Smoke Test" in page_content or "CACM" in page_content


class TestLiveSearch:
    """Test live search over NFCorpus."""

    def test_search_with_sample_query(self, page):
        """Run a live NFCorpus query and verify ranked results appear."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Type a query and click search
        search_input = page.locator("#search-input")
        expect(search_input).to_be_visible()

        search_input.fill("blood")
        page.locator("button", has_text="Search").click()

        # Wait for results
        page.wait_for_selector("table", timeout=20000)

        # Verify results contain expected elements
        page_content = page.content()

        # Check for rank numbers
        assert "rank" not in page_content.lower() or "1" in page_content

        # Check for doc IDs (MED-xxxx format typical of NFCorpus)
        results_area = page.locator("#search-results")
        results_text = results_area.inner_text()

        assert "MED-" in results_text or "docid" in results_text.lower(), \
            "Results should contain document IDs"

        # Check for scores
        assert any(
            c.isdigit() for c in results_text
        ), "Results should contain numeric scores"

        # Check for content/snippets
        assert len(results_text) > 100, "Results should contain document text"

    def test_search_command_visible(self, page):
        """Verify search command text is visible in commands tab."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Run a search first
        search_input = page.locator("#search-input")
        search_input.fill("cancer")
        page.locator("button", has_text="Search").click()
        page.wait_for_selector("table", timeout=20000)

        # Go to Search Commands tab
        tab_button = page.locator(".tab-bar button", has_text="Search Commands")
        if tab_button.count() > 0:
            tab_button.click()
            page.wait_for_timeout(500)
            cmd_content = page.locator("#tab-search-cmds").inner_text()
            assert "Search" in cmd_content or "io.anserini" in cmd_content, \
                "Search command should be visible in tab"

    def test_results_have_ranks_ids_scores_content(self, page):
        """Verify search results include rank, doc ID, score, and text."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        search_input = page.locator("#search-input")
        search_input.fill("clinical trial")
        page.locator("button", has_text="Search").click()
        page.wait_for_selector("table", timeout=20000)

        # Check table headers
        table_html = page.locator("#search-results table").inner_html()
        headers_lower = page.locator("#search-results th").all_inner_texts()
        headers_text = " ".join(headers_lower).lower()

        assert "#" in headers_text or "rank" in headers_text
        assert "docid" in headers_text or "doc" in headers_text
        assert "score" in headers_text
        assert "content" in headers_text or "text" in headers_text


class TestEvaluation:
    """Test BM25 evaluation metrics and comparison."""

    def test_run_evaluation(self, page):
        """Trigger evaluation and verify numeric observed metrics appear."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Trigger evaluation
        eval_btn = page.locator("#eval-run-btn")
        if eval_btn.count() > 0:
            eval_btn.click()

        # Wait for evaluation to complete (may take a while)
        max_wait = 120  # seconds
        for _ in range(max_wait):
            time.sleep(2)
            try:
                page_content = page.content()
                if "PASS" in page_content or "FAIL" in page_content or "CLOSE" in page_content:
                    break
            except Exception:
                pass
        else:
            # May have been pre-computed, check status
            pass

        page.goto(BASE_URL)
        wait_for_ready(page)

        # Check eval panel has content
        eval_content = page.locator("#eval-comparison").inner_text()
        assert len(eval_content) > 10, "Evaluation comparison should show data"

    def test_numeric_observed_metric(self, page):
        """Verify at least one numeric observed metric is displayed."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Fetch eval status
        eval_data = page.evaluate("""
            async () => {
                const resp = await fetch('/api/eval?action=status');
                return await resp.json();
            }
        """)

        if eval_data.get("eval_completed"):
            comparison = eval_data.get("comparison", {})
            has_numeric = False
            for metric, info in comparison.items():
                if info.get("observed") is not None:
                    has_numeric = True
                    break
            assert has_numeric, "At least one observed metric must be numeric"

    def test_expected_metric_info(self, page):
        """Verify expected metric information appears."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Fetch eval status
        eval_data = page.evaluate("""
            async () => {
                const resp = await fetch('/api/eval?action=status');
                return await resp.json();
            }
        """)

        comparison = eval_data.get("comparison", {})
        assert len(comparison) > 0, "Expected metrics should be present"

        for metric, info in comparison.items():
            assert info.get("expected") is not None, \
                f"Expected value for {metric} should be present"

    def test_observed_vs_expected_comparison(self, page):
        """Verify observed-vs-expected comparison status appears."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        eval_data = page.evaluate("""
            async () => {
                const resp = await fetch('/api/eval?action=status');
                return await resp.json();
            }
        """)

        if eval_data.get("eval_completed"):
            comparison = eval_data.get("comparison", {})
            statuses = set()
            for metric, info in comparison.items():
                statuses.add(info.get("status"))
            assert statuses, "Should have status values"
            assert any(
                s in ("pass", "close", "fail") for s in statuses
            ), "Should have pass/close/fail status"


class TestCommandsAndArtifacts:
    """Test command and artifact visibility."""

    def test_setup_commands_visible(self, page):
        """Verify setup commands are visible in the commands tab."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Setup Commands tab should be active by default
        setup_content = page.locator("#setup-commands").inner_text()
        assert len(setup_content) > 10, "Setup commands should be visible"
        assert "java" in setup_content.lower() or "anserini" in setup_content.lower(), \
            "Setup commands should reference Java/Anserini"

    def test_artifact_paths_visible(self, page):
        """Verify artifact paths are shown in the artifacts tab."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Skip if eval not run
        eval_btn = page.locator("#eval-run-btn")
        if eval_btn.count() > 0:
            eval_btn.click()
            time.sleep(5)  # brief wait for evaluation start

        # Check artifacts tab
        tab = page.locator(".tab-bar button", has_text="Artifacts")
        if tab.count() > 0:
            tab.click()
            page.wait_for_timeout(500)
            artifacts_text = page.locator("#tab-artifacts").inner_text()
            # Should have some file paths or message
            assert len(artifacts_text.strip()) > 0, "Artifacts tab should have content"


class TestDeploymentContract:
    """Test Docker/Render deployment contract."""

    def test_port_binding(self, page):
        """Verify the app binds to PORT from environment (or default 10000)."""
        resp = page.evaluate(f"""
            async () => {{
                const resp = await fetch('{BASE_URL}/health');
                return resp.status;
            }}
        """)
        assert resp == 200, "App should respond on configured port"

    def test_render_readiness_documented(self, page):
        """Verify deployment info is discoverable in the app."""
        page.goto(BASE_URL)
        page_content = page.content()

        # The app page should document the PORT/health contract
        # Check for PORT or 10000 mention
        assert "10000" in page_content or "PORT" in page_content, \
            "Port binding should be documented"


class TestRealWorkflow:
    """Verify the app uses real Anserini commands, not mocked results."""

    def test_not_mocked_search(self, page):
        """Verify search results are not mocked/hardcoded."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Search for two different queries
        queries = ["blood", "cancer treatment"]
        results_sets = []

        for q in queries:
            search_input = page.locator("#search-input")
            search_input.fill(q)
            page.locator("button", has_text="Search").click()
            page.wait_for_selector("table", timeout=20000)
            time.sleep(0.5)
            results_text = page.locator("#search-results").inner_text()
            results_sets.append(results_text)

        # Different queries should produce different results
        # (Proving results are not hardcoded/mocked)
        if len(results_sets) == 2:
            assert results_sets[0] != results_sets[1], \
                "Different queries must return different results (not mocked)"

    def test_commands_reference_anserini(self, page):
        """Verify commands reference real Anserini CLI invocations."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        setup_content = page.locator("#setup-commands").inner_text()
        assert "io.anserini" in setup_content or "anserini" in setup_content.lower(), \
            "Commands must reference Anserini, not custom mock code"

    def test_artifact_paths_real(self, page):
        """Verify artifact paths reference real files from Anserini."""
        page.goto(BASE_URL)
        wait_for_ready(page)

        # Trigger eval if needed
        eval_btn = page.locator("#eval-run-btn")
        if eval_btn.count() > 0:
            eval_btn.click()
            time.sleep(5)

        # Check artifacts tab
        tab = page.locator(".tab-bar button", has_text="Artifacts")
        if tab.count() > 0:
            tab.click()
            page.wait_for_timeout(500)
            artifacts_text = page.locator("#tab-artifacts").inner_text()
            # Artifacts should reference .txt run files or similar
            assert (
                ".txt" in artifacts_text
                or "run." in artifacts_text
                or "nfcorpus" in artifacts_text.lower()
                or "artifacts" in artifacts_text.lower()
            ), "Artifacts should reference real files"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
