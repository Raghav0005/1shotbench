"""End-to-end browser test for the NFCorpus Live Retrieval Diagnostics Workbench.

This test verifies the workflow described in PRD.md > End-to-End Verification.
It is intentionally strict: every assertion that checks for real Anserini
output (docids, scores, snippets, observed metric values, command text,
artifact paths) is designed to fail if the app falls back to mocked output.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_health(base: str, timeout: float, want_ready: bool = True) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base}/health", timeout=2)
            r.raise_for_status()
            last = r.json()
            if not want_ready:
                return last
            if (
                last.get("anserini_available")
                and last.get("nfcorpus_ready")
                and last.get("search_available")
                and last.get("eval_available")
            ):
                return last
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"app never became ready within {timeout}s; last health = {last}")


@pytest.fixture(scope="module")
def app_server():
    if not os.environ.get("ANSERINI_JAR"):
        pytest.skip("ANSERINI_JAR not set; cannot run end-to-end test")
    if not shutil.which("java"):
        pytest.skip("java not on PATH")

    port = _free_port()
    rest_port = _free_port()
    data_dir = REPO_ROOT / "data"
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["ANSERINI_REST_PORT"] = str(rest_port)
    env["NFCORPUS_DATA_DIR"] = str(data_dir)
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_health(base, timeout=15, want_ready=False)
        # Then wait for full readiness (incl. background eval).
        ready = _wait_health(base, timeout=300, want_ready=True)
        yield {"base": base, "health": ready, "proc": proc}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_e2e_workflow(app_server):
    base = app_server["base"]

    # --- sanity: /health JSON satisfies the Render contract ---
    h = app_server["health"]
    for key in ("app", "anserini_available", "nfcorpus_ready",
                "search_available", "eval_available"):
        assert key in h, f"/health missing required key: {key}"
    assert h["app"] == "ok"
    assert h["anserini_available"] is True
    assert h["nfcorpus_ready"] is True
    assert h["search_available"] is True
    assert h["eval_available"] is True

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(base)

        # Page loaded -> wait for the readiness panel to populate
        page.wait_for_selector("#readiness-panel")
        page.wait_for_function(
            "document.body.dataset.ready === '1'", timeout=15000,
        )

        # ---- Readiness panel: NFCorpus + Anserini status visible. ----
        assert "nfcorpus" in page.text_content("#dataset-badge").lower()
        java_text = page.text_content("#r-java")
        jar_text = page.text_content("#r-jar")
        index_text = page.text_content("#r-index")
        repro_text = page.text_content("#r-reproduction")
        for label, text in [
            ("java", java_text), ("jar", jar_text),
            ("nfcorpus index", index_text), ("reproduction", repro_text),
        ]:
            assert "ok" in (text or "").lower() or "ready" in (text or "").lower(), \
                f"readiness cell {label!r} did not report ok/ready: {text!r}"
        # NFCorpus is the active dataset.
        assert re.search(r"beir-v1\.0\.0-nfcorpus", index_text + repro_text), \
            f"NFCorpus not identified in readiness panel: {index_text!r} / {repro_text!r}"

        # Render/Docker contract docs visible.
        page_text = page.text_content("body") or ""
        assert "PORT" in page_text, "PORT binding contract missing from UI"
        assert "0.0.0.0" in page_text, "0.0.0.0 binding contract missing from UI"
        assert "/health" in page_text, "/health contract missing from UI"

        # ---- Live NFCorpus query via the sample-query bar. ----
        sample_buttons = page.locator('[data-testid="sample-query"]')
        assert sample_buttons.count() >= 1, "no NFCorpus sample queries surfaced"
        sample_buttons.first.click()

        page.wait_for_selector('[data-testid="result-item"]', timeout=30000)
        items = page.locator('[data-testid="result-item"]')
        n = items.count()
        assert n >= 3, f"expected ≥3 NFCorpus search results, got {n}"

        # Each result must carry rank, docid, score, and a non-empty snippet.
        first = items.first
        docid = first.locator('[data-testid="result-docid"]').text_content() or ""
        score = first.locator('[data-testid="result-score"]').text_content() or ""
        rank = first.locator('[data-testid="result-rank"]').text_content() or ""
        snippet = first.locator('[data-testid="result-snippet"]').text_content() or ""
        title = first.locator('[data-testid="result-title"]').text_content() or ""
        assert rank.strip() == "1", f"first result rank should be 1, got {rank!r}"
        # NFCorpus docids look like MED-1234.
        assert re.match(r"^MED-\d+$", docid.strip()), \
            f"docid does not match NFCorpus format MED-NNN: {docid!r}"
        assert float(score) > 0, f"score is not a positive float: {score!r}"
        # Reject obviously-mocked snippets.
        assert len(snippet.strip()) >= 60, \
            f"snippet looks too short to be a real document: {snippet!r}"
        assert "lorem ipsum" not in snippet.lower(), "mocked snippet detected"
        assert "mock" not in (title + snippet).lower(), "mocked content detected"

        # Search meta surfaces the live Anserini REST URL & elapsed time.
        meta = page.text_content("#search-meta") or ""
        assert "beir-v1.0.0-nfcorpus.flat" in meta, \
            f"live Anserini REST URL not visible: {meta!r}"
        assert "io.anserini.cli.Search" in meta, \
            f"equivalent Anserini CLI command not visible: {meta!r}"

        # ---- Evaluation panel ----
        # Observed nDCG@10 cell.
        observed_ndcg = page.text_content('[data-testid="observed-ndcg_cut_10"]') or ""
        expected_ndcg = page.text_content('[data-testid="expected-ndcg_cut_10"]') or ""
        delta_ndcg = page.text_content('[data-testid="delta-ndcg_cut_10"]') or ""
        try:
            obs = float(observed_ndcg)
            exp = float(expected_ndcg)
        except ValueError:
            pytest.fail(
                f"observed/expected nDCG@10 not numeric (eval may not have run): "
                f"observed={observed_ndcg!r} expected={expected_ndcg!r}"
            )
        assert 0 < obs <= 1, f"observed nDCG@10 out of range: {obs}"
        # Reproduction discovery exposes the expected value.
        assert abs(exp - 0.3218) < 1e-3, \
            f"expected nDCG@10 not from reproduction discovery: {exp}"
        # A numeric delta is displayed.
        assert re.match(r"^[+\-]?\d", delta_ndcg.strip()), \
            f"delta cell is not numeric: {delta_ndcg!r}"

        # Observed metrics with no expected counterpart show up too (real eval output).
        for m in ("map", "recall_100"):
            v = page.text_content(f'[data-testid="observed-{m}"]') or ""
            try:
                fv = float(v)
            except ValueError:
                pytest.fail(f"extra metric {m} missing observed value: {v!r}")
            assert 0 < fv < 1, f"{m} observed out of range: {fv}"

        # ---- Commands & artifacts drawer ----
        for cmd_key, must_contain in [
            ("fatjar_verify", "io.anserini.cli.PrebuiltIndexRegistry"),
            ("reproduction_show", "io.anserini.reproduce.ReproduceFromPrebuiltIndexes"),
            ("rest_server", "io.anserini.api.RestServer"),
            ("bm25_search", "io.anserini.search.SearchCollection"),
            ("bm25_eval", "io.anserini.eval.TrecEval"),
        ]:
            txt = page.text_content(f'[data-testid="cmd-{cmd_key}"]') or ""
            assert must_contain in txt, \
                f"command {cmd_key} missing or doesn't contain {must_contain!r}: {txt!r}"
            # The jar path must be a real resolved path, not a shell template.
            assert "$ANSERINI_JAR" not in txt, \
                f"command {cmd_key} contains unexpanded $ANSERINI_JAR: {txt!r}"
            assert re.search(r"anserini-[\d.]+-fatjar\.jar|/opt/anserini/anserini\.jar", txt), \
                f"command {cmd_key} does not reference a real jar path: {txt!r}"

        # Real artifact paths.
        run_file = page.text_content('[data-testid="art-run_file"]') or ""
        assert "run.nfcorpus.bm25.txt" in run_file, \
            f"BM25 run file artifact path missing: {run_file!r}"
        eval_file = page.text_content('[data-testid="art-eval_file"]') or ""
        assert "eval.nfcorpus.bm25.txt" in eval_file, \
            f"eval output file artifact path missing: {eval_file!r}"

        # The TrecEval text preview embeds a real metric line.
        eval_preview = page.text_content('[data-testid="preview-eval_output"]') or ""
        assert "ndcg_cut_10" in eval_preview and "all" in eval_preview, \
            f"eval output preview lacks real TrecEval line: {eval_preview!r}"

        # ---- Verify / Rerun button forces a fresh eval. ----
        prior_completed = (
            httpx.get(f"{base}/api/state", timeout=10).json()["eval"]["completed_at"]
        )
        page.click("#rerun-btn")
        # Source label should switch to "fresh rerun"; status returns to ok.
        deadline = time.time() + 240
        ok_fresh = False
        while time.time() < deadline:
            state = httpx.get(f"{base}/api/state", timeout=10).json()
            e = state["eval"]
            if (
                e["status"] == "ok"
                and e["fresh"]
                and e["completed_at"]
                and (prior_completed is None or e["completed_at"] > prior_completed)
            ):
                ok_fresh = True
                break
            time.sleep(1)
        assert ok_fresh, "Verify/Rerun did not produce a fresh evaluation completion"
        # UI reflects the fresh state.
        page.wait_for_function(
            "document.querySelector('[data-testid=\"eval-source\"]').textContent.includes('fresh')",
            timeout=15000,
        )

        browser.close()


def test_health_contract(app_server):
    """Sanity: /health is a JSON document matching the documented contract."""
    base = app_server["base"]
    r = httpx.get(f"{base}/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    for key in ("app", "anserini_available", "nfcorpus_ready",
                "search_available", "eval_available", "eval_status"):
        assert key in body, f"/health missing key {key}"
