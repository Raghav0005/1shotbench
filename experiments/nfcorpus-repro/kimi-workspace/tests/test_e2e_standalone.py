#!/usr/bin/env python3
"""
Standalone end-to-end browser test for the NFCorpus Diagnostics Workbench.
Uses Playwright directly (no pytest) to avoid environment-specific pytest issues.
"""
import sys
import time
import requests
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:10000"


def wait_for_healthy(timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=5)
            data = r.json()
            if data.get("status") == "healthy":
                return data
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("App did not become healthy in time")


def run_tests():
    print("Waiting for app to be healthy...")
    health = wait_for_healthy()
    assert health.get("anserini_available") is True
    assert health.get("nfcorpus_ready") is True
    assert health.get("search_available") is True
    assert health.get("evaluation_available") is True
    print("App is healthy.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. Dashboard loads and shows readiness
        print("Opening dashboard...")
        page.goto(BASE_URL)
        page.wait_for_selector("text=NFCorpus Live Retrieval Diagnostics Workbench")
        assert page.is_visible("text=NFCorpus (BEIR)"), "Dataset label missing"
        assert page.is_visible("text=Readiness"), "Readiness panel missing"
        assert page.is_visible("text=Java"), "Java status missing"
        assert page.is_visible("text=Anserini fatjar"), "Fatjar status missing"
        print("Dashboard loaded correctly.")

        # 2. Live search with sample query
        print("Testing live search...")
        page.wait_for_selector("#search-input:not([disabled])", timeout=30000)
        chip = page.locator(".chip", has_text="deafness")
        chip.click()
        page.wait_for_selector("table tbody tr", timeout=30000)
        rows = page.locator("table tbody tr").all()
        assert len(rows) > 0, "Expected at least one search result"
        first = rows[0]
        cells = first.locator("td").all()
        assert len(cells) >= 4, "Expected 4 columns"
        assert cells[0].inner_text().strip() == "1", "Rank should be 1"
        assert "MED-" in cells[1].inner_text(), "Docid should contain MED-"
        score = float(cells[2].inner_text().strip())
        assert score > 0, "Score should be positive"
        assert len(cells[3].inner_text()) > 10, "Snippet should have content"
        print("Live search passed.")

        # 3. Evaluation panel shows metrics
        print("Checking evaluation panel...")
        page.wait_for_selector("#observed-score", timeout=30000)
        observed = page.locator("#observed-score").inner_text().strip()
        assert observed != "—", "Observed score missing"
        assert float(observed) > 0, "Observed score should be numeric"

        expected = page.locator("#expected-score").inner_text().strip()
        assert expected != "—", "Expected score missing"
        assert float(expected) > 0, "Expected score should be numeric"

        delta = page.locator("#delta-score").inner_text().strip()
        assert delta != "—", "Delta missing"

        verdict = page.locator("#verdict-badge").inner_text().strip()
        assert verdict in ("PASS", "CLOSE", "FAIL"), f"Unexpected verdict: {verdict}"
        print(f"Evaluation panel passed (observed={observed}, expected={expected}, verdict={verdict}).")

        # 4. Commands and artifacts visible
        print("Checking commands and artifacts...")
        assert page.is_visible("text=Commands & Artifacts")
        cmd_discovery = page.locator("#cmd-discovery").inner_text()
        assert "io.anserini.reproduce.ReproduceFromPrebuiltIndexes" in cmd_discovery
        cmd_search = page.locator("#cmd-searchcollection").inner_text()
        assert "io.anserini.search.SearchCollection" in cmd_search
        assert "beir-v1.0.0-nfcorpus.flat" in cmd_search
        cmd_eval = page.locator("#cmd-trec-eval").inner_text()
        assert "io.anserini.eval.TrecEval" in cmd_eval
        assert page.is_visible("text=Run file:")
        assert page.is_visible("text=Eval output:")
        assert page.is_visible("text=Cache directory:")
        print("Commands and artifacts visible.")

        # 5. Deployment documentation visible
        print("Checking deployment docs...")
        assert page.is_visible("text=Deployment Notes")
        content = page.content()
        assert "PORT" in content
        assert "0.0.0.0" in content
        print("Deployment docs visible.")

        # 6. Search results are not mocked (API-level check)
        print("Verifying search results are not mocked...")
        r1 = requests.get(f"{BASE_URL}/api/search", params={"q": "deafness", "hits": 3})
        r2 = requests.get(f"{BASE_URL}/api/search", params={"q": "peanut butter", "hits": 3})
        assert r1.status_code == 200
        assert r2.status_code == 200
        d1 = r1.json()
        d2 = r2.json()
        ids1 = [c["docid"] for c in d1["results"]["candidates"]]
        ids2 = [c["docid"] for c in d2["results"]["candidates"]]
        assert ids1 != ids2, "Search results should differ for different queries"
        print("Search results are genuine.")

        # 7. API evaluation cross-check
        print("Checking API evaluation result...")
        api = requests.get(f"{BASE_URL}/api/evaluate").json()
        assert api["evaluation_ready"] is True
        result = api["result"]
        assert result is not None
        assert result["observed"] is not None
        assert result["expected"] is not None
        assert abs(result["observed"] - result["expected"]) < 0.001
        print("API evaluation cross-check passed.")

        browser.close()

    print("\n=== ALL TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_tests())
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        sys.exit(1)
