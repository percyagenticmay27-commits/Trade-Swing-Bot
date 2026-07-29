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
from typing import Any, Mapping, Sequence

from .swing_cio_acceptance_test import build_cio_acceptance_report, render_markdown as render_acceptance_markdown
from .swing_cio_milestone_1_freeze import build_freeze_report, render_freeze_markdown
from .swing_cio_validation_suite import validate_repository, render_markdown as render_validation_markdown
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
    for field in ("validation_config", "acceptance_config", "freeze_config", "local_integration_config", "decision_trace_path"):
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

    missing_reports = [str(item) for item in config.get("required_strategy_reports", []) if not (root / str(item)).exists()]
    if missing_reports:
        warnings.extend(f"Required strategy report is not available yet: {item}" for item in missing_reports)
    stage("STRATEGY_REPORTS", not missing_reports, "All contracted strategy reports are present")

    validation_config = _load_required(root, str(config.get("validation_config", "")), errors)
    validation_report = validate_repository(root, validation_config) if validation_config else {
        "overall_status": "NOT_READY", "governance_health_score": 0, "errors": ["Validation configuration unavailable"]
    }
    atomic_write_json(validation_report, output_dir / "swing_cio_validation_report.json")
    atomic_write_text(render_validation_markdown(validation_report), output_dir / "swing_cio_validation_report.md")
    published.extend([str(output_dir / "swing_cio_validation_report.json"), str(output_dir / "swing_cio_validation_report.md")])
    validation_ready = validation_report.get("overall_status") == "READY" and not validation_report.get("errors")
    stage("FULL_CIO_VALIDATION", validation_ready, "Phase 9F validation completed")

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
