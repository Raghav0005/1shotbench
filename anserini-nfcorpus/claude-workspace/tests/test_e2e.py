"""End-to-end Playwright test for the NFCorpus Diagnostics Workbench.

The test asserts that the app drives a real Anserini-backed workflow and
surfaces it in the dashboard, per the PRD's End-to-End Verification section.

Usage:
    # Start the app first (Docker or `python -m app.server`).
    APP_URL=http://localhost:10000 pytest tests/test_e2e.py -s
"""

from __future__ import annotations

import os
import re
import time

import pytest
import requests
from playwright.sync_api import Page, expect


APP_URL = os.environ.get("APP_URL", "http://localhost:10000")
READY_TIMEOUT = int(os.environ.get("APP_READY_TIMEOUT", "600"))


@pytest.fixture(scope="session", autouse=True)
def wait_for_ready() -> None:
    """Block until the app's setup pipeline reaches 'ready' or fail loudly."""
    deadline = time.time() + READY_TIMEOUT
    last: dict = {}
    while time.time() < deadline:
        try:
            r = requests.get(f"{APP_URL}/health", timeout=10)
            last = r.json()
            if (
                last.get("anserini_available")
                and last.get("nfcorpus_ready")
                and last.get("search_available")
                and last.get("evaluation_available")
            ):
                return
        except requests.RequestException as exc:
            last = {"error": str(exc)}
        time.sleep(3)
    pytest.fail(
        f"App did not become ready within {READY_TIMEOUT}s; last /health: {last}"
    )


def _expect_text(page: Page, testid: str, pattern: str, timeout: int = 60000) -> None:
    locator = page.get_by_test_id(testid)
    expect(locator).to_be_visible(timeout=timeout)
    expect(locator).to_contain_text(re.compile(pattern), timeout=timeout)


def test_dashboard_end_to_end(page: Page) -> None:
    page.set_default_timeout(60000)
    page.goto(APP_URL)

    # Header / dataset is NFCorpus.
    expect(page.get_by_test_id("active-dataset")).to_contain_text("NFCorpus")

    # Readiness panel visible.
    expect(page.get_by_test_id("readiness-panel")).to_be_visible()

    # The setup phase should reach "ready" (set on the pill).
    expect(page.get_by_test_id("phase-pill")).to_have_attribute(
        "data-state", "ready", timeout=READY_TIMEOUT * 1000
    )

    # Java + fatjar + nfcorpus + reproduction + search + evaluation cards green.
    _expect_text(page, "status-java", r"Java\s+\d+")
    _expect_text(page, "status-fatjar", r"verified")
    _expect_text(page, "status-nfcorpus", r"ready")
    _expect_text(page, "status-reproduction", r"found")
    _expect_text(page, "status-search", r"available")
    _expect_text(page, "status-evaluation", r"match|close|fail|observed-only")

    # Evaluation panel: at least one observed numeric metric and a comparison.
    expect(page.get_by_test_id("metrics-table")).to_be_visible()
    observed_cell = page.locator('[data-testid^="metric-observed-"]').first
    expect(observed_cell).to_be_visible()
    observed_text = observed_cell.text_content() or ""
    assert re.match(r"^\d+\.\d+$", observed_text.strip()), f"observed metric should be numeric, got {observed_text!r}"

    expected_cell = page.locator('[data-testid^="metric-expected-"]').first
    expected_text = expected_cell.text_content() or ""
    assert re.match(r"^\d+\.\d+$", expected_text.strip()), f"expected metric should be numeric, got {expected_text!r}"

    delta_cell = page.locator('[data-testid^="metric-delta-"]').first
    delta_text = (delta_cell.text_content() or "").strip()
    assert delta_text and delta_text != "—", "delta should be populated"

    status_cell = page.locator('[data-testid^="metric-status-"]').first
    status_text = (status_cell.text_content() or "").strip()
    assert status_text in {"match", "close", "fail"}, f"unexpected status {status_text!r}"

    # Commands panel exposes the exact Anserini invocations and artifact paths.
    expect(page.get_by_test_id("cmd-verify_fatjar_registry")).to_be_visible()
    expect(page.get_by_test_id("cmd-search_collection")).to_contain_text(
        "io.anserini.search.SearchCollection"
    )
    expect(page.get_by_test_id("cmd-trec_eval")).to_contain_text(
        "io.anserini.eval.TrecEval"
    )
    expect(page.get_by_test_id("cmd-restserver")).to_contain_text(
        "io.anserini.api.RestServer"
    )

    # Artifact paths visible (run + eval files).
    run_path = (page.get_by_test_id("eval-run-path").text_content() or "").strip()
    eval_path = (page.get_by_test_id("eval-eval-path").text_content() or "").strip()
    assert run_path and run_path != "—" and "run.beir.bm25.nfcorpus" in run_path
    assert eval_path and eval_path != "—"

    # Deployment / Render contract documented in the UI.
    deployment_text = page.get_by_test_id("deployment-list").text_content() or ""
    assert "PORT" in deployment_text and "/health" in deployment_text and "0.0.0.0" in deployment_text

    # ----- Live search via a sample NFCorpus topic -----
    page.get_by_test_id("sample-PLAIN-2460").click()
    expect(page.get_by_test_id("result-count")).to_be_visible(timeout=120000)
    expect(page.get_by_test_id("result-count")).to_contain_text(re.compile(r"\d+"))
    expect(page.get_by_test_id("result-1")).to_be_visible()
    expect(page.get_by_test_id("result-docid-1")).to_contain_text(re.compile(r"\S"))
    expect(page.get_by_test_id("result-score-1")).to_contain_text(re.compile(r"score\s+\d"))
    snippet_text = (page.get_by_test_id("result-snippet-1").text_content() or "").strip()
    assert len(snippet_text) >= 80, f"snippet should contain real document text, got {snippet_text!r}"

    # ----- Live search with a free-text query -----
    page.get_by_test_id("search-input").fill("diabetes diet")
    page.get_by_test_id("search-submit").click()
    expect(page.get_by_test_id("result-count")).to_contain_text(re.compile(r"\d+"))
    expect(page.get_by_test_id("result-1")).to_be_visible()

    # ----- Cross-check the API directly: real Anserini, not mocks -----
    api = requests.get(
        f"{APP_URL}/api/search",
        params={"q": "diabetes diet", "hits": 5},
        timeout=60,
    ).json()
    assert api["ok"], api
    assert api["backend"] == "anserini.api.RestServer"
    assert api["index"] == "beir-v1.0.0-nfcorpus.flat"
    assert api["result_count"] >= 1
    first = api["results"][0]
    assert first["docid"]
    assert isinstance(first["score"], (int, float))
    assert first["text"] and len(first["text"]) > 50, "live search must return real document content"

    # ----- Evaluation API confirms observed and expected metrics are real -----
    ev = requests.get(f"{APP_URL}/api/evaluation", timeout=30).json()
    assert ev["evaluation"]["ran"], ev
    assert ev["evaluation"]["metrics"], "must have at least one observed metric"
    # ndcg_cut_10 is the qrels-driven key for the NFCorpus reproduction target.
    assert "ndcg_cut_10" in ev["evaluation"]["metrics"]
    expected = ev["reproduction_target"]["expected_scores"]
    assert expected, "reproduction discovery should expose expected metric(s)"
    # Commands must reference the Anserini classes that produced the metrics.
    assert "io.anserini.search.SearchCollection" in ev["commands"]["search_collection"]["cmd"]
    assert "io.anserini.eval.TrecEval" in ev["commands"]["trec_eval"]["cmd"]

    # ----- Rerun the evaluation to prove the backend re-executes commands -----
    rerun_count_before = int(page.get_by_test_id("eval-rerun-count").text_content() or "0")
    rerun = requests.post(f"{APP_URL}/api/evaluation/rerun", timeout=600).json()
    assert rerun["ok"], rerun
    assert rerun["evaluation"]["fresh"] is True
    # Allow the UI poll to refresh, then verify counter increment & source label.
    deadline = time.time() + 30
    while time.time() < deadline:
        new_count = int(page.get_by_test_id("eval-rerun-count").text_content() or "0")
        if new_count > rerun_count_before:
            break
        time.sleep(2)
    else:
        raise AssertionError("UI did not reflect a fresh rerun")
    expect(page.get_by_test_id("eval-source")).to_contain_text("fresh rerun")


def test_health_endpoint_contract() -> None:
    r = requests.get(f"{APP_URL}/health", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in (
        "status",
        "anserini_available",
        "nfcorpus_ready",
        "search_available",
        "evaluation_available",
    ):
        assert key in body, f"missing /health key {key}: {body}"
    assert body["dataset"] == "nfcorpus"
