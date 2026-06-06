"""End-to-end browser test for NFCorpus Live Retrieval Diagnostics Workbench.

This test proves the app exercises real Anserini-backed search and evaluation
rather than mocked results.
"""

import os
import subprocess
import sys
import time

import pytest
from playwright.sync_api import sync_playwright, expect

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:10000")
SETUP_TIMEOUT_SEC = int(os.environ.get("SETUP_TIMEOUT_SEC", "180"))


def wait_for_ready(page):
    """Poll health endpoint until app reports ready or timeout."""
    deadline = time.time() + SETUP_TIMEOUT_SEC
    last_status = None
    while time.time() < deadline:
        try:
            resp = page.request.get(f"{BASE_URL}/health")
            data = resp.json()
            last_status = data
            if data.get("status") == "ok" and data.get("search_available") and data.get("evaluation_available"):
                return data
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"App did not become ready within {SETUP_TIMEOUT_SEC}s. Last status: {last_status}")


def test_health_endpoint():
    import requests
    resp = requests.get(f"{BASE_URL}/health", timeout=30)
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "anserini_available" in data
    assert "nfcorpus_ready" in data
    assert "search_available" in data
    assert "evaluation_available" in data


def test_full_workflow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Open the app
        page.goto(BASE_URL)
        page.wait_for_selector("text=NFCorpus Live Retrieval Diagnostics Workbench", timeout=10000)

        # 2. Wait for readiness panel
        page.wait_for_selector("text=Readiness", timeout=SETUP_TIMEOUT_SEC * 1000)
        # Wait until status is not "Loading…"
        expect(page.locator("#status-badge")).not_to_have_text("Loading…", timeout=SETUP_TIMEOUT_SEC * 1000)

        # 3. Verify NFCorpus is identified as the active dataset
        page.wait_for_selector("text=NFCorpus", timeout=10000)
        body = page.locator("body").inner_text()
        assert "NFCorpus" in body, "NFCorpus should be identified as the active dataset"
        assert "BEIR" in body or "beir" in body.lower(), "BEIR reference expected"

        # 4. Verify Anserini setup status is visible
        expect(page.locator("#status-rows")).to_contain_text("Anserini fatjar")
        expect(page.locator("#status-rows")).to_contain_text("Java")

        # 5. Run a live NFCorpus query
        search_input = page.locator("#search-input")
        search_input.fill("deafness")
        page.locator("button.primary", has_text="Search").click()

        # 6. Verify ranked search results appear
        page.wait_for_selector(".result-item", timeout=30000)
        results = page.locator(".result-item")
        expect(results.first).to_be_visible()
        count = results.count()
        assert count > 0, "Expected at least one search result"

        # Verify document ids, ranks, scores, and text/snippets
        first = results.first
        first_text = first.inner_text()
        assert "Rank 1" in first_text, "Result should show rank"
        assert "Score" in first_text, "Result should show score"
        assert "DocID:" in first_text, "Result should show document id"
        # Should have some snippet text, not empty
        assert len(first_text) > 50, "Result should contain snippet text"

        # 7. Verify evaluation panel displays at least one numeric observed metric
        page.wait_for_selector("#eval-metrics .metric-value", timeout=SETUP_TIMEOUT_SEC * 1000)
        metric_values = page.locator("#eval-metrics .metric-value")
        expect(metric_values.first).to_be_visible()
        val_text = metric_values.first.inner_text()
        assert val_text.replace(".", "").replace("-", "").isdigit(), f"Expected numeric metric, got: {val_text}"

        # 8. Verify expected metric information appears
        eval_panel = page.locator("#eval-metrics").inner_text()
        assert "Expected:" in eval_panel, "Expected metric should be shown"

        # 9. Verify observed-vs-expected comparison status or delta appears
        assert "Delta:" in eval_panel, "Delta should be shown"

        # 10. Verify exact command text and artifact paths/previews are visible
        # Commands drawer is open by default; wait for content to load
        commands_content = page.locator("#commands-content")
        expect(commands_content).to_contain_text("java", timeout=SETUP_TIMEOUT_SEC * 1000)
        expect(commands_content).to_contain_text("SearchCollection")
        expect(commands_content).to_contain_text("trec_eval")

        page.locator("summary", has_text="Artifacts").click()
        artifacts_content = page.locator("#artifacts-content")
        expect(artifacts_content).to_contain_text("run_file")
        expect(artifacts_content).to_contain_text("eval_file")

        # 11. Verify Docker/Render readiness contract is documented
        body_text = page.locator("body").inner_text()
        assert "0.0.0.0" in body_text, "Port binding documentation should mention 0.0.0.0"
        assert "/health" in body_text, "Health endpoint should be documented"
        assert "PORT" in body_text or "port" in body_text.lower(), "PORT env should be documented"

        # 12. Extra: hit the API directly to confirm search returns real Anserini JSON
        resp = page.request.get(f"{BASE_URL}/api/search?q=deafness&hits=3")
        search_json = resp.json()
        assert "candidates" in search_json, "Search API should return candidates"
        assert len(search_json["candidates"]) > 0, "Search API should return non-empty candidates"
        cand = search_json["candidates"][0]
        assert "docid" in cand, "Candidate should have docid"
        assert "score" in cand, "Candidate should have score"
        assert "doc" in cand, "Candidate should have doc content"

        # 13. Extra: verify evaluation API returns real observed metric
        eval_resp = page.request.get(f"{BASE_URL}/api/status")
        eval_data = eval_resp.json()
        assert eval_data["evaluation"]["run"] is True, "Evaluation should have run"
        assert "nDCG@10" in eval_data["evaluation"]["observed"], "nDCG@10 should be observed"
        obs = eval_data["evaluation"]["observed"]["nDCG@10"]
        exp = eval_data["evaluation"]["expected"]["nDCG@10"]
        assert isinstance(obs, float), "Observed metric should be a real float"
        assert isinstance(exp, float), "Expected metric should be a real float"
        # Values should be close to the known NFCorpus BM25 baseline (~0.3218)
        assert 0.25 <= obs <= 0.40, f"Observed nDCG@10 {obs} seems outside plausible NFCorpus BM25 range"

        browser.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
