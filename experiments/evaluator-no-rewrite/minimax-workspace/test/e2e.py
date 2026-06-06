"""End-to-end Playwright test for the Anserini Prebuilt Index Evaluator.

The test boots the app's Express server in a background process, opens
the page in a headless Chromium, and verifies the workflow described in
the PRD:

  * The catalog is loaded from the live Anserini prebuilt-index registry
    (not a hardcoded single-index stub).
  * CACM is selected/selectable and exposes a topics + qrels pairing.
  * nDCG@10 (or a supported fallback) is chosen.
  * Clicking Run Evaluation executes the Anserini fatjar underneath and
    produces a numeric score plus run metadata.
  * At least one catalog-only / non-selected index is visible in the
    registry-derived catalog.

The test deliberately fails the run if the page reports a hardcoded
or mocked catalog, because the page only knows about indexes returned
by `io.anserini.cli.PrebuiltIndexRegistry --list`.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
EXPECTED_CACM_NDCG = 0.4543
EXPECTED_CACM_MAP = 0.3123


def _free_port() -> int:
    s = socket.socket()
    s.bind((DEFAULT_HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_http(url: str, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(0.3)
    raise RuntimeError(f"server at {url} did not become ready: {last_err}")


def _start_server(jar: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["ANSERINI_JAR"] = str(jar)
    env["PORT"] = str(port)
    env["HOST"] = DEFAULT_HOST
    log_path = REPO_ROOT / "data" / "e2e-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w")
    proc = subprocess.Popen(
        ["node", "server.js"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    return proc


def _stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def _expect_run_finishes(page: Page, timeout_s: float = 180.0) -> dict:
    """Click Run Evaluation and wait for the score block to render."""
    run_button = page.locator("#runButton")
    run_button.click()
    score_locator = page.locator("#scoreValue")
    deadline = time.time() + timeout_s
    last_text = ""
    while time.time() < deadline:
        last_text = score_locator.inner_text().strip()
        if last_text and last_text not in {"—", "-", ""}:
            return {
                "score": last_text,
                "runFile": page.locator("#metaRunFile").inner_text(),
                "evalFile": page.locator("#metaEvalFile").inner_text(),
                "metric": page.locator("#metaMetric").inner_text(),
                "index": page.locator("#metaIndex").inner_text(),
                "topics": page.locator("#metaTopics").inner_text(),
                "qrels": page.locator("#metaQrels").inner_text(),
                "searchCmd": page.locator("#metaSearchCmd").inner_text(),
                "evalCmd": page.locator("#metaEvalCmd").inner_text(),
            }
        time.sleep(0.5)
    raise AssertionError(
        f"Run did not complete within {timeout_s}s; last score text was {last_text!r}"
    )


def _fetch_catalog(base_url: str) -> dict:
    import json

    with urllib.request.urlopen(f"{base_url}/api/catalog", timeout=30) as r:
        return json.load(r)


def test_app(jar: Path) -> None:
    port = _free_port()
    base_url = f"http://{DEFAULT_HOST}:{port}"
    server = _start_server(jar, port)
    try:
        print(f"[e2e] waiting for server at {base_url}…")
        _wait_for_http(f"{base_url}/api/health")
        print("[e2e] server is up")

        catalog = _fetch_catalog(base_url)
        inverted = catalog["indexes"]
        assert len(inverted) > 50, (
            f"Expected a populated Anserini prebuilt-index catalog, "
            f"got {len(inverted)} inverted indexes"
        )
        # Ensure the catalog comes from the real Anserini registry, not
        # a hand-maintained list of one or two entries.
        names = {idx["name"] for idx in inverted}
        assert "cacm" in names, "Expected `cacm` in the prebuilt-index catalog"
        assert "msmarco-v1-passage" in names, (
            "Expected `msmarco-v1-passage` in the prebuilt-index catalog"
        )
        # Pick another non-cacm, non-msmarco inverted index that is visible
        # in the catalog, just to prove the registry has more than the two
        # we explicitly named above.
        unexpected = [n for n in names if n not in {"cacm", "msmarco-v1-passage"}]
        assert unexpected, (
            "Expected the prebuilt-index catalog to contain indexes other than "
            "cacm and msmarco-v1-passage"
        )
        # Ensure pairings are derived from the live registry, not mocked.
        pairings = catalog["pairings"]
        assert any(p["index"] == "cacm" for p in pairings), (
            "Expected an evaluable CACM pairing"
        )
        assert any(not i["evaluable"] for i in inverted), (
            "Expected at least one catalog-only (non-evaluable) index to be visible"
        )
        # Sanity-check the Anserini-derived qrels set: the registry should
        # know about at least 50 qrels symbols from Qrels.java.
        assert len(catalog["qrels"]) >= 50, (
            f"Expected at least 50 qrels symbols from the Anserini fatjar, "
            f"got {len(catalog['qrels'])}"
        )

        with sync_playwright() as p:
            browser: Browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page: Page = context.new_page()

            print("[e2e] loading page…")
            page.goto(base_url, wait_until="domcontentloaded")

            # The status pill should flip to OK once the catalog is loaded.
            page.wait_for_selector("#statusPill.ok", timeout=30_000)
            print("[e2e] catalog status pill is OK")

            # Wait for the catalog list to populate; the CACM index should
            # be one of the entries and marked evaluable.
            page.wait_for_selector("#catalogList li", timeout=30_000)
            catalog_count = page.locator("#catalogCount").inner_text()
            print(f"[e2e] catalog shows {catalog_count} indexes")
            assert int(catalog_count) > 50, (
                f"Expected the in-page catalog to mirror the registry (>50), "
                f"got {catalog_count}"
            )

            # CACM is the default and should be auto-selected on load. The
            # dataset panel should already be visible.
            page.wait_for_selector("#datasetView:not([hidden])", timeout=15_000)
            assert "cacm" in page.locator("#datasetIndex").inner_text().lower(), (
                "Expected the default selection to be CACM"
            )
            topics = page.locator("#datasetTopics").inner_text()
            qrels = page.locator("#datasetQrels").inner_text()
            assert topics.strip(), "Expected the dataset panel to show topics"
            assert qrels.strip(), "Expected the dataset panel to show qrels"
            print(f"[e2e] default selection: index=cacm topics={topics} qrels={qrels}")

            # Confirm the metric selector lists nDCG@10 or a supported fallback.
            metric_options = [
                o.strip() for o in page.locator("#metricSelect option").all_inner_texts()
            ]
            print(f"[e2e] metric options: {metric_options}")
            preferred = "nDCG@10"
            if preferred not in metric_options:
                # Fall back to MAP, which the PRD explicitly permits.
                assert "MAP" in metric_options, (
                    "Expected nDCG@10 or MAP to be selectable for CACM"
                )
                preferred = "MAP"
            page.locator("#metricSelect").select_option(preferred)

            # Verify at least one catalog-only index is visible in the UI.
            # (It may be filtered out by default, so clear the filter and
            #  inspect the raw count.)
            page.locator("#catalogFilter").fill("")
            page.locator("#showCatalogOnly").check()
            time.sleep(0.2)
            catalog_only_count_text = page.locator("#catalogCount").inner_text()
            catalog_only_count = int(catalog_only_count_text)
            print(f"[e2e] catalog-only entries visible: {catalog_only_count}")
            assert catalog_only_count >= 1, (
                "Expected at least one catalog-only (non-evaluable) index to be "
                "visible in the registry-derived catalog"
            )
            # Switch back so the CACM run has access to the dataset panel.
            page.locator("#showCatalogOnly").uncheck()
            page.wait_for_selector("#datasetView:not([hidden])", timeout=5_000)

            # Click CACM again to make sure the UI handles re-selection.
            page.locator("#catalogList li[data-index='cacm']").click()

            # Now run the actual evaluation.
            print(f"[e2e] running evaluation with metric={preferred}…")
            result = _expect_run_finishes(page)
            print(f"[e2e] score={result['score']} metric={result['metric']}")
            print(f"[e2e] runFile={result['runFile']}")
            print(f"[e2e] evalFile={result['evalFile']}")

            # The score must be numeric. The PRD forbids hardcoded results.
            try:
                score_value = float(result["score"])
            except ValueError as e:
                raise AssertionError(
                    f"Expected a numeric score, got {result['score']!r}"
                ) from e

            if preferred == "nDCG@10":
                assert abs(score_value - EXPECTED_CACM_NDCG) < 1e-3, (
                    f"Expected CACM nDCG@10 ~= {EXPECTED_CACM_NDCG}, "
                    f"got {score_value}"
                )
            elif preferred == "MAP":
                assert abs(score_value - EXPECTED_CACM_MAP) < 1e-3, (
                    f"Expected CACM MAP ~= {EXPECTED_CACM_MAP}, "
                    f"got {score_value}"
                )

            # Run metadata must reference the chosen index, topics, qrels, and
            # metric, and must include real file paths.
            assert "cacm" in result["index"].lower()
            assert "cacm" in result["topics"].lower()
            assert "cacm" in result["qrels"].lower()
            assert result["metric"].lower().startswith(preferred.lower().split("@")[0])
            run_file_path = result["runFile"].split(" ")[0]
            assert run_file_path.endswith(".txt") and os.path.exists(run_file_path), (
                f"Run file path is missing on disk: {result['runFile']!r}"
            )
            assert result["evalFile"].endswith(".txt") and os.path.exists(result["evalFile"]), (
                f"Eval output path is missing on disk: {result['evalFile']!r}"
            )
            # The commands panel should show the actual fatjar invocations.
            assert "SearchCollection" in result["searchCmd"], (
                f"Search command does not mention SearchCollection: {result['searchCmd']!r}"
            )
            assert "TrecEval" in result["evalCmd"], (
                f"Eval command does not mention TrecEval: {result['evalCmd']!r}"
            )
            # The catalog of non-selected indexes should still be visible.
            assert int(catalog_count) > 1, (
                "Expected more than one index in the catalog sidebar"
            )

            browser.close()
        print("[e2e] PASS")
    finally:
        _stop_server(server)


def main() -> int:
    jar_env = os.environ.get("ANSERINI_JAR")
    if not jar_env:
        candidates = sorted(REPO_ROOT.glob("anserini-*-fatjar.jar"))
        if not candidates:
            print("ANSERINI_JAR is not set and no anserini-*-fatjar.jar in repo", file=sys.stderr)
            return 2
        jar_env = str(candidates[-1])
    jar = Path(jar_env)
    if not jar.exists():
        print(f"ANSERINI_JAR points to missing file: {jar}", file=sys.stderr)
        return 2
    try:
        test_app(jar)
    except (AssertionError, PlaywrightTimeoutError) as e:
        print(f"[e2e] FAIL: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
