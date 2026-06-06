"""
End-to-end browser test for the NFCorpus Retrieval Diagnostics Workbench.

This test verifies the real Anserini-backed workflow is exercised,
not mocked results. It requires the app to be running (via Docker or locally).

Usage:
    # Start the app first, then:
    pip install playwright pytest
    playwright install chromium
    pytest tests/test_browser.py -v

Environment:
    APP_URL: Base URL of the running app (default: http://localhost:10000)
    SETUP_TIMEOUT: Timeout in seconds for app setup (default: 600)
"""

import os
import re
import time
import pytest
from playwright.sync_api import sync_playwright, expect

APP_URL = os.environ.get("APP_URL", "http://localhost:10000")
SETUP_TIMEOUT = int(os.environ.get("SETUP_TIMEOUT", "600"))


@pytest.fixture(scope="module")
def browser():
    """Launch browser for the test module."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def page(browser):
    """Create a page and wait for app to be ready."""
    page = browser.new_page()
    page.goto(APP_URL, timeout=30000)
    yield page
    page.close()


@pytest.fixture(scope="module")
def wait_for_ready(page):
    """Wait for the app to finish setup."""
    start = time.time()
    while time.time() - start < SETUP_TIMEOUT:
        try:
            response = page.evaluate("fetch('/health').then(r => r.json())")
            if response.get("setup_done") and response.get("search_available"):
                return response
        except Exception:
            pass
        time.sleep(5)
    pytest.fail(f"App did not become ready within {SETUP_TIMEOUT}s")


class TestHealthEndpoint:
    """Test the /health endpoint contract."""

    def test_health_returns_json(self, page, wait_for_ready):
        """Health endpoint must return valid JSON."""
        health = wait_for_ready
        assert isinstance(health, dict), "Health response must be a JSON object"

    def test_health_has_required_fields(self, page, wait_for_ready):
        """Health response must include all required fields."""
        health = wait_for_ready
        required = ["status", "anserini_available", "nfcorpus_ready",
                     "search_available", "evaluation_available"]
        for field in required:
            assert field in health, f"Missing required field: {field}"

    def test_health_shows_ready(self, page, wait_for_ready):
        """App should report ready status."""
        health = wait_for_ready
        assert health["status"] in ("ok", "ready", "initializing"), \
            f"Unexpected status: {health['status']}"
        assert health["search_available"] is True, "Search must be available"


class TestReadinessPanel:
    """Test the readiness/status display panel."""

    def test_readiness_panel_visible(self, page, wait_for_ready):
        """The readiness panel should be visible on the page."""
        panel = page.locator("#readiness-panel")
        expect(panel).to_be_visible()

    def test_java_status_visible(self, page, wait_for_ready):
        """Java status should be visible and show ok."""
        item = page.locator("#status-java")
        expect(item).to_be_visible()
        # Should show checkmark for ok status
        icon = item.locator(".status-icon")
        expect(icon).to_have_text("✅", timeout=5000)

    def test_fatjar_status_visible(self, page, wait_for_ready):
        """Fatjar status should be visible and show ok."""
        item = page.locator("#status-fatjar")
        expect(item).to_be_visible()
        icon = item.locator(".status-icon")
        expect(icon).to_have_text("✅", timeout=5000)

    def test_nfcorpus_identified(self, page, wait_for_ready):
        """NFCorpus should be identified as the active dataset."""
        item = page.locator("#status-nfcorpus")
        expect(item).to_be_visible()
        value = item.locator(".status-value")
        # Should contain nfcorpus reference
        expect(value).to_contain_text("nfcorpus", timeout=5000)


class TestLiveSearch:
    """Test live NFCorpus search functionality."""

    def test_search_box_visible(self, page, wait_for_ready):
        """Search input and button should be visible."""
        input_el = page.locator("#search-input")
        btn = page.locator("#search-btn")
        expect(input_el).to_be_visible()
        expect(btn).to_be_visible()

    def test_search_box_enabled(self, page, wait_for_ready):
        """Search box should be enabled after setup."""
        input_el = page.locator("#search-input")
        expect(input_el).not_to_be_disabled(timeout=10000)

    def test_sample_queries_visible(self, page, wait_for_ready):
        """Sample query buttons should be visible."""
        samples = page.locator(".sample-btn")
        assert samples.count() >= 2, "Should have at least 2 sample queries"

    def test_run_search_query(self, page, wait_for_ready):
        """Run a live search and verify results appear."""
        input_el = page.locator("#search-input")
        btn = page.locator("#search-btn")

        # Type a query and search
        input_el.fill("What are the effects of aspirin on heart disease?")
        btn.click()

        # Wait for results
        results = page.locator("[data-testid='search-result']")
        expect(results.first).to_be_visible(timeout=60000)

        # Verify result structure
        count = results.count()
        assert count > 0, "Should have at least one search result"

        # Check first result has required fields
        first = results.first
        expect(first.locator(".result-rank")).to_be_visible()
        expect(first.locator(".result-docid")).to_be_visible()
        expect(first.locator(".result-score")).to_be_visible()

    def test_search_results_have_document_ids(self, page, wait_for_ready):
        """Search results must show document IDs (not mocked placeholders)."""
        results = page.locator("[data-testid='search-result']")
        if results.count() == 0:
            # Run a search first
            page.locator("#search-input").fill("vitamin D deficiency symptoms")
            page.locator("#search-btn").click()
            expect(results.first).to_be_visible(timeout=60000)

        first_docid = results.first.locator(".result-docid").text_content()
        assert first_docid and first_docid != "—", \
            f"Document ID should be a real ID, got: {first_docid}"

    def test_search_results_have_scores(self, page, wait_for_ready):
        """Search results must show numeric scores."""
        results = page.locator("[data-testid='search-result']")
        if results.count() == 0:
            page.locator("#search-input").fill("diabetes management guidelines")
            page.locator("#search-btn").click()
            expect(results.first).to_be_visible(timeout=60000)

        score_text = results.first.locator(".result-score").text_content()
        assert score_text, "Score should not be empty"
        # Should contain a numeric value
        assert re.search(r'\d+\.\d+', score_text), \
            f"Score should contain a number, got: {score_text}"

    def test_sample_query_works(self, page, wait_for_ready):
        """Clicking a sample query should trigger a search."""
        # Click the first sample button
        sample = page.locator(".sample-btn").first
        sample.click()

        # Results should appear
        results = page.locator("[data-testid='search-result']")
        expect(results.first).to_be_visible(timeout=60000)


class TestEvaluation:
    """Test BM25 evaluation panel."""

    def test_eval_panel_visible(self, page, wait_for_ready):
        """Evaluation panel should be visible."""
        panel = page.locator("#eval-panel")
        expect(panel).to_be_visible()

    def test_eval_metrics_table_visible(self, page, wait_for_ready):
        """Evaluation metrics table should be displayed."""
        table = page.locator("[data-testid='eval-metrics-table']")
        expect(table).to_be_visible(timeout=30000)

    def test_eval_has_numeric_metrics(self, page, wait_for_ready):
        """At least one observed metric should be displayed."""
        rows = page.locator("[data-testid='eval-row']")
        expect(rows.first).to_be_visible(timeout=30000)
        count = rows.count()
        assert count > 0, "Should have at least one evaluation metric row"

    def test_eval_shows_observed_values(self, page, wait_for_ready):
        """Observed metric values should be numeric (not placeholders)."""
        rows = page.locator("[data-testid='eval-row']")
        expect(rows.first).to_be_visible(timeout=30000)

        # Get the observed value from first row
        first_row = rows.first
        cells = first_row.locator("td")
        observed_text = cells.nth(1).text_content()
        assert observed_text and observed_text != "—", \
            f"Observed value should be numeric, got: {observed_text}"
        # Should be a float
        assert re.match(r'\d+\.\d+', observed_text.strip()), \
            f"Observed should be a float, got: {observed_text}"

    def test_eval_shows_expected_metrics(self, page, wait_for_ready):
        """Expected metric info should appear when available."""
        rows = page.locator("[data-testid='eval-row']")
        expect(rows.first).to_be_visible(timeout=30000)

        # Check if expected values are shown (may be N/A if not discovered)
        first_row = rows.first
        cells = first_row.locator("td")
        expected_text = cells.nth(2).text_content()
        # Just verify the cell exists (may be "—" if not available)
        assert expected_text is not None, "Expected column should exist"

    def test_eval_shows_status_or_delta(self, page, wait_for_ready):
        """Status or delta comparison should be visible."""
        rows = page.locator("[data-testid='eval-row']")
        expect(rows.first).to_be_visible(timeout=30000)

        first_row = rows.first
        cells = first_row.locator("td")
        status_text = cells.nth(4).text_content()
        # Should contain a status indicator
        valid_statuses = ["PASS", "CLOSE", "FAIL", "N/A"]
        has_status = any(s in (status_text or "") for s in valid_statuses)
        assert has_status or status_text.strip() == "—", \
            f"Should have a status, got: {status_text}"

    def test_eval_rerun_button(self, page, wait_for_ready):
        """Rerun button should be available."""
        btn = page.locator("#eval-rerun-btn")
        expect(btn).to_be_visible()


class TestCommandsAndArtifacts:
    """Test command log and artifact display."""

    def test_commands_section_exists(self, page, wait_for_ready):
        """Commands section should be present."""
        section = page.locator("#commands-panel")
        expect(section).to_be_visible()

    def test_commands_drawer_toggles(self, page, wait_for_ready):
        """Commands drawer should open and close."""
        header = page.locator("#commands-panel h2")
        header.click()

        content = page.locator("#commands-content")
        expect(content).to_be_visible(timeout=5000)

        # Should have at least one command entry
        entries = page.locator("[data-testid='command-entry']")
        assert entries.count() > 0, "Should have at least one command logged"

    def test_command_entries_have_text(self, page, wait_for_ready):
        """Command entries should contain real command text."""
        # Open drawer first
        header = page.locator("#commands-panel h2")
        if page.locator("#commands-content").is_hidden():
            header.click()

        entries = page.locator("[data-testid='command-entry']")
        expect(entries.first).to_be_visible(timeout=5000)

        cmd_text = entries.first.locator(".cmd-text").text_content()
        assert cmd_text and len(cmd_text) > 10, \
            f"Command text should be meaningful, got: {cmd_text}"
        # Should mention java or anserini
        assert "java" in cmd_text.lower() or "anserini" in cmd_text.lower(), \
            f"Command should reference Anserini, got: {cmd_text}"

    def test_artifacts_visible(self, page, wait_for_ready):
        """Artifact paths should be visible in commands section."""
        header = page.locator("#commands-panel h2")
        if page.locator("#commands-content").is_hidden():
            header.click()

        artifacts = page.locator(".artifacts-section")
        # Artifacts should be present after evaluation runs
        if artifacts.is_visible():
            items = artifacts.locator(".artifact-item")
            assert items.count() > 0, "Should have artifact entries"


class TestVerification:
    """Test the verification badge and anti-mock guarantees."""

    def test_verification_badge_visible(self, page, wait_for_ready):
        """Verification badge should be visible."""
        badge = page.locator("#verification-badge")
        expect(badge).to_be_visible()

    def test_verification_shows_verified(self, page, wait_for_ready):
        """Badge should show verified status when everything works."""
        badge = page.locator("#verification-badge")
        # Wait for the badge to have the 'verified' class
        expect(badge).to_have_class(re.compile(r'verified'), timeout=30000)

    def test_no_mocked_results(self, page, wait_for_ready):
        """Search results should come from real Anserini, not mocks."""
        # Run a unique search that wouldn't be hardcoded
        unique_query = "renal tubular acidosis treatment outcomes 2023"
        page.locator("#search-input").fill(unique_query)
        page.locator("#search-btn").click()

        results = page.locator("[data-testid='search-result']")
        expect(results.first).to_be_visible(timeout=60000)

        # Verify we got real results
        first_docid = results.first.locator(".result-docid").text_content()
        assert first_docid and first_docid != "mock_doc_1" and first_docid != "—", \
            "Results must not be mocked — expected real document IDs"

        # Verify scores are real numbers (not hardcoded 1.0 or 0.0)
        score_text = results.first.locator(".result-score").text_content()
        score_match = re.search(r'(\d+\.\d+)', score_text)
        assert score_match, f"Should have a numeric score, got: {score_text}"
        score = float(score_match.group(1))
        assert score > 0, f"Score should be positive, got: {score}"

    def test_port_binding_documented(self, page, wait_for_ready):
        """PORT binding contract should be documented."""
        # This is verified by the health endpoint responding on the configured port
        health = page.evaluate("fetch('/health').then(r => r.json())")
        assert health is not None, "Health endpoint must respond (PORT binding works)"
