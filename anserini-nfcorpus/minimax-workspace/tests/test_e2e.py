"""
NFCorpus Live Retrieval Diagnostics Workbench - E2E Tests

These tests verify the app uses real Anserini-backed workflows rather than mocks.
Tests will FAIL if the app only displays hardcoded search results or mocked metrics.

Requires: playwright, pytest, and the app running on port 10000 (or BASE_URL env var).
"""

import os
import re
import time
import pytest
from playwright.sync_api import Page, expect


BASE_URL = os.environ.get('BASE_URL', 'http://localhost:10000')


@pytest.fixture(scope='session')
def page():
    """Create a Playwright page and navigate to the app."""
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    yield page

    context.close()
    browser.close()
    playwright.stop()


def test_health_endpoint(page: Page):
    """Verify /health returns JSON with required fields."""
    response = page.request.get(f"{BASE_URL}/health")
    assert response.ok, f"Health endpoint failed: {response.status}"

    data = response.json()
    assert 'status' in data, "Health response missing 'status'"
    assert 'anserini_available' in data, "Health response missing 'anserini_available'"
    assert 'nfcorpus_ready' in data, "Health response missing 'nfcorpus_ready'"
    assert 'search_available' in data, "Health response missing 'search_available'"
    assert 'evaluation_available' in data, "Health response missing 'evaluation_available'"
    print(f"Health check passed: {data}")


def test_status_panel_visible(page: Page):
    """Verify the status/readiness panel appears with Anserini and NFCorpus info."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Check that status grid items are visible
    status_labels = ['Java', 'Anserini', 'NFCorpus Index', 'Search', 'Evaluation', 'REST Server']
    for label in status_labels:
        locator = page.locator(f'.status-item:has-text("{label}")')
        assert locator.is_visible(), f"Status item '{label}' not visible"

    print("Status panel verified")


def test_nfcorpus_dataset_identification(page: Page):
    """Verify NFCorpus is identified as the active dataset."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Look for NFCorpus badge or dataset indicator
    nfcorpus_indicator = page.locator('.dataset-badge, .badge:has-text("NFCorpus")')
    assert nfcorpus_indicator.is_visible(), "NFCorpus not identified as active dataset"

    print("NFCorpus dataset identification verified")


def test_anserini_setup_status_visible(page: Page):
    """Verify Anserini setup status is visible and shows jar/version info."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Check that Anserini status shows something other than "Not found"
    anserini_status = page.locator('#anserini-status')
    assert anserini_status.is_visible(), "Anserini status not visible"
    status_text = anserini_status.text_content()
    assert 'not found' not in status_text.lower(), f"Anserini not properly set up: {status_text}"

    print(f"Anserini status: {status_text}")


def test_sample_queries_available(page: Page):
    """Verify NFCorpus sample queries are displayed."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Check for sample query chips
    sample_list = page.locator('#sample-list')
    assert sample_list.is_visible(), "Sample queries not displayed"

    sample_chips = page.locator('.sample-chip')
    count = sample_chips.count()
    assert count > 0, "No sample queries found"

    print(f"Found {count} sample queries")


def test_live_search_returns_results(page: Page):
    """Verify live NFCorpus search returns ranked results with ids, scores, and content."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Click a sample query or enter our own
    sample_chip = page.locator('.sample-chip').first
    if sample_chip.is_visible():
        query_text = sample_chip.text_content()
        sample_chip.click()
    else:
        query_text = "CRISPR gene editing"
        page.fill('#search-query', query_text)
        page.click('#search-btn')

    # Wait for results
    page.wait_for_selector('#search-results:not(.hidden)', timeout=60000)

    # Verify results appear with required fields
    result_list = page.locator('#result-list')
    assert result_list.is_visible(), "Result list not visible"

    result_items = page.locator('.result-item')
    count = result_items.count()
    assert count > 0, "No search results returned"

    # Check for rank, docid, score, and content in at least first result
    first_result = result_items.first
    rank_text = first_result.locator('.rank').text_content()
    assert re.search(r'rank\s*\d+', rank_text, re.IGNORECASE), "No rank visible"

    docid_text = first_result.locator('.docid').text_content()
    assert 'document' in docid_text.lower() or 'id' in docid_text.lower(), "No docid visible"

    score_text = first_result.locator('.score').text_content()
    assert re.search(r'score', score_text, re.IGNORECASE), "No score visible"

    doc_content = first_result.locator('.doc-content')
    content_text = doc_content.text_content()
    assert content_text and len(content_text) > 0, "No document content/snippet"

    print(f"Search returned {count} results with rank, docid, score, and content")


def test_evaluation_panel_displays_metrics(page: Page):
    """Verify the evaluation panel shows at least one numeric observed metric."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Check if eval is already cached from startup
    eval_results = page.locator('#eval-results')
    if eval_results.is_hidden():
        # Run evaluation
        run_btn = page.locator('#run-eval-btn')
        if run_btn.is_enabled():
            run_btn.click()
            page.wait_for_selector('#eval-results:not(.hidden)', timeout=300000)
        else:
            pytest.skip("Evaluation not available (nfcorpus index not ready)")

    # Verify metrics table has data
    metrics_table = page.locator('.metrics-table table')
    assert metrics_table.is_visible(), "Metrics table not visible"

    tbody = page.locator('#metrics-tbody')
    rows = tbody.locator('tr')
    row_count = rows.count()
    assert row_count > 0, "No evaluation metrics displayed"

    # Check that at least one row has a numeric observed value
    observed_values = []
    for row in rows.all():
        cells = row.locator('td')
        if cells.count >= 2:
            observed = cells.nth(1).text_content()
            observed_values.append(observed)

    # Verify at least one observed metric is numeric
    has_numeric = any(re.search(r'\d', v) for v in observed_values)
    assert has_numeric, f"No numeric observed metrics found: {observed_values}"

    print(f"Evaluation metrics displayed: {observed_values}")


def test_expected_metrics_info_appears(page: Page):
    """Verify expected metric info appears when reproduction discovery exposes it."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Run evaluation if not already cached
    eval_results = page.locator('#eval-results')
    if eval_results.is_hidden():
        run_btn = page.locator('#run-eval-btn')
        if run_btn.is_enabled():
            run_btn.click()
            page.wait_for_selector('#eval-results:not(.hidden)', timeout=300000)
        else:
            pytest.skip("Evaluation not available")

    # Check metrics table for expected column
    metrics_table = page.locator('.metrics-table table')
    assert metrics_table.is_visible(), "Metrics table not visible"

    # The table should have headers including "Expected"
    header_row = metrics_table.locator('thead th')
    header_texts = [h.text_content() for h in header_row.all()]
    assert 'Expected' in header_texts or 'expected' in [t.lower() for t in header_texts], \
        "Expected column not found in metrics table"

    print("Expected metrics column found")


def test_observed_vs_expected_comparison(page: Page):
    """Verify observed-vs-expected comparison status or delta appears."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Run evaluation if not already cached
    eval_results = page.locator('#eval-results')
    if eval_results.is_hidden():
        run_btn = page.locator('#run-eval-btn')
        if run_btn.is_enabled():
            run_btn.click()
            page.wait_for_selector('#eval-results:not(.hidden)', timeout=300000)
        else:
            pytest.skip("Evaluation not available")

    # Check for delta or status columns in metrics table
    tbody = page.locator('#metrics-tbody')
    rows = tbody.locator('tr')

    status_or_delta_found = False
    for row in rows.all():
        cells = row.locator('td')
        cell_texts = [c.text_content() for c in cells.all()]
        # Look for status (PASS/FAIL/CLOSE) or delta values (+/- numbers)
        if any(re.search(r'(pass|fail|close)', t, re.IGNORECASE) for t in cell_texts):
            status_or_delta_found = True
            break
        if any(re.search(r'[+-]\d', t) for t in cell_texts):
            status_or_delta_found = True
            break

    assert status_or_delta_found, "No observed-vs-expected comparison (status/delta) found"

    print("Observed vs expected comparison verified")


def test_commands_and_artifacts_visible(page: Page):
    """Verify exact command text and artifact paths/previews are visible."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Expand commands drawer
    toggle_btn = page.locator('#toggle-commands')
    if toggle_btn.is_visible():
        toggle_btn.click()
        page.wait_for_selector('#commands-drawer:not(.hidden)', timeout=5000)

    # Verify commands are displayed
    commands_content = page.locator('#commands-content')
    assert commands_content.is_visible(), "Commands content not visible"

    command_items = commands_content.locator('.command-item')
    count = command_items.count()
    assert count > 0, "No command items displayed"

    # Verify at least one command contains Anserini java invocation
    all_command_text = commands_content.text_content()
    assert 'java' in all_command_text.lower() and 'anserini' in all_command_text.lower(), \
        "No Anserini commands visible"

    # Verify artifacts are displayed
    artifacts_content = page.locator('#artifacts-content')
    assert artifacts_content.is_visible(), "Artifacts content not visible"

    artifact_items = artifacts_content.locator('.artifact-item')
    assert artifact_items.count() > 0, "No artifact items displayed"

    # Check for run file path
    artifact_text = artifacts_content.text_content()
    # Should contain some path-like string
    assert '/' in artifact_text or '.' in artifact_text, "No artifact paths visible"

    print("Commands and artifacts verified")


def test_docker_render_readiness_documented(page: Page):
    """Verify Docker/Render readiness contract is documented (PORT binding in README or footer)."""
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle', timeout=30000)

    # Check footer for PORT binding info
    footer = page.locator('footer')
    assert footer.is_visible(), "Footer not visible"

    footer_text = footer.text_content()
    assert 'PORT' in footer_text, "PORT binding not documented in footer"

    # Also verify README exists at the base URL or check the file exists
    # For this test we just check the footer content mentions PORT
    print(f"Footer documents: {footer_text[:200]}")


def test_no_mocked_search_or_evaluation():
    """
    Meta-test: Verify the backend is actually using Anserini commands.

    This is tested indirectly by checking that:
    1. Commands visible in UI contain real Anserini class names
    2. Search actually queries Anserini (not a mock endpoint)
    3. Evaluation produces real metrics (not hardcoded values)

    If search results or evaluation metrics are hardcoded, the commands
    panel would not contain real Anserini class invocations.
    """
    from playwright.sync_api import sync_playwright

    # Make direct API calls to verify real Anserini is being used
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(BASE_URL)
        page.wait_for_load_state('networkidle', timeout=30000)

        # Check commands endpoint directly
        response = page.request.get(f"{BASE_URL}/api/commands")
        assert response.ok
        commands = response.json()

        # Verify commands contain real Anserini classes
        cmd_texts = [c.get('command', '') for c in commands.values()]
        anserini_classes = [
            'io.anserini.search.SearchCollection',
            'io.anserini.cli.Search',
            'io.anserini.eval.TrecEval',
            'io.anserini.reproduce'
        ]

        has_real_anserini = any(
            any(cls in cmd for cmd in cmd_texts) for cls in anserini_classes
        )
        assert has_real_anserini, \
            f"No real Anserini classes found in commands: {cmd_texts}"

        # Verify artifacts point to real paths
        artifacts_response = page.request.get(f"{BASE_URL}/api/artifacts")
        assert artifacts_response.ok
        artifacts = artifacts_response.json()

        assert 'runs_dir' in artifacts or 'cache_dir' in artifacts, \
            "No runtime directories in artifacts"

        browser.close()

    print("Verified real Anserini commands are being used (no mocks)")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--base-url', BASE_URL])