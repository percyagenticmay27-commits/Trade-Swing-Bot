import json
from pathlib import Path

from swing_trade_bot import enterprise_strategy_kpi_publisher_v21 as publisher


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _safe_portfolio() -> dict:
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
        "valuation_source": "PAPER_LEDGER_MARK_TO_MARKET",
        "account_capital": 4500.0,
        "portfolio_value": 4550.0,
        "cash_balance": 2700.0,
        "invested_capital": 1800.0,
        "positions_market_value": 1850.0,
        "unrealized_pnl": 50.0,
        "portfolio_return_percent": 1.111111,
        "position_count": 2,
    }


def test_v21_publishes_dashboard_sections_and_artifact_contract(tmp_path):
    _write(tmp_path / "paper_ledger/paper_portfolio_summary.json", _safe_portfolio())
    _write(
        tmp_path / "paper_ledger/paper_portfolio_positions.json",
        {
            "paper_trade_mode": True,
            "positions": [
                {
                    "symbol": "SOXL",
                    "shares": 3.0,
                    "entry_price": 300.0,
                    "current_price": 310.0,
                    "market_value": 930.0,
                    "unrealized_pnl": 30.0,
                    "unrealized_pnl_percent": 3.3333,
                    "active_strategy": "Strategy A",
                }
            ],
        },
    )
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["kpi_contract_version"] == "2.1"
    assert payload["portfolio"]["portfolio_value"] == 4550.0
    assert payload["holdings"]["position_count"] == 2
    assert payload["dashboard_sections"]["portfolio"]["cash_balance"] == 2700.0
    assert payload["dashboard_sections"]["holdings"]["open_positions"][0]["symbol"] == "SOXL"
    assert payload["artifact_contract"]
    assert all(Path(row["path"]).is_absolute() for row in payload["artifact_contract"])
    assert all(row["required"] is False for row in payload["artifact_contract"])


def test_v21_optional_missing_evidence_is_disclosed_not_fabricated(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["evidence_status"] == "PARTIAL"
    assert payload["performance_summary"]["win_rate_percent"] is None
    assert payload["strategy_intelligence"]["opportunity_quality"] is None
    assert payload["missing_optional_artifacts"]
    assert any("Optional evidence unavailable" in warning for warning in payload["warnings"])


def test_v21_atomic_publication(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )
    # Artifact contract order is deterministic by the declared contract tuple.
    payload["artifact_contract"] = sorted(payload["artifact_contract"], key=lambda row: row["artifact_id"])
    output = tmp_path / "enterprise_strategy_kpis.json"
    published = publisher.write_enterprise_strategy_kpis_v21(payload, output)
    assert published == output
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["kpi_contract_version"] == "2.1"
    assert not list(tmp_path.glob("*.tmp"))


def test_v21_safety_values_remain_locked(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )
    payload["broker_execution_enabled"] = True
    assert "broker_execution_enabled must be false" in publisher.validate_enterprise_strategy_kpis_v21(payload)


def test_no_dividend_production_imports_exist():
    source = Path("src/swing_trade_bot/enterprise_strategy_kpi_publisher_v21.py").read_text(encoding="utf-8").lower()
    assert "trade_dividend_bot" not in source
    assert "trade-dividend-bot" not in source
    assert "import dividend" not in source
