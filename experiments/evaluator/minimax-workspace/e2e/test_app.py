"""End-to-end browser test for the Anserini Prebuilt Index Evaluator.

This test launches a real Chromium instance, opens the running app,
selects the CACM dataset, runs an end-to-end evaluation through the
UI, and asserts that the score, the run metadata, and the surrounding
catalog all come from the live Anserini fatjar (not from a mocked UI).

The test must fail if the app only renders mocked catalog data or
mocked evaluation results, so we assert that:

* the catalog list contains more than one entry (registry-derived),
* at least one catalog-only entry is visible,
* the CACM pairing is detected and offered,
* nDCG@10 (or a clean fallback) is available as a metric,
* clicking Run Evaluation triggers a real backend round-trip and
  produces a numeric score and run metadata that include the actual
  run/eval artifact paths.
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import (
    Page,
    expect,
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).resolve().parent.parent
E2E_DIR = WORKSPACE / "e2e"
SCREENSHOT_DIR = E2E_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5555")
SCREENSHOT_DIR_REL = SCREENSHOT_DIR.relative_to(WORKSPACE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def wait_for_server(base_url: str, timeout_s: int = 60) -> None:
    """Block until the backend reports a healthy status."""

    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    health_url = f"{base_url}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=5) as r:
                if r.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.5)
    raise RuntimeError(
        f"server at {base_url} did not become healthy in {timeout_s}s: {last_err}"
    )


def find_metric(page: Page, candidates: list[str]) -> str | None:
    """Return the first metric option label from ``candidates`` that is
    available in the metric selector."""

    options = page.eval_on_selector_all(
        "#metric-select option",
        "els => els.map(e => e.value)",
    )
    for c in candidates:
        if c in options:
            return c
    return None


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def run_test() -> None:
    wait_for_server(BASE_URL, timeout_s=120)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.set_default_timeout(30_000)
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(f"{msg.type}: {msg.text}")
            if msg.type in {"error", "warning"}
            else None,
        )

        # 1. Open the app and wait for the catalog to render.
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#catalog-list li[data-name]", timeout=30_000)
        page.wait_for_function(
            "() => document.getElementById('meta-status').textContent.trim() === 'ready'",
            timeout=30_000,
        )
        page.screenshot(
            path=str(SCREENSHOT_DIR / "01-loaded.png"), full_page=True
        )

        # 2. The catalog must contain more than a single hardcoded CACM
        #    option. We assert the registry-derived catalog exposes a
        #    reasonable number of prebuilt Lucene inverted indexes.
        catalog_items = page.eval_on_selector_all(
            "#catalog-list li[data-name]",
            "els => els.map(e => e.getAttribute('data-name'))",
        )
        assert len(catalog_items) > 5, (
            f"expected the registry-derived catalog to expose many "
            f"indexes, got {len(catalog_items)}: {catalog_items[:10]}"
        )

        # 3. At least one catalog-only / non-selected entry must be
        #    visible (it should be marked .disabled).
        disabled_count = page.eval_on_selector_all(
            "#catalog-list li.disabled", "els => els.length"
        )
        assert disabled_count >= 1, (
            "expected at least one catalog-only (non-evaluable) index to "
            "be visible in the registry-derived catalog"
        )

        # 4. CACM must be selectable. We click the CACM row.
        cacm_row = page.locator('#catalog-list li[data-name="cacm"]')
        cacm_row.wait_for(state="visible", timeout=15_000)
        # CACM should carry the .evaluable class (i.e. be selectable).
        is_evaluable = cacm_row.evaluate(
            "el => !el.classList.contains('disabled')"
        )
        assert is_evaluable, "CACM should be marked evaluable in the catalog"

        cacm_row.click()
        page.wait_for_selector("#eval-section:not([hidden])", timeout=15_000)
        page.screenshot(
            path=str(SCREENSHOT_DIR / "02-cacm-selected.png"), full_page=True
        )

        # 5. The eval form must show a topic/qrels pairing for CACM.
        #    The qrels input is the auto-discovered evaluation source.
        qrels_value = page.eval_on_selector("#qrels-input", "el => el.value")
        assert qrels_value.strip(), (
            "CACM must display a qrels/evaluation source after selection"
        )

        # 6. The metric selector must offer nDCG@10 or Recall@1000.
        #    If neither is available (unlikely for CACM), we fall back
        #    to whatever the first metric is — but we record the choice
        #    so the test can still verify the workflow.
        page.wait_for_function(
            "() => document.querySelectorAll('#metric-select option').length > 0",
            timeout=15_000,
        )
        chosen_metric = find_metric(page, ["nDCG@10", "Recall@1000"])
        if chosen_metric is None:
            chosen_metric = page.eval_on_selector(
                "#metric-select option", "el => el.value"
            )
        assert chosen_metric, "metric selector should have at least one option"
        page.select_option("#metric-select", chosen_metric)

        # 7. Click Run Evaluation and wait for the result to render.
        page.click("#run-btn")
        # The status pill shows a spinner then "Done in …s".
        try:
            page.wait_for_function(
                "() => { const t = document.getElementById('run-status').textContent; "
                "return t && t.includes('Done in'); }",
                timeout=180_000,
            )
        except PlaywrightTimeoutError:
            page.screenshot(
                path=str(SCREENSHOT_DIR / "03-timeout.png"), full_page=True
            )
            status = page.eval_on_selector(
                "#run-status", "el => el.textContent"
            )
            raise AssertionError(
                f"evaluation did not finish in time; status was {status!r}"
            )
        page.screenshot(
            path=str(SCREENSHOT_DIR / "03-result.png"), full_page=True
        )

        # 8. A numeric score must be visible.
        score_text = page.locator('[data-testid="score-value"]').text_content()
        assert score_text and score_text.strip() not in {"—", "n/a", ""}, (
            f"expected a numeric score in the result card, got {score_text!r}"
        )
        score_match = re.search(r"-?\d+(?:\.\d+)?", score_text)
        assert score_match, f"score does not look numeric: {score_text!r}"
        score_value = float(score_match.group(0))
        assert score_value > 0, (
            f"expected a non-zero positive score from a real evaluation, "
            f"got {score_value}"
        )

        # 9. Run metadata must include the index, topics, qrels, metric,
        #    and the artifact paths.
        meta_index = page.locator('[data-testid="meta-index"]').text_content() or ""
        meta_topics = page.locator('[data-testid="meta-topics"]').text_content() or ""
        meta_qrels = page.locator('[data-testid="meta-qrels"]').text_content() or ""
        meta_metric = page.locator('[data-testid="meta-metric"]').text_content() or ""
        meta_run_file = page.locator('[data-testid="meta-run-file"]').text_content() or ""
        meta_eval_file = page.locator('[data-testid="meta-eval-file"]').text_content() or ""

        for label, value in (
            ("index", meta_index),
            ("topics", meta_topics),
            ("qrels", meta_qrels),
            ("metric", meta_metric),
        ):
            assert value.strip() and value.strip() != "—", (
                f"{label} metadata missing from the result card "
                f"(value={value!r})"
            )

        # The run file path must look like an absolute path on disk and
        # the eval file path must likewise. The run-file preview also
        # has to be non-empty (TREC format starts with "<qid> Q0 ...").
        run_path_match = re.search(r"(/[\w./+@-]+\.txt)", meta_run_file)
        eval_path_match = re.search(r"(/[\w./+@-]+\.txt)", meta_eval_file)
        assert run_path_match, f"run file path missing: {meta_run_file!r}"
        assert eval_path_match, f"eval file path missing: {meta_eval_file!r}"
        run_path = Path(run_path_match.group(1))
        eval_path = Path(eval_path_match.group(1))
        assert run_path.is_file() and run_path.stat().st_size > 0, (
            f"run file should exist and be non-empty: {run_path}"
        )
        assert eval_path.is_file() and eval_path.stat().st_size > 0, (
            f"eval file should exist and be non-empty: {eval_path}"
        )

        # 10. Make sure the run file actually contains TREC-formatted
        #     lines — this catches any silent mocking of the run
        #     artifact. A real CACM BM25 retrieval produces tens of
        #     thousands of scored docs across the 64 topics, so a
        #     suspiciously small file would also be a red flag.
        run_text = run_path.read_text(encoding="utf-8")
        run_lines = run_text.splitlines()
        assert len(run_lines) > 1000, (
            f"run file should contain thousands of TREC results for a "
            f"real retrieval, got only {len(run_lines)} lines"
        )
        run_first_line = run_lines[0]
        assert re.match(r"^\d+\s+Q0\s+\S+", run_first_line), (
            f"run file does not contain TREC-formatted results: "
            f"first line was {run_first_line!r}"
        )
        eval_text = eval_path.read_text(encoding="utf-8")
        assert eval_text.strip(), "eval file should not be empty"
        assert "all" in eval_text, (
            "eval file should contain a trec_eval summary line for 'all'"
        )
        # The eval file must contain a measurement row with a numeric
        # value. The CACM + nDCG@10 smoke-test value is 0.4543, so we
        # also assert the value lives in a reasonable range to catch
        # completely fabricated scores.
        eval_value_match = re.search(
            r"(?:ndcg_cut_10|map|recall_1000|P_30|recip_rank)\s+all\s+(-?\d+\.\d+)",
            eval_text,
        )
        assert eval_value_match, (
            f"eval file does not contain a recognizable trec_eval line: "
            f"{eval_text!r}"
        )
        eval_value = float(eval_value_match.group(1))
        assert 0.0 <= eval_value <= 1.0, (
            f"trec_eval value out of [0,1] range: {eval_value}"
        )
        if chosen_metric == "nDCG@10":
            # Sanity check: the CACM BM25 nDCG@10 value is 0.4543.
            assert 0.4 <= eval_value <= 0.5, (
                f"CACM nDCG@10 expected ~0.4543, got {eval_value}"
            )

        # 11. Browse to a non-default index to confirm the registry list
        #     is actually consumed by the UI. We use the search filter
        #     to ensure the registry really contains more than CACM.
        page.fill("#catalog-filter", "msmarco-v1-passage")
        page.wait_for_timeout(300)
        filtered_items = page.eval_on_selector_all(
            "#catalog-list li[data-name]",
            "els => els.map(e => e.getAttribute('data-name'))",
        )
        assert any("msmarco-v1-passage" in n for n in filtered_items), (
            "filter should reveal additional registry-derived indexes"
        )
        page.screenshot(
            path=str(SCREENSHOT_DIR / "04-filtered.png"), full_page=True
        )
        page.fill("#catalog-filter", "")

        # 12. Take a final summary screenshot.
        page.screenshot(
            path=str(SCREENSHOT_DIR / "05-final.png"), full_page=True
        )

        # 13. Save score for at-a-glance summary in the test logs.
        print(
            f"\nE2E summary:\n"
            f"  base url        : {BASE_URL}\n"
            f"  catalog items   : {len(catalog_items)}\n"
            f"  catalog-only    : {disabled_count}\n"
            f"  selected index  : cacm\n"
            f"  topics          : {meta_topics.strip()}\n"
            f"  qrels           : {meta_qrels.strip()}\n"
            f"  metric          : {meta_metric.strip()}\n"
            f"  score           : {score_value}\n"
            f"  run file        : {run_path}\n"
            f"  eval file       : {eval_path}\n"
            f"  screenshots     : {SCREENSHOT_DIR_REL}\n"
        )

        if console_errors:
            print("\nConsole messages from the page (warnings/errors):")
            for line in console_errors:
                print(f"  {line}")

        browser.close()


if __name__ == "__main__":
    try:
        run_test()
    except AssertionError:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"e2e test crashed: {exc}", file=sys.stderr)
        raise
    print("e2e test PASSED")
