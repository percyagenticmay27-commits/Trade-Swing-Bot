"""Unified paper-only orchestration cycle for Swing Bot CIO publication.

The cycle coordinates existing Swing-owned producers in dependency order. It
never connects with a broker, places orders, moves capital, changes strategy
policy, or writes to the AI CIO host. Current runtime evidence is refreshed before
downstream reports are published so new reports cannot silently consume stale
watchlist, allocation, committee, or paper-ledger artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .discovery_engine import (
    DiscoveryEngine,
    load_candidates,
    load_financial_health,
    load_mentions,
    write_watchlist_reports,
)
from .enterprise_strategy_allocation_discovery import (
    load_discovered_strategy_allocations,
    resolve_strategy_allocation_evidence,
)
from .executive_dashboard import build_executive_dashboard
from .monthly_command_center import build_monthly_command_center
from .opportunity_quality_engine import build_opportunity_quality_report
from .opportunity_quality_inputs import build_and_write_opportunity_quality_inputs
from .paper_portfolio_manager import build_and_write_paper_portfolio_report
from .performance_analytics_engine import build_and_write_performance_analytics_report
from .portfolio_allocation_engine import build_portfolio_allocation_report
from .stock_performance_report import build_and_write_stock_performance_report
from .swing_cio_acceptance_test import build_cio_acceptance_report, render_markdown as render_acceptance_markdown
from .swing_cio_milestone_1_freeze import build_freeze_report, render_freeze_markdown
from .swing_cio_validation_suite import validate_repository, render_markdown as render_validation_markdown
from .swing_committee_runtime_evidence import build_and_write_runtime_evidence
from .swing_committee_traceability import build_committee_step, build_decision_trace, write_decision_trace
from .swing_local_filesystem_integration import (
    atomic_write_json,
    build_local_filesystem_registration,
    validate_integration_config,
)
from .trade_history_manager import build_and_write_trade_history_report
from .weekly_stock_report import build_and_write_weekly_stock_report

MODULE_NAME = "swing_daily_cycle"
MODULE_VERSION = "1.1.0"
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
    for field in (
        "validation_config",
        "acceptance_config",
        "freeze_config",
        "local_integration_config",
        "decision_trace_path",
        "decision_trace_evidence_path",
        "opportunity_quality_input_path",
    ):
        if not isinstance(payload.get(field), str) or not str(payload.get(field)).strip():
            errors.append(f"{field} must be a non-empty relative path")
    reports = payload.get("required_strategy_reports")
    if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes)) or not reports:
        errors.append("required_strategy_reports must be a non-empty list")

    refresh = payload.get("runtime_evidence_refresh")
    if refresh is not None:
        if not isinstance(refresh, Mapping):
            errors.append("runtime_evidence_refresh must be an object")
        elif refresh.get("enabled") is True:
            for section_name, fields in {
                "watchlist": ("candidates_path", "mentions_path", "financial_health_path"),
                "portfolio_allocation": ("confidence_path", "strategy_recommendations_path"),
                "paper_ledger": ("ledger_dir", "data_dir"),
            }.items():
                section = refresh.get(section_name)
                if not isinstance(section, Mapping):
                    errors.append(f"runtime_evidence_refresh.{section_name} must be an object")
                    continue
                for field in fields:
                    if not isinstance(section.get(field), str) or not str(section.get(field)).strip():
                        errors.append(
                            f"runtime_evidence_refresh.{section_name}.{field} must be a non-empty relative path"
                        )
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


def _cycle_date(generated_at: str) -> date:
    try:
        return date.fromisoformat(generated_at[:10])
    except ValueError:
        return date.today()


def _runtime_refresh_config(config: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = config.get("runtime_evidence_refresh")
    if isinstance(value, Mapping) and value.get("enabled") is True:
        return value
    return None


def _refresh_watchlist(
    root: Path,
    output_dir: Path,
    refresh: Mapping[str, Any],
    generated_at: str,
    published: list[str],
) -> None:
    section = refresh.get("watchlist")
    if not isinstance(section, Mapping):
        raise ValueError("runtime watchlist refresh configuration is unavailable")
    candidates_path = root / str(section.get("candidates_path", ""))
    mentions_path = root / str(section.get("mentions_path", ""))
    financial_health_path = root / str(section.get("financial_health_path", ""))
    for label, path in (
        ("candidate state", candidates_path),
        ("discovery mentions", mentions_path),
        ("financial health", financial_health_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Current watchlist {label} input is missing: {path}")

    as_of = _cycle_date(generated_at)
    rows = DiscoveryEngine(paper_trade_mode=True).evaluate(
        load_candidates(candidates_path),
        load_mentions(mentions_path),
        load_financial_health(financial_health_path),
        as_of=as_of,
    )
    csv_path, json_path = write_watchlist_reports(output_dir, rows)
    payload = load_json(json_path)
    payload.update(
        {
            "strategy_id": PLUGIN_ID,
            "generated_at_utc": generated_at,
            "as_of_date": as_of.isoformat(),
            "freshness_status": "CURRENT_CYCLE",
            "source_artifacts": [
                str(candidates_path.relative_to(root)),
                str(mentions_path.relative_to(root)),
                str(financial_health_path.relative_to(root)),
            ],
            "candidate_state_source": str(candidates_path.relative_to(root)),
            "screening_performance_scope": "CANDIDATE_LIFECYCLE_INPUT_NOT_STRATEGY_PERFORMANCE",
        }
    )
    atomic_write_json(payload, json_path)
    published.extend([str(csv_path), str(json_path)])


def _refresh_allocation_and_paper_evidence(
    root: Path,
    output_dir: Path,
    refresh: Mapping[str, Any],
    generated_at: str,
    published: list[str],
) -> None:
    allocation_cfg = refresh.get("portfolio_allocation")
    if not isinstance(allocation_cfg, Mapping):
        raise ValueError("runtime portfolio allocation configuration is unavailable")
    confidence_path = root / str(allocation_cfg.get("confidence_path", ""))
    strategy_path = root / str(allocation_cfg.get("strategy_recommendations_path", ""))
    watchlist_path = output_dir / "watchlist_report.json"
    for label, path in (
        ("confidence", confidence_path),
        ("strategy recommendations", strategy_path),
        ("watchlist", watchlist_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Current portfolio allocation {label} input is missing: {path}")

    build_portfolio_allocation_report(
        confidence_path=confidence_path,
        watchlist_path=watchlist_path,
        strategy_recommendations_path=strategy_path,
        output_dir=output_dir,
        paper_trade_mode=True,
    )
    published.extend([
        str(output_dir / "portfolio_allocations.csv"),
        str(output_dir / "portfolio_allocations.json"),
    ])

    ledger_cfg = refresh.get("paper_ledger")
    if not isinstance(ledger_cfg, Mapping):
        raise ValueError("runtime paper ledger configuration is unavailable")
    ledger_dir = root / str(ledger_cfg.get("ledger_dir", ""))
    data_dir = root / str(ledger_cfg.get("data_dir", ""))
    if not (ledger_dir / "open_positions.json").is_file():
        raise FileNotFoundError(f"Paper open-position state is missing: {ledger_dir / 'open_positions.json'}")
    if not (ledger_dir / "trade_history.json").is_file():
        raise FileNotFoundError(f"Paper trade history is missing: {ledger_dir / 'trade_history.json'}")

    allocations_payload, allocation_source_path = load_discovered_strategy_allocations()
    allocation_evidence = resolve_strategy_allocation_evidence(allocations_payload, PLUGIN_ID)
    account_capital = float(allocation_evidence["allocated_capital"])
    if account_capital <= 0:
        raise ValueError("Governed SWING-001 allocation must be positive")

    max_price_age_days = int(ledger_cfg.get("max_price_age_days", 5))
    build_and_write_paper_portfolio_report(
        ledger_dir=ledger_dir,
        data_dir=data_dir,
        output_dir=ledger_dir,
        account_capital=account_capital,
        as_of=_cycle_date(generated_at),
        max_price_age_days=max_price_age_days,
    )
    summary_path = ledger_dir / "paper_portfolio_summary.json"
    summary = load_json(summary_path)
    summary.update(
        {
            "strategy_id": PLUGIN_ID,
            "account_capital_source": "AI_CIO_ENTERPRISE_EVIDENCE",
            "account_capital_source_path": str(allocation_source_path.resolve()),
            "account_capital_source_json_path": allocation_evidence.get("allocation_source_json_path"),
            "account_capital_evidence_schema": allocation_evidence.get("allocation_evidence_schema"),
        }
    )
    atomic_write_json(summary, summary_path)
    published.extend([
        str(summary_path),
        str(ledger_dir / "paper_portfolio_positions.json"),
    ])

    build_and_write_trade_history_report(
        trade_history_path=ledger_dir / "trade_history.json",
        output_dir=ledger_dir,
    )
    published.extend([
        str(ledger_dir / "managed_trade_history.json"),
        str(ledger_dir / "closed_positions.json"),
        str(ledger_dir / "trade_history_summary.json"),
    ])

    build_and_write_performance_analytics_report(
        ledger_dir=ledger_dir,
        output_dir=ledger_dir,
    )
    published.extend([
        str(ledger_dir / "paper_performance.json"),
        str(ledger_dir / "paper_performance.csv"),
        str(ledger_dir / "paper_performance.md"),
    ])


def _produce_strategy_reports(
    root: Path,
    output_dir: Path,
    config: Mapping[str, Any],
    generated_at: str,
    errors: list[str],
    published: list[str],
    stage: Callable[[str, bool, str], None],
) -> bool:
    """Run authentic producers in current-evidence dependency order."""
    refresh = _runtime_refresh_config(config)
    try:
        if refresh is not None:
            _refresh_watchlist(root, output_dir, refresh, generated_at, published)
        quality_input_path = root / str(config.get("opportunity_quality_input_path", ""))
        build_and_write_opportunity_quality_inputs(output_dir, quality_input_path)
        published.append(str(quality_input_path))
        stage("OPPORTUNITY_QUALITY_INPUTS", True, "Opportunity Quality inputs were rebuilt from the current ranked watchlist")
        build_opportunity_quality_report(
            input_path=quality_input_path,
            output_dir=output_dir,
            paper_trade_mode=True,
        )
        for suffix in ("csv", "json", "md"):
            published.append(str(output_dir / f"opportunity_quality_report.{suffix}"))
        stage("OPPORTUNITY_QUALITY", True, "Opportunity Quality was rebuilt before committee evaluation")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Opportunity Quality input or report production failed: {exc}")
        stage("OPPORTUNITY_QUALITY_INPUTS", False, "Opportunity Quality input assembly or current watchlist refresh failed safely")
        stage("OPPORTUNITY_QUALITY", False, "Opportunity Quality production failed safely")
        stage("COMMITTEE_RUNTIME_EVIDENCE", False, "Skipped because current Opportunity Quality did not complete")
        stage("COMMITTEE_DECISION_TRACE", False, "Skipped because committee runtime evidence did not complete")
        stage("STOCK_PERFORMANCE_REPORT", False, "Skipped because current runtime evidence did not complete")
        stage("WEEKLY_STOCK_REPORT", False, "Skipped because Stock Performance did not complete")
        stage("EXECUTIVE_DASHBOARD", False, "Skipped because Weekly Stock Report did not complete")
        stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")
        return False

    evidence_relative = str(config.get("decision_trace_evidence_path", ""))
    evidence_path = root / evidence_relative
    try:
        build_and_write_runtime_evidence(
            output_dir,
            evidence_path,
            generated_at_utc=generated_at,
            paper_trade_mode=True,
        )
        published.append(str(evidence_path))
        stage("COMMITTEE_RUNTIME_EVIDENCE", True, "Committees consumed the current ranked watchlist and freshly generated Opportunity Quality")
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
        stage("COMMITTEE_DECISION_TRACE", True, "Authentic committee trace was produced from current-cycle runtime evidence")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Committee runtime evidence or decision trace production failed: {exc}")
        stage("COMMITTEE_RUNTIME_EVIDENCE", False, "Committee runtime evidence production failed safely")
        stage("COMMITTEE_DECISION_TRACE", False, "Committee trace production failed safely")
        stage("STOCK_PERFORMANCE_REPORT", False, "Skipped because committee evidence did not complete")
        stage("WEEKLY_STOCK_REPORT", False, "Skipped because Stock Performance did not complete")
        stage("EXECUTIVE_DASHBOARD", False, "Skipped because Weekly Stock Report did not complete")
        stage("MONTHLY_COMMAND_CENTER", False, "Skipped because Executive Dashboard did not complete")
        return False

    try:
        if refresh is not None:
            _refresh_allocation_and_paper_evidence(root, output_dir, refresh, generated_at, published)
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
        stage("STOCK_PERFORMANCE_REPORT", True, "Stock Performance consumed current allocation and refreshed paper evidence")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Current allocation, paper evidence, or Stock Performance production failed: {exc}")
        stage("STOCK_PERFORMANCE_REPORT", False, "Current allocation, paper evidence, or Stock Performance production failed safely")
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
        stage("WEEKLY_STOCK_REPORT", True, "Weekly Stock reports were produced after current Stock Performance")
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
        stage("EXECUTIVE_DASHBOARD", True, "Executive Dashboard was produced from current-cycle reports")
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
        stage("MONTHLY_COMMAND_CENTER", True, "Monthly Command Center was produced from current-cycle reports")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Monthly Command Center production failed: {exc}")
        stage("MONTHLY_COMMAND_CENTER", False, "Monthly Command Center production failed safely")
        return False
    return True


def _mark_skipped_producers(
    stage: Callable[[str, bool, str], None],
    reason: str,
) -> None:
    stage("OPPORTUNITY_QUALITY_INPUTS", False, f"Skipped: {reason}")
    stage("OPPORTUNITY_QUALITY", False, f"Skipped: {reason}")
    stage("COMMITTEE_RUNTIME_EVIDENCE", False, f"Skipped: {reason}")
    stage("COMMITTEE_DECISION_TRACE", False, f"Skipped: {reason}")
    stage("STOCK_PERFORMANCE_REPORT", False, "Skipped because current runtime evidence did not complete")
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
