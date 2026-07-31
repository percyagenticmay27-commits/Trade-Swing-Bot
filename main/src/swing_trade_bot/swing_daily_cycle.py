"""Unified paper-only orchestration cycle for Swing Bot CIO publication.

The cycle coordinates existing artifacts and governance modules. It never connects
with a broker, places orders, moves capital, changes strategy policy, or writes to
a database. Runtime strategy reports must already be produced by their owning
engines; this coordinator validates and publishes the CIO contract around them.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .swing_cio_acceptance_test import build_cio_acceptance_report, render_markdown as render_acceptance_markdown
from .swing_cio_milestone_1_freeze import build_freeze_report, render_freeze_markdown
from .swing_cio_validation_suite import validate_repository, render_markdown as render_validation_markdown
from .swing_committee_traceability import build_committee_step, build_decision_trace, write_decision_trace
from .swing_committee_runtime_evidence import build_and_write_runtime_evidence
from .opportunity_quality_engine import build_opportunity_quality_report
from .stock_performance_report import build_and_write_stock_performance_report
from .weekly_stock_report import build_and_write_weekly_stock_report
from .executive_dashboard import build_executive_dashboard
from .monthly_command_center import build_monthly_command_center
from .swing_local_filesystem_integration import (
    atomic_write_json,
    build_local_filesystem_registration,
    validate_integration_config,
)

MODULE_NAME = "swing_daily_cycle"
MODULE_VERSION = "1.0.0"
CYCLE_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def atomic_write_text(text: str, destination: str | Path) -> Path:
    final_path = Path(destination)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(final_path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, final_path)
    return final_path


def validate_cycle_config(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("cycle_schema_version") != CYCLE_SCHEMA_VERSION:
        errors.append("cycle_schema_version must be 1.0")
    if payload.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    expected = {
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "direct_database_writes": False,
        "publish_registration_last": True,
        "atomic_publish_required": True,
    }
    for field, value in expected.items():
        if payload.get(field) is not value:
            errors.append(f"{field} must be {str(value).lower()}")
    static = payload.get("static_artifacts")
    if not isinstance(static, Mapping) or not static:
        errors.append("static_artifacts must be a non-empty object")
    for field in ("validation_config", "acceptance_config", "freeze_config", "local_integration_config", "decision_trace_path", "decision_trace_evidence_path", "opportunity_quality_input_path"):
        if not isinstance(payload.get(field), str) or not str(payload.get(field)).strip():
            errors.append(f"{field} must be a non-empty relative path")
    reports = payload.get("required_strategy_reports")
    if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes)) or not reports:
        errors.append("required_strategy_reports must be a non-empty list")
    return errors


def _load_required(root: Path, relative: str, errors: list[str]) -> dict[str, Any]:
    path = root / relative
    try:
        return load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Unable to load {relative}: {exc}")
        return {}


def _publish_static_artifacts(root: Path, output_dir: Path, mapping: Mapping[str, Any], errors: list[str]) -> list[str]:
    published: list[str] = []
    for output_name, source_relative in mapping.items():
        source = root / str(source_relative)
        try:
            payload = load_json(source)
            atomic_write_json(payload, output_dir / str(output_name))
            published.append(str(output_dir / str(output_name)))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"Static artifact {output_name} could not be published from {source_relative}: {exc}")
    return published


def _readiness_alias(report: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(report)
    if "overall_status" not in normalized and "final_result" in normalized:
        normalized["overall_status"] = normalized["final_result"]
    return normalized


def _produce_strategy_reports(
    root: Path,
    output_dir: Path,
    config: Mapping[str, Any],
    generated_at: str,
    errors: list[str],
    published: list[str],
    stage: Callable[[str, bool, str], None],
) -> bool:
    """Run authentic report producers in their frozen dependency order."""

    evidence_relative = str(config.get("decision_trace_evidence_path", ""))
    evidence_path = root / evidence_relative
    try:
        if not evidence_path.is_file():
            build_and_write_runtime_evidence(
                output_dir,
                evidence_path,
                generated_at_utc=generated_at,
                paper_trade_mode=True,
            )
            published.append(str(evidence_path))
            stage("COMMITTEE_RUNTIME_EVIDENCE", True, "Highest-ranked candidate evidence was produced from current reports")
        else:
            stage("COMMITTEE_RUNTIME_EVIDENCE", True, "Existing committee runtime evidence is available")
        evidence = load_json(evidence_path)
        raw_steps = evidence.get("committee_steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("committee_steps must be a non-empty list")
        steps = [
            build_committee_step(
                evaluation_cycle_id=str(evidence.get("evaluation_cycle_id", "")),
                symbol=str(evidence.get("symbol", "")),
                strategy_id=str(evidence.get("strategy_id", "")),
                committee_id=str(item.get("committee_id", "")),
                sequence=int(item.get("sequence", 0)),
                status=str(item.get("status", "")),
                reason_codes=item.get("reason_codes"),
                evidence=item.get("evidence"),
                source_artifacts=item.get("source_artifacts"),
            )
            for item in raw_steps
            if isinstance(item, Mapping)
        ]
        if len(steps) != len(raw_steps):
            raise ValueError("every committee step must be an object")
        trace = build_decision_trace(
            evaluation_cycle_id=str(evidence.get("evaluation_cycle_id", "")),
            symbol=str(evidence.get("symbol", "")),
            strategy_id=str(evidence.get("strategy_id", "")),
            committee_steps=steps,
            final_status=str(evidence.get("final_status", "")),
            source_artifacts=evidence.get("source_artifacts"),
            bias_audit=evidence.get("bias_audit"),
            generated_at_utc=generated_at,
        )
        trace_path = root / str(config.get("decision_trace_path", ""))
        write_decision_trace(trace, trace_path)
        published.append(str(trace_path))
        stage("COMMITTEE_DECISION_TRACE", True, "Authentic committee trace was produced from runtime evidence")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Committee runtime evidence or decision trace production failed: {exc}")
        if not evidence_path.is_file():
            stage("COMMITTEE_RUNTIME_EVIDENCE", False, "Committee runtime evidence production failed safely")
        stage("COMMITTEE_DECISION_TRACE", False, "Committee trace production failed safely")
        _mark_skipped_producers(stage, "Opportunity Quality depends on the committee trace")
        return False

    try:
        build_opportunity_quality_report(
            input_path=root / str(config.get("opportunity_quality_input_path", "")),
            output_dir=output_dir,
            paper_trade_mode=True,
        )
        for suffix in ("csv", "json", "md"):
            published.append(str(output_dir / f"opportunity_quality_report.{suffix}"))
        stage("OPPORTUNITY_QUALITY", True, "Opportunity Quality reports were produced from existing inputs")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Opportunity Quality production failed: {exc}")
        stage("OPPORTUNITY_QUALITY", False, "Opportunity Quality production failed safely")
        stage("STOCK_PERFORMANCE_REPORT", False, "Skipped because Opportunity Quality did not complete")
        stage("WEEKLY_STOCK_REPORT", False, "Skipped because Stock Performance did not complete")
        stage("EXECUTIVE_DASHBOARD", False, "Skipped because Weekly Stock Report did not complete")
        stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")
        return False

    try:
        build_and_write_stock_performance_report(
            output_dir / "strategy_comparison.json",
            output_dir / "strategy_recommendations.csv",
            output_dir / "portfolio_allocations.json",
            output_dir / "portfolio_manager_report.csv",
            output_dir,
            paper_trade_mode=True,
        )
        for suffix in ("csv", "json", "md"):
            published.append(str(output_dir / f"stock_performance_report.{suffix}"))
        stage("STOCK_PERFORMANCE_REPORT", True, "Stock Performance reports were produced from existing paper outputs")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Stock Performance production failed: {exc}")
        stage("STOCK_PERFORMANCE_REPORT", False, "Stock Performance production failed safely")
        stage("WEEKLY_STOCK_REPORT", False, "Skipped because Stock Performance did not complete")
        stage("EXECUTIVE_DASHBOARD", False, "Skipped because Weekly Stock Report did not complete")
        stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")
        return False

    try:
        optional_paths = {
            "portfolio_manager_report_path": output_dir / "portfolio_manager_report.csv",
            "confidence_report_path": output_dir / "confidence_report.json",
            "strategy_recommendations_path": output_dir / "strategy_recommendations.csv",
            "watchlist_report_path": output_dir / "watchlist_report.json",
            "earnings_report_path": output_dir / "earnings_report.json",
        }
        build_and_write_weekly_stock_report(
            output_dir / "stock_performance_report.json",
            output_dir / "portfolio_allocations.json",
            output_dir,
            **{
                name: path
                for name, path in optional_paths.items()
                if path.is_file()
            },
            paper_trade_mode=True,
        )
        for suffix in ("csv", "json", "md"):
            published.append(str(output_dir / f"weekly_stock_report.{suffix}"))
        stage("WEEKLY_STOCK_REPORT", True, "Weekly Stock reports were produced after Stock Performance")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Weekly Stock production failed: {exc}")
        stage("WEEKLY_STOCK_REPORT", False, "Weekly Stock production failed safely")
        stage("EXECUTIVE_DASHBOARD", False, "Skipped because Weekly Stock Report did not complete")
        stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")
        return False

    try:
        build_executive_dashboard(output_dir, output_dir=output_dir, paper_trade_mode=True)
        published.extend([
            str(output_dir / "executive_dashboard.json"),
            str(output_dir / "executive_dashboard.md"),
        ])
        stage("EXECUTIVE_DASHBOARD", True, "Executive Dashboard was produced from existing reports")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Executive Dashboard production failed: {exc}")
        stage("EXECUTIVE_DASHBOARD", False, "Executive Dashboard production failed safely")
        stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")
        return False

    try:
        build_monthly_command_center(output_dir, output_dir=output_dir, paper_trade_mode=True)
        published.extend([
            str(output_dir / "monthly_command_center.json"),
            str(output_dir / "monthly_command_center.md"),
        ])
        stage("MONTHLY_COMMAND_CENTER", True, "Monthly Command Center was produced from existing reports")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Monthly Command Center production failed: {exc}")
        stage("MONTHLY_COMMAND_CENTER", False, "Monthly Command Center production failed safely")
        return False
    return True


def _mark_skipped_producers(
    stage: Callable[[str, bool, str], None],
    reason: str,
) -> None:
    stage("OPPORTUNITY_QUALITY", False, f"Skipped: {reason}")
    stage("STOCK_PERFORMANCE_REPORT", False, "Skipped because Opportunity Quality did not complete")
    stage("WEEKLY_STOCK_REPORT", False, "Skipped because Stock Performance did not complete")
    stage("EXECUTIVE_DASHBOARD", False, "Skipped because Weekly Stock Report did not complete")
    stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")


def run_swing_daily_cycle(
    repository_root: str | Path,
    *,
    cycle_config_path: str | Path = "configs/swing_daily_cycle.json",
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    generated_at = generated_at_utc or _utc_now()
    errors: list[str] = []
    warnings: list[str] = []
    stages: list[dict[str, Any]] = []
    published: list[str] = []

    def stage(name: str, passed: bool, message: str) -> None:
        stages.append({"stage": name, "status": "PASS" if passed else "FAIL", "message": message})

    config = _load_required(root, str(cycle_config_path), errors)
    config_errors = validate_cycle_config(config) if config else ["Cycle configuration is unavailable"]
    errors.extend(config_errors)
    stage("CYCLE_CONFIGURATION", not config_errors, "Unified cycle configuration is valid")

    output_dir = root / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    static_mapping = config.get("static_artifacts") if isinstance(config.get("static_artifacts"), Mapping) else {}
    static_before = len(errors)
    published.extend(_publish_static_artifacts(root, output_dir, static_mapping, errors))
    stage("STATIC_CIO_ARTIFACTS", len(errors) == static_before, "CIO contracts were atomically published")

    producers_ready = _produce_strategy_reports(
        root,
        output_dir,
        config,
        generated_at,
        errors,
        published,
        stage,
    )
    required_paths = [
        str(config.get("decision_trace_path", "")),
        *[str(item) for item in config.get("required_strategy_reports", [])],
    ]
    missing_reports = [
        item for item in required_paths if not item or not (root / item).is_file()
    ]
    if missing_reports:
        warnings.extend(
            f"Required strategy report is not available yet: {item}"
            for item in missing_reports
        )
    reports_ready = producers_ready and not missing_reports
    stage("STRATEGY_REPORTS", reports_ready, "All contracted strategy reports are present")

    validation_config = _load_required(root, str(config.get("validation_config", "")), errors)
    if reports_ready and validation_config:
        validation_report = validate_repository(root, validation_config)
    else:
        validation_report = {
            "overall_status": "NOT_READY",
            "governance_health_score": 0,
            "errors": ["Required strategy reports are unavailable; CIO validation was not run"],
        }
    atomic_write_json(validation_report, output_dir / "swing_cio_validation_report.json")
    atomic_write_text(render_validation_markdown(validation_report), output_dir / "swing_cio_validation_report.md")
    published.extend([str(output_dir / "swing_cio_validation_report.json"), str(output_dir / "swing_cio_validation_report.md")])
    validation_ready = validation_report.get("overall_status") == "READY" and not validation_report.get("errors")
    stage("FULL_CIO_VALIDATION", validation_ready, "Phase 9F validation completed only after report readiness")

    acceptance_config = _load_required(root, str(config.get("acceptance_config", "")), errors)
    service_registration = _load_required(root, "configs/swing_strategy_service_registration.json", errors)
    strategy_profiles = _load_required(root, "configs/swing_strategy_capability_profiles.json", errors)
    committee_governance = _load_required(root, "configs/swing_committee_governance.json", errors)
    committee_learning = _load_required(root, "configs/swing_committee_learning.json", errors)
    decision_trace = _load_required(root, str(config.get("decision_trace_path", "")), errors)

    if all((acceptance_config, service_registration, strategy_profiles, committee_governance, committee_learning, decision_trace)):
        acceptance_report = build_cio_acceptance_report(
            acceptance_config=acceptance_config,
            validation_report=validation_report,
            service_registration=service_registration,
            strategy_profiles=strategy_profiles,
            committee_governance=committee_governance,
            committee_learning=committee_learning,
            decision_trace=decision_trace,
            generated_at_utc=generated_at,
        )
    else:
        acceptance_report = {
            "module_name": "swing_cio_acceptance_test",
            "plugin_id": PLUGIN_ID,
            "generated_at_utc": generated_at,
            "paper_trade_mode": True,
            "advisory_only": True,
            "final_result": "NOT_READY_FOR_CIO",
            "overall_status": "NOT_READY_FOR_CIO",
            "stages": [],
            "errors": ["Acceptance inputs are incomplete"],
            "warnings": [],
        }
    acceptance_report = _readiness_alias(acceptance_report)
    atomic_write_json(acceptance_report, output_dir / "swing_cio_acceptance_report.json")
    atomic_write_text(render_acceptance_markdown(acceptance_report), output_dir / "swing_cio_acceptance_report.md")
    published.extend([str(output_dir / "swing_cio_acceptance_report.json"), str(output_dir / "swing_cio_acceptance_report.md")])
    acceptance_ready = acceptance_report.get("overall_status") == "READY_FOR_CIO" and not acceptance_report.get("errors")
    stage("CIO_ACCEPTANCE", acceptance_ready, "Phase 9F.1 acceptance completed")

    freeze_config = _load_required(root, str(config.get("freeze_config", "")), errors)
    freeze_report = build_freeze_report(freeze_config, validation_report, acceptance_report) if freeze_config else {
        "freeze_status": "NOT_FROZEN", "errors": ["Freeze configuration unavailable"]
    }
    atomic_write_json(freeze_report, output_dir / "swing_cio_milestone_1_freeze.json")
    atomic_write_text(render_freeze_markdown(freeze_report), output_dir / "swing_cio_milestone_1_freeze.md")
    published.extend([str(output_dir / "swing_cio_milestone_1_freeze.json"), str(output_dir / "swing_cio_milestone_1_freeze.md")])
    frozen = freeze_report.get("freeze_status") == "FROZEN" and not freeze_report.get("errors")
    stage("MILESTONE_1_FREEZE", frozen, "CIO compatibility contract remains frozen")

    integration_config = _load_required(root, str(config.get("local_integration_config", "")), errors)
    integration_result = validate_integration_config(integration_config) if integration_config else None
    registration_published = False
    if integration_result and integration_result.valid and acceptance_ready and frozen and not missing_reports:
        registration = build_local_filesystem_registration(integration_config, generated_at)
        atomic_write_json(registration, output_dir / "swing_local_filesystem_registration.json")
        published.append(str(output_dir / "swing_local_filesystem_registration.json"))
        registration_published = True
    elif integration_result and not integration_result.valid:
        errors.extend(integration_result.errors)
    stage("LOCAL_FILESYSTEM_REGISTRATION", registration_published, "Registration is published last only after full readiness")

    cycle_status = "COMPLETE" if registration_published and not errors else "BLOCKED"
    report = {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "cycle_schema_version": CYCLE_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "plugin_id": PLUGIN_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "cycle_status": cycle_status,
        "registration_published": registration_published,
        "stage_count": len(stages),
        "passed_stage_count": sum(1 for item in stages if item["status"] == "PASS"),
        "stages": stages,
        "published_artifacts": published,
        "missing_strategy_reports": missing_reports,
        "errors": errors,
        "warnings": warnings,
    }
    atomic_write_json(report, root / str(config.get("cycle_report_json", "results/swing_daily_cycle_report.json")))
    atomic_write_text(render_cycle_markdown(report), root / str(config.get("cycle_report_markdown", "results/swing_daily_cycle_report.md")))
    return report


def render_cycle_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Swing Daily Cycle Report", "",
        f"- Cycle status: **{report.get('cycle_status')}**",
        f"- Plugin ID: `{report.get('plugin_id')}`",
        f"- Registration published: **{report.get('registration_published')}**",
        f"- Passed stages: {report.get('passed_stage_count')} / {report.get('stage_count')}", "",
        "## Stages", "",
    ]
    for item in report.get("stages") or []:
        lines.append(f"- {item.get('stage')}: **{item.get('status')}** — {item.get('message')}")
    lines.extend(["", "## Missing Strategy Reports", ""])
    missing = report.get("missing_strategy_reports") or []
    lines.extend(f"- `{item}`" for item in missing) if missing else lines.append("- None")
    lines.extend(["", "## Errors", ""])
    errors = report.get("errors") or []
    lines.extend(f"- {item}" for item in errors) if errors else lines.append("- None")
    lines.extend(["", "Paper-only and advisory-only. Registration is always the final publication step.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the unified paper-only Swing Bot daily cycle")
    parser.add_argument("--root", default=".", help="Swing Bot Python project root")
    parser.add_argument("--config", default="configs/swing_daily_cycle.json", help="Cycle configuration path relative to root")
    args = parser.parse_args(argv)
    report = run_swing_daily_cycle(args.root, cycle_config_path=args.config)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["cycle_status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
