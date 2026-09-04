from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot import swing_daily_cycle as cycle


def _base_config() -> dict:
    return {
        "cycle_schema_version": "1.0",
        "plugin_id": "SWING-001",
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "direct_database_writes": False,
        "publish_registration_last": True,
        "atomic_publish_required": True,
        "static_artifacts": {"swing_plugin_manifest.json": "configs/manifest.json"},
        "validation_config": "configs/validation.json",
        "acceptance_config": "configs/acceptance.json",
        "freeze_config": "configs/freeze.json",
        "local_integration_config": "configs/integration.json",
        "decision_trace_evidence_path": "results/trace_evidence.json",
        "decision_trace_path": "results/trace.json",
        "opportunity_quality_input_path": "results/opportunity_quality_inputs.json",
        "required_strategy_reports": ["results/opportunity_quality_report.json"],
        "cycle_report_json": "results/swing_daily_cycle_report.json",
        "cycle_report_markdown": "results/swing_daily_cycle_report.md",
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_valid_cycle_config() -> None:
    assert cycle.validate_cycle_config(_base_config()) == []


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("paper_trade_mode", False),
        ("advisory_only", False),
        ("automatic_activation_allowed", True),
        ("broker_execution_allowed", True),
        ("capital_movement_allowed", True),
        ("direct_database_writes", True),
        ("publish_registration_last", False),
        ("atomic_publish_required", False),
    ],
)
def test_safety_locks_reject_changes(field: str, bad_value: bool) -> None:
    payload = _base_config()
    payload[field] = bad_value
    assert any(field in error for error in cycle.validate_cycle_config(payload))


def test_wrong_plugin_id_rejected() -> None:
    payload = _base_config()
    payload["plugin_id"] = "BAD"
    assert "plugin_id must be SWING-001" in cycle.validate_cycle_config(payload)


def test_missing_static_mapping_rejected() -> None:
    payload = _base_config()
    payload["static_artifacts"] = {}
    assert any("static_artifacts" in error for error in cycle.validate_cycle_config(payload))


def test_missing_reports_list_rejected() -> None:
    payload = _base_config()
    payload["required_strategy_reports"] = []
    assert any("required_strategy_reports" in error for error in cycle.validate_cycle_config(payload))


def test_runtime_refresh_config_requires_relative_input_paths() -> None:
    payload = _base_config()
    payload["runtime_evidence_refresh"] = {
        "enabled": True,
        "watchlist": {},
        "portfolio_allocation": {},
        "paper_ledger": {},
    }
    errors = cycle.validate_cycle_config(payload)
    assert any("watchlist.candidates_path" in error for error in errors)
    assert any("portfolio_allocation.confidence_path" in error for error in errors)
    assert any("paper_ledger.ledger_dir" in error for error in errors)


def test_atomic_write_text_replaces_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "report.md"
    destination.write_text("old", encoding="utf-8")
    cycle.atomic_write_text("new", destination)
    assert destination.read_text(encoding="utf-8") == "new"
    assert not (tmp_path / "report.md.tmp").exists()


def test_readiness_alias_preserves_existing_status() -> None:
    result = cycle._readiness_alias({"overall_status": "READY_FOR_CIO", "final_result": "OTHER"})
    assert result["overall_status"] == "READY_FOR_CIO"


def test_readiness_alias_copies_final_result() -> None:
    result = cycle._readiness_alias({"final_result": "READY_FOR_CIO"})
    assert result["overall_status"] == "READY_FOR_CIO"


def _prepare_cycle_tree(root: Path, *, include_report: bool = True, include_trace: bool = True) -> dict:
    config = _base_config()
    _write(root / "configs/swing_daily_cycle.json", config)
    _write(root / "configs/manifest.json", {"plugin_id": "SWING-001"})
    for name in (
        "validation.json",
        "acceptance.json",
        "freeze.json",
        "swing_strategy_service_registration.json",
        "swing_strategy_capability_profiles.json",
        "swing_committee_governance.json",
        "swing_committee_learning.json",
    ):
        _write(root / "configs" / name, {"plugin_id": "SWING-001"})
    _write(
        root / "configs/integration.json",
        {
            "integration_schema_version": "1.0",
            "plugin_id": "SWING-001",
            "plugin_name": "Trade Swing Bot",
            "plugin_type": "SWING_TRADING",
            "plugin_root": "/home/tradebot/Trade-Swing-Bot/main",
            "artifact_root": "/home/tradebot/Trade-Swing-Bot/main/results",
            "manifest_path": "/home/tradebot/Trade-Swing-Bot/main/results/swing_plugin_manifest.json",
            "output_contract_path": "/home/tradebot/Trade-Swing-Bot/main/results/swing_output_contract.json",
            "schema_registry_path": "/home/tradebot/Trade-Swing-Bot/main/results/swing_schema_registry.json",
            "acceptance_report_path": "/home/tradebot/Trade-Swing-Bot/main/results/swing_cio_acceptance_report.json",
            "transport": "LOCAL_FILESYSTEM",
            "same_server": True,
            "read_only_consumer": True,
            "paper_trade_mode": True,
            "advisory_only": True,
            "automatic_activation_allowed": False,
            "broker_execution_allowed": False,
            "capital_movement_allowed": False,
            "direct_database_writes": False,
            "atomic_publish_required": True,
            "freshness": {"warning_after_minutes": 1440, "stale_after_minutes": 2880},
        },
    )
    if include_report:
        _write(root / "results/opportunity_quality_report.json", {"status": "READY"})
    if include_trace:
        _write(root / "results/trace.json", {"decision_trace_id": "TRACE-1"})
    return config


def _patch_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cycle, "_produce_strategy_reports", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cycle,
        "validate_repository",
        lambda root, cfg: {"overall_status": "READY", "governance_health_score": 100.0, "errors": [], "category_status": {}},
    )
    monkeypatch.setattr(cycle, "render_validation_markdown", lambda report: "validation")
    monkeypatch.setattr(
        cycle,
        "build_cio_acceptance_report",
        lambda **kwargs: {"final_result": "READY_FOR_CIO", "errors": [], "stages": []},
    )
    monkeypatch.setattr(cycle, "render_acceptance_markdown", lambda report: "acceptance")
    monkeypatch.setattr(
        cycle,
        "build_freeze_report",
        lambda cfg, validation, acceptance: {"freeze_status": "FROZEN", "errors": [], "frozen_interfaces": []},
    )
    monkeypatch.setattr(cycle, "render_freeze_markdown", lambda report: "freeze")


def test_complete_cycle_publishes_registration_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_cycle_tree(tmp_path)
    _patch_ready(monkeypatch)
    report = cycle.run_swing_daily_cycle(tmp_path, generated_at_utc="2026-07-29T12:00:00Z")
    assert report["cycle_status"] == "COMPLETE"
    assert report["registration_published"] is True
    registration = tmp_path / "results/swing_local_filesystem_registration.json"
    assert registration.exists()
    assert report["published_artifacts"][-1] == str(registration)


def test_missing_strategy_report_blocks_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_cycle_tree(tmp_path, include_report=False)
    _patch_ready(monkeypatch)
    report = cycle.run_swing_daily_cycle(tmp_path)
    assert report["cycle_status"] == "BLOCKED"
    assert report["registration_published"] is False
    assert report["missing_strategy_reports"] == ["results/opportunity_quality_report.json"]
    assert not (tmp_path / "results/swing_local_filesystem_registration.json").exists()


def test_missing_trace_blocks_acceptance_and_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_cycle_tree(tmp_path, include_trace=False)
    _patch_ready(monkeypatch)
    report = cycle.run_swing_daily_cycle(tmp_path)
    assert report["cycle_status"] == "BLOCKED"
    assert report["registration_published"] is False
    assert any("trace.json" in error for error in report["errors"])


def test_validation_failure_blocks_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_cycle_tree(tmp_path)
    _patch_ready(monkeypatch)
    monkeypatch.setattr(
        cycle,
        "validate_repository",
        lambda root, cfg: {"overall_status": "NOT_READY", "governance_health_score": 90.0, "errors": ["bad"]},
    )
    monkeypatch.setattr(
        cycle,
        "build_cio_acceptance_report",
        lambda **kwargs: {"final_result": "NOT_READY_FOR_CIO", "errors": ["validation failed"], "stages": []},
    )
    monkeypatch.setattr(
        cycle,
        "build_freeze_report",
        lambda cfg, validation, acceptance: {"freeze_status": "NOT_FROZEN", "errors": ["not ready"]},
    )
    report = cycle.run_swing_daily_cycle(tmp_path)
    assert report["cycle_status"] == "BLOCKED"
    assert report["registration_published"] is False


def test_cycle_report_is_always_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_cycle_tree(tmp_path, include_report=False)
    _patch_ready(monkeypatch)
    cycle.run_swing_daily_cycle(tmp_path)
    assert (tmp_path / "results/swing_daily_cycle_report.json").exists()
    assert (tmp_path / "results/swing_daily_cycle_report.md").exists()


def test_static_artifact_is_published_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_cycle_tree(tmp_path)
    _patch_ready(monkeypatch)
    cycle.run_swing_daily_cycle(tmp_path)
    assert json.loads((tmp_path / "results/swing_plugin_manifest.json").read_text(encoding="utf-8"))["plugin_id"] == "SWING-001"
    assert not (tmp_path / "results/swing_plugin_manifest.json.tmp").exists()


def test_strategy_producer_order_builds_quality_before_committees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "results"
    output.mkdir()
    calls: list[str] = []

    def quality_inputs(results_dir, path):
        calls.append("quality_inputs")
        _write(Path(path), {"paper_trade_mode": True, "entry_score_display_only": True, "rows": [{"symbol": "TOP"}]})
        return Path(path)

    def quality_report(**kwargs):
        calls.append("quality_report")
        _write(output / "opportunity_quality_report.json", {"rows": [{"symbol": "TOP", "opportunity_quality_score": 80, "entry_score": 75, "thesis_intact": True}]})

    def committee(results_dir, path, **kwargs):
        calls.append("committee_runtime")
        _write(
            Path(path),
            {
                "evaluation_cycle_id": "CYCLE",
                "symbol": "TOP",
                "strategy_id": "STRATEGY_A",
                "committee_steps": [{"committee_id": "DISCOVERY_COMMITTEE", "sequence": 1, "status": "PASS", "reason_codes": [], "evidence": {}, "source_artifacts": []}],
                "final_status": "WAIT",
                "source_artifacts": [],
                "bias_audit": {},
            },
        )
        return Path(path)

    monkeypatch.setattr(cycle, "build_and_write_opportunity_quality_inputs", quality_inputs)
    monkeypatch.setattr(cycle, "build_opportunity_quality_report", quality_report)
    monkeypatch.setattr(
        cycle,
        "build_and_write_promotion_readiness",
        lambda output_dir: (
            Path(output_dir) / "promotion_readiness_report.json",
            Path(output_dir) / "promotion_readiness_report.csv",
        ),
    )
    monkeypatch.setattr(cycle, "build_and_write_runtime_evidence", committee)
    monkeypatch.setattr(cycle, "build_committee_step", lambda **kwargs: kwargs)
    monkeypatch.setattr(cycle, "build_decision_trace", lambda **kwargs: {"trace": True})
    monkeypatch.setattr(cycle, "write_decision_trace", lambda payload, path: calls.append("decision_trace") or _write(Path(path), payload))
    monkeypatch.setattr(cycle, "build_and_write_stock_performance_report", lambda *args, **kwargs: calls.append("stock_performance"))
    monkeypatch.setattr(cycle, "build_and_write_weekly_stock_report", lambda *args, **kwargs: calls.append("weekly"))
    monkeypatch.setattr(cycle, "build_executive_dashboard", lambda *args, **kwargs: calls.append("executive"))
    monkeypatch.setattr(cycle, "build_monthly_command_center", lambda *args, **kwargs: calls.append("monthly"))

    config = _base_config()
    errors: list[str] = []
    published: list[str] = []
    stages: list[str] = []
    result = cycle._produce_strategy_reports(
        tmp_path,
        output,
        config,
        "2026-08-13T01:30:26Z",
        errors,
        published,
        lambda name, passed, message: stages.append(name),
    )

    assert result is True
    assert errors == []
    assert calls[:4] == ["quality_inputs", "quality_report", "committee_runtime", "decision_trace"]
    assert calls.index("stock_performance") > calls.index("decision_trace")
    assert stages[:5] == [
        "OPPORTUNITY_QUALITY_INPUTS",
        "OPPORTUNITY_QUALITY",
        "PROMOTION_READINESS",
        "COMMITTEE_RUNTIME_EVIDENCE",
        "COMMITTEE_DECISION_TRACE",
    ]


def test_current_runtime_artifacts_are_rebuilt_even_when_old_files_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "results"
    output.mkdir()
    _write(output / "opportunity_quality_inputs.json", {"stale": True})
    _write(output / "trace_evidence.json", {"stale": True})
    calls = {"quality": 0, "committee": 0}

    def quality_inputs(results_dir, path):
        calls["quality"] += 1
        _write(Path(path), {"rows": [{"symbol": "TOP"}]})
        return Path(path)

    def quality_report(**kwargs):
        _write(output / "opportunity_quality_report.json", {"rows": [{"symbol": "TOP", "opportunity_quality_score": 10}]})

    def committee(results_dir, path, **kwargs):
        calls["committee"] += 1
        _write(
            Path(path),
            {
                "evaluation_cycle_id": "CYCLE",
                "symbol": "TOP",
                "strategy_id": "STRATEGY_A",
                "committee_steps": [{"committee_id": "DISCOVERY_COMMITTEE", "sequence": 1, "status": "PASS", "reason_codes": [], "evidence": {}, "source_artifacts": []}],
                "final_status": "WAIT",
                "source_artifacts": [],
                "bias_audit": {},
            },
        )
        return Path(path)

    monkeypatch.setattr(cycle, "build_and_write_opportunity_quality_inputs", quality_inputs)
    monkeypatch.setattr(cycle, "build_opportunity_quality_report", quality_report)
    monkeypatch.setattr(
        cycle,
        "build_and_write_promotion_readiness",
        lambda output_dir: (
            Path(output_dir) / "promotion_readiness_report.json",
            Path(output_dir) / "promotion_readiness_report.csv",
        ),
    )
    monkeypatch.setattr(cycle, "build_and_write_runtime_evidence", committee)
    monkeypatch.setattr(cycle, "build_committee_step", lambda **kwargs: kwargs)
    monkeypatch.setattr(cycle, "build_decision_trace", lambda **kwargs: {"trace": True})
    monkeypatch.setattr(cycle, "write_decision_trace", lambda payload, path: _write(Path(path), payload))
    monkeypatch.setattr(cycle, "build_and_write_stock_performance_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(cycle, "build_and_write_weekly_stock_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(cycle, "build_executive_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(cycle, "build_monthly_command_center", lambda *args, **kwargs: None)

    errors: list[str] = []
    assert cycle._produce_strategy_reports(
        tmp_path,
        output,
        _base_config(),
        "2026-08-13T01:30:26Z",
        errors,
        [],
        lambda *args: None,
    ) is True
    assert calls == {"quality": 1, "committee": 1}


def test_cli_returns_zero_for_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cycle, "run_swing_daily_cycle", lambda *args, **kwargs: {"cycle_status": "COMPLETE"})
    assert cycle.main(["--root", str(tmp_path)]) == 0


def test_cli_returns_one_for_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cycle, "run_swing_daily_cycle", lambda *args, **kwargs: {"cycle_status": "BLOCKED"})
    assert cycle.main(["--root", str(tmp_path)]) == 1
