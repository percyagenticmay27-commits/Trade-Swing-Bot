import json
from pathlib import Path

import pytest

from swing_trade_bot.enterprise_strategy_kpi_publisher import (
    build_enterprise_strategy_kpis,
    validate_enterprise_strategy_kpis,
    write_enterprise_strategy_kpis,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_builds_available_evidence_from_existing_swing_outputs(tmp_path):
    write_json(tmp_path / "portfolio_allocations.json", {
        "allocations": [
            {"symbol": "SOXL", "allocation_percent": 25, "confidence_level": "HIGH", "cash_equivalent": ""},
            {"symbol": "TQQQ", "allocation_percent": 15, "confidence_level": "HIGH", "cash_equivalent": ""},
            {"symbol": "SGOV", "allocation_percent": 60, "confidence_level": "RESERVE", "cash_equivalent": "SGOV"},
        ]
    })
    write_json(tmp_path / "executive_dashboard.json", {"summary": {"active_positions": 5}})

    payload = build_enterprise_strategy_kpis(tmp_path, allocated_capital=10000)

    assert payload["strategy_id"] == "SWING-001"
    assert payload["evidence_status"] == "PARTIAL"
    assert payload["allocated_capital"] == 10000.0
    assert payload["allocation_source"] == "ALLOCATED_CAPITAL"
    assert payload["portfolio_value"] == 10000.0
    assert payload["portfolio_value_source"] == "PAPER_ALLOCATION_PROXY"
    assert payload["position_count"] == 2
    assert payload["paper_trade_mode"] is True
    assert payload["broker_execution_enabled"] is False


def test_accepts_strategy_allocations_mapping(tmp_path):
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 10000}},
    )
    assert payload["allocated_capital"] == 10000.0
    assert payload["allocation_source"] == "STRATEGY_ALLOCATIONS"


def test_matching_allocation_inputs_are_accepted(tmp_path):
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations={"SWING-001": 10000},
        allocated_capital=10000,
    )
    assert payload["allocated_capital"] == 10000.0
    assert payload["allocation_source"] == "STRATEGY_ALLOCATIONS"


def test_conflicting_allocation_inputs_fail_clearly(tmp_path):
    with pytest.raises(ValueError, match="Conflicting SWING-001 allocation evidence"):
        build_enterprise_strategy_kpis(
            tmp_path,
            strategy_allocations={"SWING-001": 10000},
            allocated_capital=9000,
        )


def test_missing_allocation_inputs_fail_clearly(tmp_path):
    with pytest.raises(ValueError, match="SWING-001 allocation evidence is required"):
        build_enterprise_strategy_kpis(tmp_path)


def test_nonpositive_allocated_capital_fails_clearly(tmp_path):
    with pytest.raises(ValueError, match="allocated_capital must be a positive finite number"):
        build_enterprise_strategy_kpis(tmp_path, allocated_capital=0)


def test_uses_marked_portfolio_value_when_existing_dashboard_provides_it(tmp_path):
    write_json(tmp_path / "portfolio_allocations.json", {"allocations": []})
    write_json(tmp_path / "executive_dashboard.json", {"summary": {"portfolio_value": 10425.75}})

    payload = build_enterprise_strategy_kpis(tmp_path, allocated_capital=10000)

    assert payload["portfolio_value"] == 10425.75
    assert payload["portfolio_value_source"] == "EXECUTIVE_DASHBOARD"


def test_missing_allocations_remains_registry_only(tmp_path):
    payload = build_enterprise_strategy_kpis(tmp_path, allocated_capital=10000)
    assert payload["evidence_status"] == "REGISTRY_ONLY"
    assert payload["position_count"] == 0


def test_atomic_writer_publishes_valid_json(tmp_path):
    write_json(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = build_enterprise_strategy_kpis(tmp_path, allocated_capital=10000)
    output = write_enterprise_strategy_kpis(payload, tmp_path / "enterprise_strategy_kpis.json")
    assert output.exists()
    assert not (tmp_path / "enterprise_strategy_kpis.json.tmp").exists()
    assert json.loads(output.read_text(encoding="utf-8"))["strategy_id"] == "SWING-001"


@pytest.mark.parametrize(
    ("field", "unsafe"),
    [
        ("paper_trade_mode", False),
        ("paper_compatible", False),
        ("advisory_only", False),
        ("reporting_only", False),
        ("live_trading_enabled", True),
        ("broker_execution_enabled", True),
        ("capital_movement_enabled", True),
        ("order_placement_enabled", True),
        ("automatic_activation_allowed", True),
        ("governance_review_required", False),
        ("direct_database_writes", True),
    ],
)
def test_unsafe_values_are_rejected(tmp_path, field, unsafe):
    write_json(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = build_enterprise_strategy_kpis(tmp_path, allocated_capital=10000)
    payload[field] = unsafe
    assert validate_enterprise_strategy_kpis(payload)


def test_unsafe_source_is_rejected_before_missing_allocation(tmp_path):
    write_json(tmp_path / "paper_ledger" / "paper_performance.json", {
        "paper_trade_mode": False,
    })
    with pytest.raises(ValueError, match="paper_performance.paper_trade_mode must be true"):
        build_enterprise_strategy_kpis(tmp_path)


def test_no_dividend_production_imports():
    source = Path("src/swing_trade_bot/enterprise_strategy_kpi_publisher.py").read_text(encoding="utf-8").lower()
    assert "dividend_bot" not in source
    assert "trade-dividend-bot" not in source
    assert "trade_dividend_bot" not in source
