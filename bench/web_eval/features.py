from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from bench.web_eval.schemas import BrowserAction, FeatureCheck


def load_features(path: Path) -> list[FeatureCheck]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    elif path.suffix == ".json":
        data = json.loads(raw)
    else:
        raise ValueError(f"Unsupported features file type: {path.suffix}")

    if not isinstance(data, dict):
        raise ValueError("Features file must be a mapping with a `features` list.")
    items = data.get("features")
    if not isinstance(items, list) or not items:
        raise ValueError("Features file must contain a non-empty `features` list.")

    checks: list[FeatureCheck] = []
    for item in items:
        checks.append(_parse_feature(item))
    return checks


def load_app_profile(path: Path | None, features_data: dict[str, Any] | None) -> dict[str, Any] | None:
    if path and path.exists():
        raw = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
        if isinstance(data, dict) and "app" in data:
            return data["app"]
        if isinstance(data, dict):
            return data
    if features_data and isinstance(features_data.get("app"), dict):
        return features_data["app"]
    return None


def load_features_file(path: Path) -> tuple[list[FeatureCheck], dict[str, Any] | None]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Features file must be a mapping.")
    app = load_app_profile(None, data)
    return load_features(path), app


def _parse_feature(item: Any) -> FeatureCheck:
    if not isinstance(item, dict):
        raise ValueError("Each feature must be a mapping.")
    feature_id = item.get("id")
    title = item.get("title")
    if not feature_id or not title:
        raise ValueError("Each feature requires `id` and `title`.")
    description = item.get("description", title)
    acceptance = item.get("acceptance", description)
    steps_raw = item.get("steps", [])
    steps: list[BrowserAction] = []
    if isinstance(steps_raw, list):
        for step in steps_raw:
            if isinstance(step, str):
                steps.append(BrowserAction(action=step))
            elif isinstance(step, dict):
                action = step.get("action")
                if not action:
                    raise ValueError(f"Feature {feature_id} step missing action.")
                params = {k: v for k, v in step.items() if k != "action"}
                steps.append(BrowserAction(action=str(action), params=params))
    return FeatureCheck(
        id=str(feature_id),
        title=str(title),
        description=str(description),
        acceptance=str(acceptance),
        steps=steps,
    )


def write_features(path: Path, features: list[FeatureCheck], app: dict[str, Any] | None = None) -> None:
    data: dict[str, Any] = {"features": [feature.to_dict() for feature in features]}
    if app:
        data["app"] = app
    if path.suffix in {".yaml", ".yml"}:
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
