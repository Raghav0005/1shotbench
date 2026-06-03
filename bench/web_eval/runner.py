from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.config import ROOT_DIR, load_project_env
from bench.web_eval.features import load_features_file, write_features
from bench.web_eval.judge import JudgeClient, compute_correctness
from bench.web_eval.prd import load_prd_context
from bench.web_eval.profile import AppServer, resolve_app_profile
from bench.web_eval.report import write_artifacts
from bench.web_eval.schemas import BrowserAction, EvidencePacket, FeatureCheck, FeatureJudgment, WebEvalSummary
from bench.web_eval.setup import collect_setup_context, run_project_setup


EVALS_DIR = ROOT_DIR / "evals"
WEB_EVAL_DIR = Path(__file__).resolve().parent
BROWSER_SCRIPT = WEB_EVAL_DIR / "browser.mjs"


@dataclass
class WebEvalOptions:
    project_path: Path
    features_path: Path | None = None
    prd_path: Path | None = None
    base_url: str | None = None
    profile_path: Path | None = None
    label: str = "web-eval"
    eval_id: str | None = None
    no_start: bool = False
    dry_run: bool = False
    judge_model: str | None = None
    max_generated_features: int = 8
    setup_mode: str = "auto"
    agentic_evidence: bool = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


class WebEvalRunner:
    def __init__(self, root_dir: Path = ROOT_DIR):
        self.root_dir = root_dir

    def preflight(self) -> list[str]:
        errors: list[str] = []
        if not BROWSER_SCRIPT.exists():
            errors.append(f"Missing browser script: {BROWSER_SCRIPT}")
        node_modules = WEB_EVAL_DIR / "node_modules"
        if not node_modules.exists():
            errors.append(
                "Playwright layer not installed. Run: "
                f"cd {WEB_EVAL_DIR} && npm install && npx playwright install chromium"
            )
        return errors

    def run(self, options: WebEvalOptions) -> WebEvalSummary:
        errors = self.preflight()
        if errors:
            raise RuntimeError("\n".join(errors))

        project_path = options.project_path.resolve()
        if not project_path.exists():
            raise FileNotFoundError(f"Project path not found: {project_path}")

        eval_id = options.eval_id or _make_eval_id()
        output_dir = EVALS_DIR / eval_id
        output_dir.mkdir(parents=True, exist_ok=True)

        prd_context = load_prd_context(options.prd_path)
        judge = JudgeClient(model=options.judge_model, dry_run=options.dry_run)
        app_data = None
        generated_features = False
        if options.features_path:
            features_path = options.features_path.resolve()
            features, app_data = load_features_file(features_path)
        else:
            if not prd_context:
                raise ValueError("Pass --features, or pass --prd so features can be generated from the PRD.")
            features = judge.generate_features(prd_context, max_features=options.max_generated_features)
            features_path = output_dir / "generated-features.yaml"
            write_features(features_path, features)
            generated_features = True

        profile_path = options.profile_path
        profile_data = None
        if profile_path and profile_path.exists():
            import yaml

            raw = profile_path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(raw)
            profile_data = loaded.get("app", loaded) if isinstance(loaded, dict) else None
        elif app_data:
            profile_data = app_data

        setup_context = collect_setup_context(project_path, options.prd_path)
        planned_setup_commands = judge.plan_setup_commands(setup_context, project_path=project_path)
        setup_results = run_project_setup(
            project_path,
            output_dir,
            mode=options.setup_mode,
            planned_commands=planned_setup_commands or None,
            setup_context=setup_context,
        )

        profile = resolve_app_profile(
            project_path,
            base_url=options.base_url,
            profile_data=profile_data,
            no_start=options.no_start,
        )

        started_at = _now_iso()
        server = AppServer(profile, project_path)
        load_project_env()
        try:
            startup_error: str | None = None
            if not options.no_start and profile.start_command:
                try:
                    server.start()
                except Exception as exc:
                    startup_error = str(exc)

            if startup_error:
                evidence_by_feature, judgments = _startup_failure_results(features, startup_error)
                notes = _build_summary_notes(setup_results, startup_error=startup_error)
                summary = self._build_summary(
                    eval_id=eval_id,
                    options=options,
                    project_path=project_path,
                    features_path=features_path,
                    profile=profile,
                    judge=judge,
                    judgments=judgments,
                    started_at=started_at,
                    notes=notes,
                )
                metadata = self._run_metadata(
                    project_path=project_path,
                    features_path=features_path,
                    generated_features=generated_features,
                    options=options,
                    profile=profile,
                    planned_setup_commands=planned_setup_commands,
                    startup_error=startup_error,
                )
                self._write_run_artifacts(
                    output_dir=output_dir,
                    summary=summary,
                    evidence_by_feature=evidence_by_feature,
                    judgments=judgments,
                    metadata=metadata,
                )
                return summary

            evidence_by_feature: dict[str, EvidencePacket] = {}
            judgments = []
            for feature in features:
                evidence = self._collect_evidence(
                    feature=feature,
                    profile=profile,
                    output_dir=output_dir,
                    suffix="scripted",
                )
                if options.agentic_evidence:
                    try:
                        planned_steps = judge.plan_evidence_steps(feature, evidence, prd_context)
                    except Exception as exc:
                        planned_steps = []
                        evidence.checks["agentic_plan_error"] = str(exc)
                    if planned_steps:
                        planned_feature = FeatureCheck(
                            id=feature.id,
                            title=feature.title,
                            description=feature.description,
                            acceptance=feature.acceptance,
                            steps=[*feature.steps, *planned_steps],
                        )
                        planned_evidence = self._collect_evidence(
                            feature=planned_feature,
                            profile=profile,
                            output_dir=output_dir,
                            suffix="agentic",
                        )
                        evidence = _merge_evidence(evidence, planned_evidence, planned_steps)
                evidence_by_feature[feature.id] = evidence
                try:
                    judgment = judge.judge_feature(
                        feature,
                        evidence,
                        prd_context,
                        setup_context=setup_context,
                        setup_results=setup_results,
                    )
                except Exception as exc:
                    judgment = FeatureJudgment(
                        feature_id=feature.id,
                        verdict="uncertain",
                        confidence=0.0,
                        reason=f"Judge call failed: {exc}",
                        evidence_used=["judge_error"],
                    )
                judgments.append(judgment)

            notes = _build_summary_notes(setup_results)
            summary = self._build_summary(
                eval_id=eval_id,
                options=options,
                project_path=project_path,
                features_path=features_path,
                profile=profile,
                judge=judge,
                judgments=judgments,
                started_at=started_at,
                notes=notes,
            )
            metadata = self._run_metadata(
                project_path=project_path,
                features_path=features_path,
                generated_features=generated_features,
                options=options,
                profile=profile,
                planned_setup_commands=planned_setup_commands,
                startup_error=None,
            )
            self._write_run_artifacts(
                output_dir=output_dir,
                summary=summary,
                evidence_by_feature=evidence_by_feature,
                judgments=judgments,
                metadata=metadata,
            )
            return summary
        finally:
            server.stop()

    def _build_summary(
        self,
        *,
        eval_id: str,
        options: WebEvalOptions,
        project_path: Path,
        features_path: Path,
        profile,
        judge: JudgeClient,
        judgments: list[FeatureJudgment],
        started_at: str,
        notes: str | None,
    ) -> WebEvalSummary:
        passed, failed, uncertain, pct = compute_correctness(judgments)
        return WebEvalSummary(
            eval_id=eval_id,
            label=options.label,
            started_at=started_at,
            ended_at=_now_iso(),
            project_path=str(project_path),
            features_path=str(features_path),
            prd_path=str(options.prd_path) if options.prd_path else None,
            base_url=profile.base_url,
            total_features=len(judgments),
            passed=passed,
            failed=failed,
            uncertain=uncertain,
            correctness_pct=pct,
            judgments=judgments,
            git_commit=_git_commit(self.root_dir),
            judge_model=None if options.dry_run else judge.model,
            notes=notes,
        )

    def _run_metadata(
        self,
        *,
        project_path: Path,
        features_path: Path,
        generated_features: bool,
        options: WebEvalOptions,
        profile,
        planned_setup_commands,
        startup_error: str | None,
    ) -> dict[str, Any]:
        return {
            "options": {
                "project_path": str(project_path),
                "features_path": str(features_path),
                "features_generated": generated_features,
                "prd_path": str(options.prd_path) if options.prd_path else None,
                "base_url": profile.base_url,
                "no_start": options.no_start,
                "dry_run": options.dry_run,
                "setup_mode": options.setup_mode,
                "agentic_evidence": options.agentic_evidence,
                "planned_setup_commands": [command.to_dict() for command in planned_setup_commands],
            },
            "app_profile": profile.to_dict(),
            "app_start": {
                "status": "failed" if startup_error else "ready",
                "error": startup_error,
            },
        }

    def _write_run_artifacts(
        self,
        *,
        output_dir: Path,
        summary: WebEvalSummary,
        evidence_by_feature: dict[str, EvidencePacket],
        judgments: list[FeatureJudgment],
        metadata: dict[str, Any],
    ) -> None:
        write_artifacts(output_dir, summary=summary, evidence_by_feature=evidence_by_feature, judgments=judgments)
        (output_dir / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    def _collect_evidence(
        self,
        *,
        feature: FeatureCheck,
        profile,
        output_dir: Path,
        suffix: str = "scripted",
    ) -> EvidencePacket:
        job = {
            "featureId": feature.id,
            "baseURL": profile.base_url,
            "outputDir": str(output_dir),
            "steps": [_step_to_json(step) for step in feature.steps],
        }
        jobs_dir = output_dir / "jobs"
        jobs_dir.mkdir(exist_ok=True)
        job_path = jobs_dir / f"{feature.id}.{suffix}.json"
        evidence_path = output_dir / "evidence" / f"{feature.id}.{suffix}.browser.json"
        evidence_path.parent.mkdir(exist_ok=True)
        job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

        env = load_project_env()
        proc = subprocess.run(
            ["node", str(BROWSER_SCRIPT), "--job", str(job_path), "--output", str(evidence_path)],
            cwd=str(WEB_EVAL_DIR),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if evidence_path.exists():
            raw = json.loads(evidence_path.read_text(encoding="utf-8"))
            return _evidence_from_raw(raw)
        return EvidencePacket(
            feature_id=feature.id,
            error=(proc.stderr or proc.stdout or "browser layer failed").strip(),
        )


def _step_to_json(step: BrowserAction) -> dict:
    return {"action": step.action, **step.params}


def _evidence_from_raw(raw: dict) -> EvidencePacket:
    return EvidencePacket(
        feature_id=str(raw.get("feature_id", "")),
        url=raw.get("url"),
        page_title=raw.get("page_title"),
        visible_text=raw.get("visible_text"),
        aria_snapshot=raw.get("aria_snapshot"),
        screenshot_path=raw.get("screenshot_path"),
        interactive_elements=list(raw.get("interactive_elements") or []),
        console_errors=list(raw.get("console_errors") or []),
        network_errors=list(raw.get("network_errors") or []),
        action_log=list(raw.get("action_log") or []),
        checks=dict(raw.get("checks") or {}),
        error=raw.get("error"),
    )


def _merge_evidence(scripted: EvidencePacket, planned: EvidencePacket, planned_steps: list[BrowserAction]) -> EvidencePacket:
    checks = dict(scripted.checks)
    checks.update(planned.checks)
    checks["scripted_visible_text"] = scripted.visible_text
    checks["agentic_planned_steps"] = [_step_to_json(step) for step in planned_steps]
    return EvidencePacket(
        feature_id=scripted.feature_id,
        url=planned.url or scripted.url,
        page_title=planned.page_title or scripted.page_title,
        visible_text=planned.visible_text or scripted.visible_text,
        aria_snapshot=planned.aria_snapshot or scripted.aria_snapshot,
        screenshot_path=planned.screenshot_path or scripted.screenshot_path,
        interactive_elements=planned.interactive_elements or scripted.interactive_elements,
        console_errors=[*scripted.console_errors, *planned.console_errors],
        network_errors=[*scripted.network_errors, *planned.network_errors],
        action_log=[*scripted.action_log, "agentic_plan_start", *planned.action_log],
        checks=checks,
        error=planned.error or scripted.error,
    )


def _make_eval_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _startup_failure_results(
    features: list[FeatureCheck],
    startup_error: str,
) -> tuple[dict[str, EvidencePacket], list[FeatureJudgment]]:
    evidence_by_feature: dict[str, EvidencePacket] = {}
    judgments: list[FeatureJudgment] = []
    reason = f"Application failed to start or become ready: {startup_error}"
    for feature in features:
        evidence_by_feature[feature.id] = EvidencePacket(
            feature_id=feature.id,
            action_log=["app_start_failed"],
            checks={
                "app_startup_failed": True,
                "startup_error": startup_error,
            },
            error=startup_error,
        )
        judgments.append(
            FeatureJudgment(
                feature_id=feature.id,
                verdict="fail",
                confidence=1.0,
                reason=reason,
                evidence_used=["startup_error"],
            )
        )
    return evidence_by_feature, judgments


def _build_summary_notes(
    setup_results,
    *,
    startup_error: str | None = None,
) -> str | None:
    notes: list[str] = []
    failed_setup = [result for result in setup_results if result.status == "failed"]
    if failed_setup:
        notes.append(f"{len(failed_setup)} setup command(s) failed; see setup.json.")
    if startup_error:
        notes.append(f"Application startup/readiness failed; all features were marked fail. {startup_error}")
    if not notes:
        return None
    return " ".join(notes)
