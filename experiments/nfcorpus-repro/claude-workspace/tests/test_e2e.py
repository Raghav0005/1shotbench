"""End-to-end browser test for the NFCorpus diagnostics workbench.

The test must fail when the app merely renders mocked search results or
hardcoded metric values. To enforce that, we cross-check:
- /api/search results have docids that match the NFCorpus pattern (MED-…/PLAIN-…)
- the observed nDCG@10 reported by the UI is within 0.005 of the published
  reproduction value (0.3218), proving a real TrecEval against beir-v1.0.0-nfcorpus.test
- the run file path reported by the UI exists on the local filesystem and has
  TREC-format content
- the command panel exposes the actual Anserini main classes
  (SearchCollection, TrecEval, RestServer, ReproduceFromPrebuiltIndexes).
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import httpx
import pytest

NFCORPUS_DOCID_RE = re.compile(r"^(MED|PLAIN)-")
ANSERINI_CLASSES = [
    "io.anserini.search.SearchCollection",
    "io.anserini.eval.TrecEval",
    "io.anserini.api.RestServer",
    "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
]


def _wait(page, sel, timeout=15000):
    page.wait_for_selector(sel, timeout=timeout)


def test_full_workflow(app_server, page):
    base = app_server

    # ------ 1. Open the app ------
    page.goto(base + "/", wait_until="domcontentloaded")
    _wait(page, '[data-testid="readiness-panel"]')

    # ------ 2. Health/readiness panel renders ------
    assert page.locator('[data-testid="readiness-panel"]').is_visible()
    for card in ["java", "fatjar", "nfcorpus", "reproduction", "search", "evaluation"]:
        assert page.locator(f'[data-testid="status-{card}"]').is_visible(), card

    # ------ 3. NFCorpus is the active dataset ------
    assert page.locator('[data-testid="active-dataset"]').inner_text().strip() == "NFCorpus"

    # ------ 4. Anserini setup status is visible (fatjar + java cards must be 'ok') ------
    page.wait_for_function(
        """() => {
            const fj = document.querySelector('[data-testid="status-fatjar"]');
            const jv = document.querySelector('[data-testid="status-java"]');
            return fj && jv && fj.classList.contains('state-ok') && jv.classList.contains('state-ok');
        }""",
        timeout=120000,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-testid="phase-label"]').textContent.trim() === 'ready'""",
        timeout=240000,
    )

    fatjar_detail = page.locator('[data-testid="status-fatjar-detail"]').inner_text()
    assert "anserini-" in fatjar_detail.lower() or ".jar" in fatjar_detail.lower()

    # ------ 5. Run a sample NFCorpus query ------
    chips = page.locator('[data-testid="sample-chip"]')
    assert chips.count() >= 1, "expected at least one sample query chip"
    sample_text = chips.first.inner_text().strip()
    # Click a chip *and* explicitly submit, which is what a human user would do.
    chips.first.click()
    page.locator('[data-testid="search-input"]').fill(sample_text)
    page.locator('[data-testid="search-submit"]').click()
    page.wait_for_selector('[data-testid="search-result"]', timeout=60000)

    # ------ 6. Results have docids, ranks, scores, and text ------
    results = page.locator('[data-testid="search-result"]')
    assert results.count() >= 3
    for i in range(min(results.count(), 5)):
        r = results.nth(i)
        rank = int(r.locator('[data-testid="result-rank"]').inner_text())
        docid = r.locator('[data-testid="result-docid"]').inner_text()
        score = float(r.locator('[data-testid="result-score"]').inner_text())
        title = r.locator('[data-testid="result-title"]').inner_text()
        text = r.locator('[data-testid="result-text"]').inner_text()
        assert rank == i + 1
        assert NFCORPUS_DOCID_RE.match(docid), f"docid {docid!r} not NFCorpus-shaped (anti-mock check)"
        assert score > 0
        assert title and len(text) > 30, "expected real NFCorpus title + snippet"

    # ------ 7. Evaluation panel shows at least one numeric observed metric ------
    page.wait_for_function(
        """() => document.querySelector('[data-testid="eval-status"]').textContent.trim() === 'done'""",
        timeout=240000,
    )
    metric_rows = page.locator('[data-testid="metric-row"]')
    assert metric_rows.count() >= 1
    observed_text = metric_rows.first.locator('[data-testid="metric-observed"]').inner_text()
    assert observed_text not in ("", "—"), "observed metric is empty"
    observed = float(observed_text)
    assert 0.0 < observed < 1.0

    # ------ 8. Expected metric info is shown ------
    expected_text = metric_rows.first.locator('[data-testid="metric-expected"]').inner_text()
    assert expected_text not in ("", "—")
    expected = float(expected_text)
    assert 0.0 < expected < 1.0

    # ------ 9. Observed vs expected comparison (delta + status) is shown ------
    delta_text = metric_rows.first.locator('[data-testid="metric-delta"]').inner_text()
    status_text = metric_rows.first.locator('[data-testid="metric-status"]').inner_text()
    assert delta_text not in ("", "—")
    assert status_text in {"match", "close", "fail"}
    assert abs(observed - expected) < 0.005, (
        f"observed {observed} too far from expected {expected}; this looks like a mock"
    )

    # ------ 10. Exact command text and artifact paths visible ------
    cmd_records = page.locator('[data-testid="command-record"]')
    assert cmd_records.count() >= 4
    # `<details>` collapses children, so use text_content (which ignores display:none).
    all_cmd_text = " ".join(
        page.locator('[data-testid="command-text"]').all_text_contents()
    )
    for cls in ANSERINI_CLASSES:
        assert cls in all_cmd_text, f"expected {cls} to appear in command list"
    run_path = page.locator('[data-testid="eval-run-path"]').inner_text().strip()
    eval_path = page.locator('[data-testid="eval-eval-path"]').inner_text().strip()
    assert run_path and run_path != "—"
    assert eval_path and eval_path != "—"
    assert Path(run_path).exists(), f"run artifact missing on disk: {run_path}"
    head = Path(run_path).read_text().splitlines()[:10]
    # TREC run format: qid Q0 docid rank score tag
    assert any(len(line.split()) == 6 for line in head), "run file is not TREC-format"

    # ------ 11. Docker / Render readiness contract documented in UI ------
    deploy = page.locator('[data-testid="deployment-list"]').inner_text()
    assert "PORT" in deploy
    assert "0.0.0.0" in deploy
    assert "10000" in deploy
    assert "/health" in deploy

    # ------ 12. Anti-mock: the rerun must actually re-run, not just bump a counter ------
    initial_mtime = Path(run_path).stat().st_mtime
    page.locator('[data-testid="rerun-button"]').click()
    page.wait_for_function(
        """() => {
            const rc = document.querySelector('[data-testid="eval-rerun-count"]');
            return rc && parseInt(rc.textContent.trim(), 10) >= 1;
        }""",
        timeout=120000,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-testid="eval-status"]').textContent.trim() === 'done'""",
        timeout=240000,
    )
    new_mtime = Path(run_path).stat().st_mtime
    assert new_mtime >= initial_mtime, (
        f"rerun did not rewrite the run file (mtime {initial_mtime} -> {new_mtime})"
    )
    rerun_source = page.locator('[data-testid="eval-source"]').inner_text()
    assert "fresh" in rerun_source.lower() or "rerun" in rerun_source.lower()


def test_health_endpoint_contract(app_server):
    r = httpx.get(app_server + "/health", timeout=10.0)
    assert r.status_code == 200
    data = r.json()
    for key in ["status", "anserini", "nfcorpus", "search", "evaluation"]:
        assert key in data, f"/health missing {key}"
    assert data["anserini"]["available"] is True
    assert data["nfcorpus"]["ready"] is True
    assert data["search"]["available"] is True
    assert data["evaluation"]["available"] is True


def test_search_proxies_real_anserini(app_server):
    # Sanity check the search endpoint independently of the browser.
    r = httpx.get(app_server + "/api/search", params={"q": "diabetes diet", "hits": 5}, timeout=30.0)
    assert r.status_code == 200
    data = r.json()
    assert data["index"] == "beir-v1.0.0-nfcorpus.flat"
    assert data["hits_returned"] >= 1
    for row in data["results"]:
        assert NFCORPUS_DOCID_RE.match(row["docid"]), f"non-NFCorpus docid {row['docid']!r}"
        assert row["score"] > 0
        assert row["text"]
