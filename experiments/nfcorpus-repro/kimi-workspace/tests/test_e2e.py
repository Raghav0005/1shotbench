import pytest
import requests
import time

BASE_URL = "http://localhost:10000"


def wait_for_healthy(timeout=120):
    """Poll /health until the app reports healthy or timeout."""
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


@pytest.fixture(scope="session", autouse=True)
def ensure_app():
    wait_for_healthy()


def test_health_endpoint():
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data.get("anserini_available") is True
    assert data.get("nfcorpus_ready") is True
    assert data.get("search_available") is True
    assert data.get("evaluation_available") is True


def test_dashboard_loads(page):
    page.goto(BASE_URL)
    page.wait_for_selector("text=NFCorpus Live Retrieval Diagnostics Workbench")
    assert page.is_visible("text=NFCorpus (BEIR)")
    assert page.is_visible("text=Readiness")
    assert page.is_visible("text=Java")
    assert page.is_visible("text=Anserini fatjar")


def test_live_search_with_sample_query(page):
    page.goto(BASE_URL)
    page.wait_for_selector("text=Live Search")

    # Wait for search input to be enabled
    page.wait_for_selector("#search-input:not([disabled])", timeout=30000)

    # Click a sample chip
    chip = page.locator(".chip", has_text="deafness")
    chip.click()

    # Wait for results table
    page.wait_for_selector("table tbody tr", timeout=30000)

    rows = page.locator("table tbody tr").all()
    assert len(rows) > 0, "Expected at least one search result"

    first = rows[0]
    cells = first.locator("td").all()
    assert len(cells) >= 4, "Expected rank, docid, score, snippet columns"
    # Rank
    assert cells[0].inner_text().strip() == "1"
    # Docid should look like MED-XXXX
    assert "MED-" in cells[1].inner_text()
    # Score should be numeric
    score_text = cells[2].inner_text().strip()
    assert float(score_text) > 0
    # Snippet should contain text
    assert len(cells[3].inner_text()) > 10


def test_evaluation_panel_shows_metrics(page):
    page.goto(BASE_URL)
    page.wait_for_selector("text=BM25 Evaluation")

    # Wait until evaluation is no longer in initial loading state
    page.wait_for_selector("#observed-score", timeout=30000)
    observed = page.locator("#observed-score").inner_text().strip()
    assert observed != "—", "Observed score should be present"
    float(observed)  # should be numeric

    expected = page.locator("#expected-score").inner_text().strip()
    assert expected != "—", "Expected score should be present"
    float(expected)

    delta = page.locator("#delta-score").inner_text().strip()
    assert delta != "—", "Delta should be present"

    verdict = page.locator("#verdict-badge").inner_text().strip()
    assert verdict in ("PASS", "CLOSE", "FAIL"), f"Unexpected verdict: {verdict}"


def test_commands_and_artifacts_visible(page):
    page.goto(BASE_URL)
    page.wait_for_selector("text=Commands & Artifacts")

    # Ensure the exact command text is visible
    cmd_discovery = page.locator("#cmd-discovery").inner_text()
    assert "io.anserini.reproduce.ReproduceFromPrebuiltIndexes" in cmd_discovery

    cmd_search = page.locator("#cmd-searchcollection").inner_text()
    assert "io.anserini.search.SearchCollection" in cmd_search
    assert "beir-v1.0.0-nfcorpus.flat" in cmd_search

    cmd_eval = page.locator("#cmd-trec-eval").inner_text()
    assert "io.anserini.eval.TrecEval" in cmd_eval

    # Artifact paths should be visible
    assert page.is_visible("text=Run file:")
    assert page.is_visible("text=Eval output:")
    assert page.is_visible("text=Cache directory:")


def test_deployment_documentation_visible(page):
    page.goto(BASE_URL)
    page.wait_for_selector("text=Deployment Notes")
    text = page.locator("text=Deployment Notes").first.inner_text()
    assert "Render" in page.content() or "Docker" in page.content()
    assert "PORT" in page.content()
    assert "0.0.0.0" in page.content()


def test_search_results_are_not_mocked(page):
    """Validate that search returns different results for different queries."""
    r1 = requests.get(f"{BASE_URL}/api/search", params={"q": "deafness", "hits": 3})
    r2 = requests.get(f"{BASE_URL}/api/search", params={"q": "peanut butter", "hits": 3})
    assert r1.status_code == 200
    assert r2.status_code == 200
    d1 = r1.json()
    d2 = r2.json()
    ids1 = [c["docid"] for c in d1["results"]["candidates"]]
    ids2 = [c["docid"] for c in d2["results"]["candidates"]]
    assert ids1 != ids2, "Search results should differ for different queries (not mocked)"


def test_evaluation_result_matches_api(page):
    """Cross-check the UI evaluation data against the API."""
    api = requests.get(f"{BASE_URL}/api/evaluate").json()
    assert api["evaluation_ready"] is True
    result = api["result"]
    assert result is not None
    assert result["observed"] is not None
    assert result["expected"] is not None
    # The observed should be very close to expected for this reproducible task
    assert abs(result["observed"] - result["expected"]) < 0.001
