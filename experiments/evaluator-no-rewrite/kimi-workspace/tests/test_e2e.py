import subprocess
import sys
import time
import pytest
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://127.0.0.1:5000"

@pytest.fixture(scope="module")
def flask_app():
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to be ready
    for _ in range(60):
        try:
            import urllib.request
            with urllib.request.urlopen(BASE_URL + "/api/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("Flask app did not start in time")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

def test_full_workflow(flask_app):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)

        # Wait for catalog to load
        page.wait_for_selector("#indexList .index-item", timeout=15000)

        # 1. Confirm catalog exposes more than a hardcoded single CACM option
        items = page.locator("#indexList .index-item")
        count = items.count()
        assert count > 1, f"Expected more than 1 index in catalog, got {count}"

        # 2. Confirm at least one catalog-only/non-selected index is visible
        # (if CACM is evaluable, any other index counts)
        catalog_only = page.locator("#indexList .index-item.catalog-only")
        assert catalog_only.count() > 0, "Expected at least one catalog-only index visible"

        # 3. Confirm CACM is selected or selectable
        cacm_item = page.locator("#indexList .index-item[data-name='cacm']")
        expect(cacm_item).to_have_count(1)
        if not cacm_item.locator(".selected").count():
            cacm_item.click()
            page.wait_for_timeout(300)

        # CACM should be selected now
        expect(page.locator("#indexList .index-item.selected")).to_have_attribute("data-name", "cacm")

        # 4. Confirm CACM shows a topic/qrels pairing
        topic_select = page.locator("#topicSelect")
        expect(topic_select).not_to_have_value("")
        selected_text = topic_select.input_value()
        assert selected_text != "", "Topic select should have a value for CACM"

        # 5. Select a supported metric with fallback
        metric_select = page.locator("#metricSelect")
        expect(metric_select).to_have_count(1)
        # Try to select nDCG@10 or Recall@1000 if available
        options = metric_select.locator("option").all_text_contents()
        target = None
        for opt in options:
            if "nDCG@10" in opt:
                target = opt
                break
        if not target:
            for opt in options:
                if "Recall@1000" in opt or "R@1K" in opt:
                    target = opt
                    break
        if not target:
            for opt in options:
                if opt and opt != "Select a topic first":
                    target = opt
                    break
        assert target, "No metric options available"
        metric_select.select_option(label=target)

        # 6. Click Run Evaluation
        run_btn = page.locator("#runBtn")
        expect(run_btn).to_be_enabled(timeout=5000)
        run_btn.click()

        # 7. Wait for result: numeric score appears
        result_box = page.locator("#resultBox .result-box")
        # Wait up to 2 minutes for retrieval + evaluation (CACM is fast, but be generous)
        result_box.wait_for(state="visible", timeout=120000)

        # Should show completed with a score
        score_el = result_box.locator(".score")
        expect(score_el).to_be_visible(timeout=10000)
        score_text = score_el.text_content()
        assert score_text is not None and score_text != "N/A", f"Expected numeric score, got: {score_text}"
        try:
            float(score_text)
        except ValueError:
            pytest.fail(f"Score is not numeric: {score_text}")

        # 8. Verify run metadata appears
        meta = result_box.locator(".meta")
        meta_text = meta.text_content() or ""
        assert "Index:" in meta_text, "Missing index metadata"
        assert "Topics:" in meta_text, "Missing topics metadata"
        assert "Qrels:" in meta_text, "Missing qrels metadata"
        assert "Metric:" in meta_text, "Missing metric metadata"
        assert "Run file:" in meta_text, "Missing run file metadata"
        assert "Eval file:" in meta_text, "Missing eval file metadata"

        browser.close()
