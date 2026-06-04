"""
End-to-end browser test for NFCorpus Live Retrieval Diagnostics Workbench.

Uses Playwright to verify:
- Health/readiness panel appears
- NFCorpus is the active dataset
- Anserini setup status is visible
- Live search returns ranked results with doc ids, scores, text
- Evaluation panel shows observed metrics
- Expected metric information appears
- Observed-vs-expected comparison status/delta appears
- Exact command text and artifact paths are visible
- The app uses real Anserini commands (not mocked)

Usage:
    pip install playwright
    playwright install chromium
    python test_browser.py [--url http://localhost:10000] [--timeout 300]
"""

import json
import sys
import time
import argparse
import urllib.request
import urllib.error

try:
    from playwright.sync_api import sync_playwright, expect
except ImportError:
    print("Playwright not installed. Install with: pip install playwright && playwright install chromium")
    sys.exit(1)


def wait_for_health(url, timeout=300):
    """Poll /health until the app reports ready or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{url}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                print(f"  Health: status={data.get('status')} anserini={data.get('anserini_available')} "
                      f"nfcorpus={data.get('nfcorpus_ready')} search={data.get('search_available')} "
                      f"eval={data.get('evaluation_available')}")
                if data.get("nfcorpus_ready") and data.get("anserini_available"):
                    return data
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError, OSError):
            pass
        time.sleep(3)
    raise RuntimeError(f"App did not become healthy within {timeout}s")


def run_tests(url, timeout=300):
    print(f"Testing app at {url}")

    # 1. Wait for health
    print("\n[1/8] Waiting for app to become healthy...")
    health = wait_for_health(url, timeout)
    assert health["anserini_available"], "Anserini should be available"
    assert health["nfcorpus_ready"], "NFCorpus index should be ready"
    print("  ✅ App is healthy and ready")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 2. Load page and verify readiness panel
        print("\n[2/8] Loading page and checking readiness panel...")
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_selector("#readiness-panel", timeout=10000)
        readiness = page.query_selector("#readiness-panel")
        assert readiness is not None, "Readiness panel should be present"
        print("  ✅ Readiness panel visible")

        # 3. Verify NFCorpus is identified as the active dataset
        print("\n[3/8] Checking NFCorpus dataset identification...")
        body_text = page.inner_text("body")
        assert "NFCorpus" in body_text, "Page should mention NFCorpus"
        assert "beir-v1.0.0-nfcorpus" in body_text, "Page should show NFCorpus index name"
        print("  ✅ NFCorpus identified as active dataset")

        # 4. Verify Anserini setup status visible
        print("\n[4/8] Checking Anserini setup status...")
        # Poll status API to check
        status_resp = urllib.request.urlopen(f"{url}/api/status", timeout=10)
        status = json.loads(status_resp.read())
        assert status["setup_complete"], f"Setup should be complete, got: {status}"
        assert status["fatjar_ready"], "Fatjar should be ready"
        # Check page shows setup complete
        setup_label = page.inner_text("#lbl-setup")
        assert "Complete" in setup_label or "Ready" in setup_label, f"Setup label should show complete, got: {setup_label}"
        print("  ✅ Anserini setup status visible and complete")

        # 5. Run a live search
        print("\n[5/8] Running live search...")
        # Click a sample query tag or type one
        search_input = page.query_selector("#search-input")
        assert search_input is not None, "Search input should be present"
        search_input.fill("vitamin D")
        search_btn = page.query_selector("#search-btn")
        assert search_btn is not None, "Search button should be present"
        search_btn.click()

        # Wait for results
        page.wait_for_selector(".result-table tbody tr", timeout=60000)
        rows = page.query_selector_all(".result-table tbody tr")
        assert len(rows) > 0, "Search should return results"
        print(f"  ✅ Got {len(rows)} search results")

        # Verify result structure: rank, docid, score, text
        first_row = rows[0]
        cells = first_row.query_selector_all("td")
        assert len(cells) >= 4, f"Result row should have at least 4 cells, got {len(cells)}"
        rank_text = cells[0].inner_text()
        docid_text = cells[1].inner_text()
        score_text = cells[2].inner_text()
        snippet_text = cells[3].inner_text()

        # Rank should be "1"
        assert rank_text.strip() == "1", f"First result rank should be 1, got: {rank_text}"
        # DocID should be non-empty
        assert len(docid_text.strip()) > 0, "DocID should be non-empty"
        # Score should be a number
        float(score_text.strip())
        # Snippet should have content
        assert len(snippet_text.strip()) > 0, "Result should have text content"
        print(f"  ✅ Result structure verified: rank={rank_text}, docid={docid_text}, score={score_text}")

        # Verify search command is shown
        cmd_box = page.query_selector("#search-command")
        assert cmd_box is not None, "Search command box should be present"
        cmd_text = cmd_box.inner_text()
        assert "io.anserini.cli.Search" in cmd_text, f"Command should show Search CLI, got: {cmd_text}"
        assert "beir-v1.0.0-nfcorpus.flat" in cmd_text, "Command should reference NFCorpus index"
        print("  ✅ Search command shown correctly")

        # 6. Verify evaluation panel shows observed metric
        print("\n[6/8] Checking evaluation panel...")
        # Wait for eval content to appear
        page.wait_for_selector("#eval-content", timeout=30000)
        eval_content = page.query_selector("#eval-content")
        assert eval_content is not None, "Evaluation content should be present"

        # Check metric table has rows
        metric_rows = page.query_selector_all("#metric-table tbody tr")
        assert len(metric_rows) > 0, "Metric table should have at least one row"
        print(f"  ✅ Evaluation panel shows {len(metric_rows)} metric(s)")

        # 7. Verify expected metric information appears
        print("\n[7/8] Checking expected metrics and comparison...")
        first_metric = metric_rows[0]
        metric_cells = first_metric.query_selector_all("td")
        assert len(metric_cells) >= 5, "Metric row should have metric/expected/observed/delta/status cells"
        metric_name = metric_cells[0].inner_text()
        expected_val = metric_cells[1].inner_text()
        observed_val = metric_cells[2].inner_text()
        delta_val = metric_cells[3].inner_text()
        status_badge = metric_cells[4].inner_text()

        assert "ndcg" in metric_name.lower(), f"Metric should be nDCG, got: {metric_name}"
        float(expected_val)  # Should be numeric
        float(observed_val)  # Should be numeric
        print(f"  Metric: {metric_name}")
        print(f"  Expected: {expected_val}")
        print(f"  Observed: {observed_val}")
        print(f"  Delta: {delta_val}")
        print(f"  Status: {status_badge}")

        # Verify observed value is reasonable (not mocked - should be close to 0.3218)
        obs = float(observed_val)
        assert abs(obs - 0.3218) < 0.01, \
            f"Observed nDCG@10 should be close to 0.3218, got {obs}. " \
            "This may indicate mocked or incorrect results."
        print("  ✅ Expected metric and comparison verified")

        # 8. Verify commands and artifacts are visible
        print("\n[8/8] Checking commands and artifacts...")
        # Open commands drawer
        page.click("text=Show all commands")
        page.wait_for_selector("#commands-drawer.open", timeout=5000)
        cmd_section = page.query_selector("#command-list")
        assert cmd_section is not None, "Commands section should be present"
        cmds_text = cmd_section.inner_text()
        assert "SearchCollection" in cmds_text, "Should show SearchCollection command"
        assert "TrecEval" in cmds_text, "Should show TrecEval command"
        print("  ✅ Commands visible (SearchCollection, TrecEval)")

        # Open artifacts drawer
        page.click("text=Show artifacts")
        page.wait_for_selector("#artifacts-drawer.open", timeout=5000)
        art_section = page.query_selector("#artifact-list")
        assert art_section is not None, "Artifacts section should be present"
        art_text = art_section.inner_text()
        assert "run_file" in art_text or "run.nfcorpus" in art_text, \
            f"Artifacts should mention run file, got: {art_text}"
        print("  ✅ Artifacts visible")

        # Verify raw eval output
        page.click("text=Show raw eval output")
        page.wait_for_selector("#eval-raw-drawer.open", timeout=5000)
        raw_eval = page.query_selector("#eval-raw")
        raw_text = raw_eval.inner_text()
        assert "ndcg" in raw_text.lower(), "Raw eval output should contain ndcg"
        print("  ✅ Raw evaluation output visible")

        # Take a screenshot for evidence
        page.screenshot(path="test_screenshot.png")
        print("\n📸 Screenshot saved to test_screenshot.png")

        browser.close()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Browser test for NFCorpus Workbench")
    parser.add_argument("--url", default="http://localhost:10000", help="App URL")
    parser.add_argument("--timeout", type=int, default=300, help="Health check timeout (seconds)")
    args = parser.parse_args()
    run_tests(args.url, args.timeout)
