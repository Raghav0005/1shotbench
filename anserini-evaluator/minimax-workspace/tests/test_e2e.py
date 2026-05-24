#!/usr/bin/env python3
"""
Playwright end-to-end test for Anserini Prebuilt Index Evaluator.
Verifies the complete workflow: browsing catalog, selecting CACM, running evaluation.
"""

import os
import sys
import subprocess
import time
import signal
from pathlib import Path

import pytest

# Playwright
try:
    from playwright.sync_api import sync_playwright, expect
except ImportError:
    pytest.skip("Playwright not installed", allow_module_level=True)

# Server paths
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
SERVER_SCRIPT = WORKSPACE_DIR / 'server.py'
ANSERINI_JAR = WORKSPACE_DIR / 'anserini-2.1.1-fatjar.jar'
SERVER_URL = 'http://127.0.0.1:5555'
SERVER_STARTUP_TIMEOUT = 30
EVALUATION_TIMEOUT = 120  # seconds for retrieval + eval


@pytest.fixture(scope='module')
def server():
    """Start the Flask server for testing."""
    # Check prerequisites
    if not SERVER_SCRIPT.exists():
        pytest.fail(f"Server script not found: {SERVER_SCRIPT}")
    if not ANSERINI_JAR.exists():
        pytest.fail(f"Anserini jar not found: {ANSERINI_JAR}")
    
    # Check Java
    result = subprocess.run(['java', '-version'], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail("Java not available")
    
    # Set environment
    env = os.environ.copy()
    env['ANSERINI_JAR'] = str(ANSERINI_JAR)
    env['PORT'] = '5555'
    
    # Kill any existing server on port 5555
    subprocess.run(['lsof', '-ti:5555'], capture_output=True)
    subprocess.run(['lsof', '-ti:5555'], capture_output=True).stdout and \
        subprocess.run(['xargs', 'kill', '-9'], input=subprocess.run(['lsof', '-ti:5555'], capture_output=True).stdout)
    time.sleep(1)
    
    # Start server
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT)],
        env=env,
        cwd=str(WORKSPACE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Wait for server to be ready - poll for port availability
    start_time = time.time()
    server_ready = False
    
    while time.time() - start_time < SERVER_STARTUP_TIMEOUT:
        # Try to connect to see if server is up
        try:
            result = subprocess.run(
                ['curl', '-s', '-m', '1', f'{SERVER_URL}/api/health'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.stdout and 'ok' in result.stdout:
                server_ready = True
                break
        except:
            pass
        
        # Check if process died
        if proc.poll() is not None:
            # Read any output before dying
            output = proc.stdout.read() if proc.stdout else ''
            pytest.fail(f"Server process died during startup. Output: {output}")
        
        time.sleep(0.5)
    
    if not server_ready:
        # Dump server output for debugging
        output = ''
        if proc.poll() is None:
            proc.terminate()
        try:
            output = proc.stdout.read() if proc.stdout else ''
        except:
            pass
        pytest.fail(f"Server failed to start within {SERVER_STARTUP_TIMEOUT}s. Output: {output}")
    
    yield proc
    
    # Shutdown
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope='module')
def browser(server):
    """Launch browser for testing."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def test_health(browser):
    """Test that the server is healthy."""
    page = browser.new_page()
    response = page.request.get(f"{SERVER_URL}/api/health")
    assert response.ok
    data = response.json()
    assert data['status'] == 'ok'
    assert data['jar_exists'] is True


def test_index_catalog_shows_more_than_hardcoded_cacm(browser):
    """Test that the index catalog exposes more than just CACM when registry is available."""
    page = browser.new_page()
    response = page.request.get(f"{SERVER_URL}/api/indexes")
    assert response.ok
    indexes = response.json()
    
    # Should have multiple indexes from the registry
    assert len(indexes) > 1, f"Expected more than 1 index from registry, got {len(indexes)}"
    
    # Check that CACM is in the list
    index_names = [idx['name'] for idx in indexes]
    assert 'cacm' in index_names, "CACM should be in the catalog"
    
    # Check that there's at least one non-evaluable index (catalog-only)
    catalog_only = [idx for idx in indexes if not idx.get('evaluable', False)]
    assert len(catalog_only) > 0, "Should have at least one catalog-only index"
    
    print(f"Found {len(indexes)} indexes, {len(catalog_only)} catalog-only")


def test_cacm_is_evaluable(browser):
    """Test that CACM shows topic/qrels pairing and is evaluable."""
    page = browser.new_page()
    response = page.request.get(f"{SERVER_URL}/api/indexes")
    assert response.ok
    indexes = response.json()
    
    # Find CACM
    cacm = next((idx for idx in indexes if idx['name'] == 'cacm'), None)
    assert cacm is not None, "CACM not found in catalog"
    
    # Check CACM is evaluable
    assert cacm.get('evaluable') is True, "CACM should be marked as evaluable"
    
    # Check topic/qrels pairing
    assert 'topics' in cacm, "CACM should have topics"
    assert 'qrels' in cacm, "CACM should have qrels"
    assert cacm['topics'] == 'cacm', f"CACM topics should be 'cacm', got {cacm['topics']}"
    assert cacm['qrels'] == 'cacm', f"CACM qrels should be 'cacm', got {cacm['qrels']}"
    
    # Check available metrics
    assert 'available_metrics' in cacm, "CACM should have available_metrics"
    metrics = cacm['available_metrics']
    assert len(metrics) > 0, "CACM should have at least one metric"
    
    # Check for nDCG@10 or Recall@1000
    metric_ids = [m['id'] for m in metrics]
    has_ndcg10 = 'ndcg_cut.10' in metric_ids
    has_recall1000 = 'recall.1000' in metric_ids
    
    print(f"CACM metrics: {metric_ids}")
    assert has_ndcg10 or has_recall1000, "CACM should support nDCG@10 or Recall@1000"


def test_run_evaluation_workflow(browser):
    """Test the complete evaluation workflow in browser."""
    page = browser.new_page()
    
    # Navigate to app
    page.goto(SERVER_URL)
    
    # Wait for status to show ready
    page.wait_for_selector('.status-bar.ok', timeout=30000)
    
    # Check status text
    status_text = page.locator('#status-text').text_content()
    print(f"Status: {status_text}")
    assert 'Ready' in status_text or 'ok' in status_text.lower()
    
    # Wait for index list to load
    page.wait_for_selector('.index-item', timeout=30000)
    
    # Count indexes in catalog
    index_count = page.locator('.index-item').count()
    print(f"Index count: {index_count}")
    assert index_count > 1, f"Expected more than 1 index, got {index_count}"
    
    # Find and click CACM
    page.locator('.index-item[data-index="cacm"]').click()
    
    # Wait for evaluation panel to be visible
    page.wait_for_selector('#eval-panel:not(.hidden)', timeout=10000)
    
    # Verify config values
    selected_index = page.locator('#selected-index').text_content()
    selected_topics = page.locator('#selected-topics').text_content()
    selected_qrels = page.locator('#selected-qrels').text_content()
    
    assert selected_index.strip() == 'cacm'
    assert selected_topics.strip() == 'cacm'
    assert selected_qrels.strip() == 'cacm'
    
    # Select a supported metric (prefer nDCG@10 or Recall@1000)
    metric_select = page.locator('#metric-select')
    options = metric_select.locator('option').all_text_contents()
    print(f"Available metrics: {options}")
    
    # Try to select nDCG@10 or fallback to first available after default
    if 'nDCG@10' in options:
        metric_select.select_option('ndcg_cut.10')
    elif 'Recall@1000' in options:
        metric_select.select_option('recall.1000')
    else:
        # Select any available metric
        available_options = [opt for opt in options if opt != 'Select metric...']
        if available_options:
            # Get the value of the first real option
            first_option_value = metric_select.locator('option').nth(1).get_attribute('value')
            metric_select.select_option(first_option_value)
    
    # Wait for Run Evaluation button to be enabled
    run_btn = page.locator('#run-btn')
    expect(run_btn).to_be_enabled()
    
    # Click Run Evaluation
    run_btn.click()
    
    # Wait for loading overlay to show (not hidden)
    page.wait_for_selector('#loading-overlay:not(.hidden)', timeout=10000)
    
    # Wait for evaluation to complete - check for results section or error
    # Poll until we see results or timeout
    start_time = time.time()
    while time.time() - start_time < 120:
        if page.locator('#results-section:not(.hidden)').count() > 0:
            break
        if page.locator('.error-message').count() > 0:
            break
        time.sleep(1)
    
    # Verify results appeared
    page.wait_for_selector('#results-section:not(.hidden)', timeout=10000)
    
    # Verify score appears
    score_element = page.locator('.result-score')
    expect(score_element).to_be_visible()
    
    score_text = score_element.text_content()
    print(f"Score: {score_text}")
    
    # Score should be a number (not "N/A" or empty)
    assert score_text.strip() != 'N/A'
    assert score_text.strip() != ''
    
    # Try to parse as float
    try:
        score_float = float(score_text.strip())
        assert score_float >= 0 and score_float <= 1, f"Score {score_float} out of expected range [0,1]"
    except ValueError:
        pytest.fail(f"Could not parse score as number: {score_text}")
    
    # Verify run metadata appears
    meta_items = page.locator('.meta-item')
    assert meta_items.count() >= 4, "Should have at least 4 metadata items"
    
    # Check that run file path is shown
    run_file_meta = page.locator('.meta-item').filter(has_text='Run File')
    expect(run_file_meta).to_be_visible()
    
    # Verify run files section updated
    run_file_count = page.locator('.run-file-item').count()
    assert run_file_count >= 1, f"At least one run file should be listed, got {run_file_count}"


def test_catalog_only_indexes_visible(browser):
    """Test that catalog-only indexes are visible and distinguishable."""
    page = browser.new_page()
    response = page.request.get(f"{SERVER_URL}/api/indexes")
    assert response.ok
    indexes = response.json()
    
    # Find a catalog-only index (non-evaluable)
    catalog_only = [idx for idx in indexes if not idx.get('evaluable', False)]
    assert len(catalog_only) > 0, "Should have at least one catalog-only index"
    
    # Navigate to app
    page.goto(SERVER_URL)
    
    # Wait for index list
    page.wait_for_selector('.index-item', timeout=30000)
    
    # Check that catalog-only items exist in the UI
    catalog_only_items = page.locator('.index-item.catalog-only')
    count = catalog_only_items.count()
    assert count > 0, "Should have catalog-only items visible in UI"
    
    print(f"Found {count} catalog-only indexes in UI")
    
    # Verify evaluable items are also shown
    evaluable_items = page.locator('.index-item.evaluable')
    eval_count = evaluable_items.count()
    assert eval_count > 0, "Should have at least one evaluable index"
    
    print(f"Found {eval_count} evaluable indexes in UI")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])