import json
from pathlib import Path

from swing_trade_bot import enterprise_kpi


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_kpis_matches_swing_strategy_identity(tmp_path):
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

    payload = enterprise_kpi.build_kpis(tmp_path, allocated_capital=10_000)

    assert payload["strategy_id"] == "SWING-001"
    assert payload["allocated_capital"] == 10_000.0
    assert payload["position_count"] == 2
    assert payload["evidence_status"] == "AVAILABLE"
    assert enterprise_kpi.validate_kpis(payload) == ()


def test_publish_kpis_writes_host_readable_artifact(tmp_path):
    results = tmp_path / "results"
    _write_json(results / "portfolio_allocations.json", {"allocations": []})
    output = results / "enterprise_strategy_kpis.json"

    published = enterprise_kpi.publish_kpis(
        results,
        output,
        allocated_capital=5_000,
    )

    assert published == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["strategy_id"] == "SWING-001"
    assert payload["allocated_capital"] == 5_000.0
    assert payload["paper_trade_mode"] is True
    assert payload["broker_execution_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["direct_database_writes"] is False


def test_facade_safety_constants_are_locked():
    assert enterprise_kpi.PAPER_TRADE_MODE is True
    assert enterprise_kpi.LIVE_TRADING_ENABLED is False
    assert enterprise_kpi.BROKER_EXECUTION_ENABLED is False
    assert enterprise_kpi.CAPITAL_MOVEMENT_ENABLED is False
    assert enterprise_kpi.ORDER_PLACEMENT_ENABLED is False
    assert enterprise_kpi.DIRECT_DATABASE_WRITES is False


def test_no_dividend_production_imports_exist():
    source = Path("src/swing_trade_bot/enterprise_kpi.py").read_text(encoding="utf-8").lower()
    assert "trade_dividend_bot" not in source
    assert "trade-dividend-bot" not in source
    assert "from dividend" not in source
    assert "import dividend" not in source
