import json
from pathlib import Path

import pytest

from swing_trade_bot import enterprise_kpi


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_kpis_uses_preserved_swing_strategy_allocation(tmp_path):
    _write_json(
        tmp_path / "portfolio_allocations.json",
        {
            "allocations": [
                {"symbol": "SOXL", "allocation_percent": 25.0, "confidence_level": "HIGH", "cash_equivalent": ""},
                {"symbol": "TQQQ", "allocation_percent": 15.0, "confidence_level": "HIGH", "cash_equivalent": ""},
                {"symbol": "SGOV", "allocation_percent": 60.0, "confidence_level": "RESERVE", "cash_equivalent": "SGOV"},
            ]
        },
    )

    payload = enterprise_kpi.build_kpis(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["strategy_id"] == "SWING-001"
    assert payload["allocated_capital"] == 4500.0
    assert payload["allocation_source"] == "STRATEGY_ALLOCATIONS"
    assert payload["portfolio_value"] == 4500.0
    assert payload["portfolio_value_source"] == "PAPER_ALLOCATION_PROXY"
    assert payload["position_count"] == 2
    assert payload["evidence_status"] == "AVAILABLE"
    assert enterprise_kpi.validate_kpis(payload) == ()


def test_publish_kpis_reads_strategy_allocation_file(tmp_path):
    results = tmp_path / "results"
    _write_json(results / "portfolio_allocations.json", {"allocations": []})
    allocation_file = tmp_path / "preserved_allocations.json"
    _write_json(allocation_file, {"strategy_allocations": {"SWING-001": 4500.0}})
    output = results / "enterprise_strategy_kpis.json"

    published = enterprise_kpi.publish_kpis(
        results,
        output,
        strategy_allocations_path=allocation_file,
    )

    assert published == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["allocated_capital"] == 4500.0
    assert payload["portfolio_value"] == 4500.0
    assert payload["strategy_allocations_source"] == str(allocation_file)
    assert payload["paper_trade_mode"] is True
    assert payload["broker_execution_enabled"] is False
    assert payload["capital_movement_enabled"] is False


def test_missing_swing_allocation_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="SWING-001"):
        enterprise_kpi.build_kpis(
            tmp_path,
            strategy_allocations={"strategy_allocations": {"DIVIDEND-001": 5500.0}},
        )


def test_missing_allocation_file_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        enterprise_kpi.publish_kpis(
            tmp_path,
            tmp_path / "out.json",
            strategy_allocations_path=tmp_path / "missing.json",
        )


def test_proxy_must_equal_strategy_allocation(tmp_path):
    payload = enterprise_kpi.build_kpis(
        tmp_path,
        strategy_allocations={"SWING-001": 4500.0},
    )
    payload["portfolio_value"] = 10000.0
    assert "PAPER_ALLOCATION_PROXY must equal allocated_capital" in enterprise_kpi.validate_kpis(payload)


def test_facade_safety_constants_are_locked():
    assert enterprise_kpi.PAPER_TRADE_MODE is True
    assert enterprise_kpi.LIVE_TRADING_ENABLED is False
    assert enterprise_kpi.BROKER_EXECUTION_ENABLED is False
    assert enterprise_kpi.CAPITAL_MOVEMENT_ENABLED is False
    assert enterprise_kpi.ORDER_PLACEMENT_ENABLED is False
    assert enterprise_kpi.DIRECT_DATABASE_WRITES is False


def test_no_external_host_production_imports_exist():
    source = Path("src/swing_trade_bot/enterprise_kpi.py").read_text(encoding="utf-8").lower()
    assert "trade_dividend_bot" not in source
    assert "trade-dividend-bot" not in source
    assert "from dividend" not in source
    assert "import dividend" not in source
