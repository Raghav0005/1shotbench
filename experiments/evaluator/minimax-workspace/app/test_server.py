"""Unit tests for the Flask server's pure helpers.

These tests do not require the Anserini fatjar or Java — they exercise
the metric-translation and pairing-normalization logic only.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from anywhere
WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "app"))

import server  # noqa: E402
from server import (  # noqa: E402
    Pairing,
    TRANSLATABLE_METRICS,
    _expected_score_for,
    _metric_args_for,
    _serialize_metrics,
    metrics_for_pairing,
    metric_args,
    normalize_metric_label,
)


def test_metric_args_user_friendly():
    assert metric_args("nDCG@10") == "-c -m ndcg_cut.10"
    assert metric_args("Recall@1000") == "-c -m recall.1000"
    assert metric_args("MAP") == "-c -m map"
    assert metric_args("P.30") == "-c -m P.30"


def test_metric_args_passthrough():
    assert metric_args("-c -m ndcg_cut.5") == "-c -m ndcg_cut.5"


def test_metric_args_unknown():
    assert metric_args("not-a-real-metric") is None


def test_normalize_metric_label():
    assert normalize_metric_label("R@1K") == "Recall@1000"
    assert normalize_metric_label("nDCG@10") == "nDCG@10"
    assert normalize_metric_label("MRR@10") == "MRR@10"


def test_serialize_metrics_renames_keys():
    metrics = {
        "R@1K": {"args": "-c -m recall.1000", "expected": 0.85},
        "nDCG@10": {"args": "-c -m ndcg_cut.10", "expected": 0.50},
    }
    out = _serialize_metrics(metrics)
    assert "Recall@1000" in out
    assert "R@1K" not in out
    assert out["Recall@1000"]["expected"] == 0.85


def _make_pairing(metrics: dict[str, dict]) -> Pairing:
    return Pairing(
        index="cacm",
        topic_key="cacm",
        eval_key="cacm",
        metrics=metrics,
    )


def test_metrics_for_pairing_adds_modern_metrics():
    pairing = _make_pairing(
        {
            "MAP": {"args": "-c -m map", "expected": 0.3},
            "P30": {"args": "-c -m P.30", "expected": 0.2},
        }
    )
    options = metrics_for_pairing(pairing)
    labels = [o["label"] for o in options]
    # YAML-declared metrics come first.
    assert labels[0] == "MAP"
    assert labels[1] == "P30"
    # Modern metrics always added.
    assert "nDCG@10" in labels
    assert "Recall@1000" in labels
    # Each option is well-formed.
    for opt in options:
        assert "args" in opt
        assert opt["args"].startswith("-c ")


def test_metrics_for_pairing_dedupes_existing_modern():
    pairing = _make_pairing(
        {
            "nDCG@10": {"args": "-c -m ndcg_cut.10", "expected": 0.5},
        }
    )
    options = metrics_for_pairing(pairing)
    ndcg = [o for o in options if o["label"] == "nDCG@10"]
    assert len(ndcg) == 1
    # The YAML entry wins over the standard one (no duplicate).
    assert ndcg[0]["args"] == "-c -m ndcg_cut.10"
    assert ndcg[0]["expected"] == 0.5
    # The other standard one is still added.
    assert any(o["label"] == "Recall@1000" for o in options)


def test_metric_args_for_uses_user_facing_label():
    pairing = _make_pairing(
        {
            "R@1K": {"args": "-c -m recall.1000", "expected": 0.85},
        }
    )
    args, err = _metric_args_for(pairing, "Recall@1000")
    assert err is None
    assert args == "-c -m recall.1000"


def test_metric_args_for_uses_yaml_modern():
    pairing = _make_pairing(
        {
            "nDCG@10": {"args": "-c -m ndcg_cut.10", "expected": 0.5},
        }
    )
    args, err = _metric_args_for(pairing, "nDCG@10")
    assert err is None
    assert args == "-c -m ndcg_cut.10"


def test_metric_args_for_uses_standard_translation():
    pairing = _make_pairing(
        {
            "MAP": {"args": "-c -m map", "expected": 0.3},
        }
    )
    args, err = _metric_args_for(pairing, "nDCG@10")
    assert err is None
    assert args == "-c -m ndcg_cut.10"


def test_metric_args_for_unknown_metric():
    pairing = _make_pairing({})
    args, err = _metric_args_for(pairing, "MAP@9999")
    assert args is None
    assert err is not None and "MAP@9999" in err


def test_expected_score_for_uses_user_facing_label():
    pairing = _make_pairing(
        {
            "R@1K": {"args": "-c -m recall.1000", "expected": 0.85},
        }
    )
    assert _expected_score_for(pairing, "Recall@1000") == 0.85


def test_translatable_metrics_contains_required():
    # PRD requirement: the metric selector must include nDCG@10 and
    # Recall@1000.
    assert "nDCG@10" in TRANSLATABLE_METRICS
    assert "Recall@1000" in TRANSLATABLE_METRICS


if __name__ == "__main__":
    test_funcs = [
        v for k, v in sorted(globals().items()) if k.startswith("test_")
    ]
    failures = 0
    for fn in test_funcs:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    print(f"\nAll {len(test_funcs)} tests passed")
