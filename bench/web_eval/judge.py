from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from bench.config import load_project_env
from bench.web_eval.schemas import BrowserAction, EvidencePacket, FeatureCheck, FeatureJudgment, FeatureVerdict
from bench.web_eval.setup import PlannedSetupCommand, SetupCommandResult, commands_from_json


FEATURE_GENERATOR_SYSTEM = """You convert product requirements into browser-testable feature checks for web apps.
Return JSON only with key: features.
Each feature must have: id, title, description, acceptance, steps.
Use 3 to 8 high-value features unless asked otherwise.
Prefer functional outcomes over exact UI structure.
Steps should be generic evidence-gathering actions, not brittle CSS selectors.
Allowed actions: open, click, fill, press, select, wait_settle, wait_for_text, visible_text, snapshot, screenshot.
Always start each feature with open / and a short wait_settle unless a route is explicit in the PRD.
Use visible_text, snapshot, and screenshot to gather evidence.
Only include click/fill steps when the PRD clearly requires a user action.
"""


SETUP_SYSTEM = """You plan setup commands for evaluating an agent-built web app.
Use only the PRD, implementation README/manifests, and referenced local skill docs provided by the user.
Return JSON only with key: commands.
Each command item must have: command, cwd, reason.
Commands must be concrete single commands; do not use pipes, &&, ;, command substitution, heredocs, sudo, rm, mv, cp, chmod, chown, or git.
Prefer project-local install/setup scripts and standard dependency commands.
If a skill doc describes an installation workflow, translate it into concrete safe commands that the allowlisted runner can execute.
Follow the skill doc's completion criteria and verification steps; do not stop after a partial smoke check when the skill requires additional validation.
When a PRD or manifest names an install/setup skill, plan that install workflow before CLI/runtime usage checks. Do not rely only on inherited environment variables such as *_JAR unless the implementation README explicitly says the artifact is already present and the plan verifies the file path.
Do not invent dependency versions when the provided PRD, README, manifest, or skill docs do not specify one; "latest known" is not evidence. If docs say to discover the latest release from metadata, either use a pinned version from the implementation README or plan the documented metadata/download workflow instead of guessing.
Use cwd relative to the project root unless an absolute project path is necessary.
If no setup is needed, return an empty commands list.
"""


PLAN_SYSTEM = """You plan a short browser evidence-gathering flow for a web app feature.
Use ONLY the allowed actions and fields listed by the user.
Return JSON only with key: steps.
Use at most 6 steps.
Do not use brittle CSS selectors unless the evidence already exposes a stable selector.
Prefer text, role+name, placeholder, label, select label/value, wait_settle, visible_text, snapshot, and screenshot.
If the existing evidence is already enough to judge the feature, return an empty steps list.
The goal is to gather evidence, not to decide pass/fail.
"""


JUDGE_SYSTEM = """You are a strict functional evaluator for web applications.
Judge whether the feature requirement is satisfied based ONLY on the evidence packet.
Different UI layouts are valid if behavior matches the acceptance criteria.
Return JSON only with keys: verdict, confidence, reason, evidence_used.
verdict must be one of: pass, fail, uncertain.
confidence is a float from 0 to 1.
reason is one short sentence.
evidence_used is a list of short strings naming evidence fields you relied on.
If evidence is insufficient, use uncertain."""


class JudgeClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        dry_run: bool = False,
    ):
        env = load_project_env()
        self.model = model or env.get("WEB_EVAL_JUDGE_MODEL") or env.get("OPENAI_MODEL") or "gpt-4o-mini"
        self.api_base = (api_base or env.get("WEB_EVAL_JUDGE_API_BASE") or env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or env.get("WEB_EVAL_JUDGE_API_KEY") or env.get("OPENAI_API_KEY")
        self.dry_run = dry_run



    def plan_setup_commands(
        self,
        setup_context: dict[str, Any],
        *,
        project_path,
        max_commands: int = 12,
    ) -> list[PlannedSetupCommand]:
        if self.dry_run or not self.api_key:
            return []
        payload = {
            "setup_context": setup_context,
            "allowed_command_families": [
                "npm install",
                "npm ci",
                "npm run <setup-like-script>",
                "pip install -r <project-file>",
                "python -m pip install -r <project-file>",
                "python/node/bash/sh <project-local setup/install script>",
                "curl or wget downloads with explicit project-local output path",
                "environment assignment such as NAME=value or export NAME=value",
                "safe stdout redirection to a project-local file",
                "grep -q PATTERN FILE verification against a project-local file",
                "npx playwright install [chromium|firefox|webkit]",
                "java/test smoke-check commands",
            ],
            "max_commands": max_commands,
        }
        raw = self._chat(
            "Plan setup commands needed before browser evaluation.\n\n"
            f"{json.dumps(payload, indent=2)}",
            system=SETUP_SYSTEM,
        )
        parsed = _parse_json_object(raw)
        return commands_from_json(parsed.get("commands"), project_path)[:max_commands]

    def generate_features(self, prd_context: str, *, max_features: int = 8) -> list[FeatureCheck]:
        if self.dry_run:
            return []
        if not self.api_key:
            raise RuntimeError(
                "Judge API key missing. Set OPENAI_API_KEY or WEB_EVAL_JUDGE_API_KEY to generate features."
            )
        prompt = (
            f"Create up to {max_features} feature checks from this PRD. "
            "Focus on externally observable app behavior and success criteria.\n\n"
            f"{prd_context}"
        )
        raw = self._chat(prompt, system=FEATURE_GENERATOR_SYSTEM)
        parsed = _parse_json_object(raw)
        return _features_from_json(parsed, max_features=max_features)

    def plan_evidence_steps(
        self,
        feature: FeatureCheck,
        evidence: EvidencePacket,
        prd_context: str | None,
        *,
        max_steps: int = 6,
    ) -> list[BrowserAction]:
        if self.dry_run:
            return []
        if not self.api_key:
            return []
        payload = {
            "feature": feature.to_dict(),
            "current_evidence": evidence.compact_dict(max_text=1800, max_aria=2500),
            "prd_context": _truncate(prd_context, 2500),
            "allowed_actions": {
                "open": ["path", "url"],
                "click": ["text", "exact", "role", "name", "selector"],
                "fill": ["text", "placeholder", "label", "selector"],
                "press": ["key"],
                "select": ["selector", "value", "label", "option"],
                "wait_settle": ["ms"],
                "wait_for_text": ["text", "selector", "timeout", "exact"],
                "visible_text": ["key", "selector", "max_chars"],
                "snapshot": [],
                "screenshot": ["name", "fullPage"],
            },
        }
        raw = self._chat(
            "Plan additional browser actions to collect enough evidence for this feature.\n\n"
            f"{json.dumps(payload, indent=2)}",
            system=PLAN_SYSTEM,
        )
        parsed = _parse_json_object(raw)
        return _actions_from_json(parsed.get("steps"), max_steps=max_steps)

    def judge_feature(
        self,
        feature: FeatureCheck,
        evidence: EvidencePacket,
        prd_context: str | None,
        setup_context: dict[str, Any] | None = None,
        setup_results: list[SetupCommandResult] | None = None,
    ) -> FeatureJudgment:
        if evidence.error and not evidence.visible_text and not evidence.aria_snapshot:
            return FeatureJudgment(
                feature_id=feature.id,
                verdict="uncertain",
                confidence=0.2,
                reason=f"Browser evidence collection failed: {evidence.error}",
                evidence_used=["error"],
            )
        if self.dry_run:
            verdict: FeatureVerdict = "pass" if not evidence.error else "uncertain"
            return FeatureJudgment(
                feature_id=feature.id,
                verdict=verdict,
                confidence=0.5,
                reason="Dry-run mode: skipped LLM judge.",
                evidence_used=["dry_run"],
            )
        if not self.api_key:
            raise RuntimeError(
                "Judge API key missing. Set OPENAI_API_KEY or WEB_EVAL_JUDGE_API_KEY, or pass --dry-run."
            )
        payload = {
            "feature": feature.to_dict(),
            "evidence": evidence.compact_dict(),
            "prd_context": prd_context,
            "setup_context": setup_context,
            "setup_results": [result.__dict__ for result in setup_results] if setup_results else [],
        }
        user_prompt = (
            "Evaluate this feature against the evidence.\n\n"
            f"{json.dumps(payload, indent=2)}"
        )
        raw = self._chat(user_prompt)
        parsed = _parse_judge_json(raw)
        return FeatureJudgment(
            feature_id=feature.id,
            verdict=parsed["verdict"],
            confidence=float(parsed.get("confidence", 0.5)),
            reason=str(parsed.get("reason", "")),
            evidence_used=[str(x) for x in parsed.get("evidence_used", [])],
            raw_response=raw,
        )

    def _chat(self, user_prompt: str, *, system: str = JUDGE_SYSTEM) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Judge API error ({exc.code}): {detail}") from exc
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Judge API returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise RuntimeError("Judge API returned empty content.")
        return str(content)


def _parse_judge_json(raw: str) -> dict[str, Any]:
    parsed = _parse_json_object(raw)
    verdict = str(parsed.get("verdict", "uncertain")).lower()
    if verdict not in {"pass", "fail", "uncertain"}:
        verdict = "uncertain"
    parsed["verdict"] = verdict
    return parsed


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from judge model.")
    return parsed


def _features_from_json(parsed: dict[str, Any], *, max_features: int) -> list[FeatureCheck]:
    raw_features = parsed.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("Feature generator response must contain a features list.")
    features: list[FeatureCheck] = []
    for item in raw_features[:max_features]:
        if not isinstance(item, dict):
            continue
        feature_id = _slug(str(item.get("id") or item.get("title") or f"feature-{len(features) + 1}"))
        title = str(item.get("title") or feature_id)
        description = str(item.get("description") or title)
        acceptance = str(item.get("acceptance") or description)
        steps = _actions_from_json(item.get("steps"), max_steps=12)
        if not steps:
            steps = [
                BrowserAction("open", {"path": "/"}),
                BrowserAction("wait_settle", {"ms": 1500}),
                BrowserAction("snapshot"),
                BrowserAction("screenshot", {"name": feature_id}),
            ]
        features.append(FeatureCheck(feature_id, title, description, acceptance, steps))
    if not features:
        raise ValueError("Feature generator returned no usable features.")
    return features


def _actions_from_json(raw_steps: Any, *, max_steps: int) -> list[BrowserAction]:
    allowed = {
        "open",
        "click",
        "fill",
        "press",
        "select",
        "wait_settle",
        "wait_for_text",
        "visible_text",
        "snapshot",
        "screenshot",
    }
    actions: list[BrowserAction] = []
    if not isinstance(raw_steps, list):
        return actions
    for raw in raw_steps[:max_steps]:
        if isinstance(raw, str):
            action = raw
            params: dict[str, Any] = {}
        elif isinstance(raw, dict):
            action = str(raw.get("action") or "")
            params = {str(k): v for k, v in raw.items() if k != "action"}
        else:
            continue
        if action not in allowed:
            continue
        actions.append(BrowserAction(action, params))
    return actions


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "feature"


def _truncate(value: str | None, limit: int) -> str | None:
    if not value or len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def compute_correctness(judgments: list[FeatureJudgment]) -> tuple[int, int, int, float]:
    total = len(judgments)
    passed = sum(1 for j in judgments if j.verdict == "pass")
    failed = sum(1 for j in judgments if j.verdict == "fail")
    uncertain = sum(1 for j in judgments if j.verdict == "uncertain")
    pct = (passed / total * 100.0) if total else 0.0
    return passed, failed, uncertain, pct
