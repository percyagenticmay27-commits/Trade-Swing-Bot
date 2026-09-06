import json
from pathlib import Path

from swing_trade_bot import enterprise_strategy_kpi_publisher_v21 as publisher


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _safe_portfolio(*, valuation_source: str = "PAPER_LEDGER_MARK_TO_MARKET") -> dict:
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
        "valuation_source": valuation_source,
        "account_capital": 4500.0,
        "portfolio_value": 4550.0,
        "cash_balance": 2700.0,
        "invested_capital": 1800.0,
        "positions_market_value": 1850.0,
        "unrealized_pnl": 50.0,
        "portfolio_return_percent": 1.111111,
        "position_count": 2,
    }


def _positions() -> dict:
    return {
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
    }


def test_v21_publishes_dashboard_sections_and_artifact_contract(tmp_path):
    _write(tmp_path / "paper_ledger/paper_portfolio_summary.json", _safe_portfolio())
    _write(tmp_path / "paper_ledger/paper_portfolio_positions.json", _positions())
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


def test_v21_accepts_split_adjusted_current_paper_portfolio(tmp_path):
    _write(
        tmp_path / "paper_ledger/paper_portfolio_summary.json",
        _safe_portfolio(valuation_source="PAPER_LEDGER_SPLIT_ADJUSTED_MARK_TO_MARKET"),
    )
    _write(tmp_path / "paper_ledger/paper_portfolio_positions.json", _positions())
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["portfolio_value_source"] == "PAPER_LEDGER_SPLIT_ADJUSTED_MARK_TO_MARKET"
    assert payload["portfolio_value"] == 4550.0
    assert payload["cash_balance"] == 2700.0
    assert payload["invested_capital"] == 1800.0
    assert payload["open_positions"][0]["symbol"] == "SOXL"


def test_v21_publishes_open_trade_analytics_without_fabricated_exit_fields(tmp_path):
    summary = _safe_portfolio()
    summary["position_count"] = 1
    summary["invested_capital"] = 900.0
    summary["positions_market_value"] = 930.0
    summary["cash_balance"] = 3600.0
    summary["portfolio_value"] = 4530.0
    summary["unrealized_pnl"] = 30.0
    _write(tmp_path / "paper_ledger/paper_portfolio_summary.json", summary)
    _write(
        tmp_path / "paper_ledger/paper_portfolio_positions.json",
        {
            "paper_trade_mode": True,
            "positions": [
                {
                    "symbol": "SOXL",
                    "entry_date": "2026-08-04",
                    "entry_price": 300.0,
                    "shares": 3.0,
                    "cost_basis": 900.0,
                    "current_price": 310.0,
                    "market_value": 930.0,
                    "unrealized_pnl": 30.0,
                    "unrealized_pnl_percent": 3.3333,
                    "active_strategy": "Strategy A",
                    "status": "OPEN",
                    "max_drawdown_amount": -45.0,
                    "max_drawdown_percent": -5.0,
                }
            ],
        },
    )
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    row = payload["trade_analytics"]["open_positions"][0]
    assert row["symbol"] == "SOXL"
    assert row["entry_date"] == "2026-08-04"
    assert row["entry_price"] == 300.0
    assert row["shares"] == 3.0
    assert row["cost_basis"] == 900.0
    assert row["current_price"] == 310.0
    assert row["market_value"] == 930.0
    assert row["unrealized_pnl"] == 30.0
    assert row["unrealized_pnl_percent"] == 3.3333
    assert row["active_strategy"] == "Strategy A"
    assert row["position_status"] == "OPEN"
    assert row["max_drawdown_amount"] == -45.0
    assert row["max_drawdown_percent"] == -5.0
    assert "exit_date" not in row
    assert "exit_price" not in row
    assert "realized_pnl" not in row


def test_v21_does_not_infer_max_drawdown_from_snapshot_prices(tmp_path):
    summary = _safe_portfolio()
    summary["position_count"] = 1
    _write(tmp_path / "paper_ledger/paper_portfolio_summary.json", summary)
    _write(tmp_path / "paper_ledger/paper_portfolio_positions.json", _positions())
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    row = payload["trade_analytics"]["open_positions"][0]
    assert row["max_drawdown_amount"] is None
    assert row["max_drawdown_percent"] is None
    assert payload["trade_analytics"]["max_drawdown_inference_allowed"] is False
    assert payload["trade_analytics"]["max_drawdown_policy"] == "AUTHORITATIVE_POSITION_HISTORY_ONLY"


def test_v21_publishes_closed_trade_analytics_when_authoritative_fields_exist(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    _write(
        tmp_path / "paper_ledger/closed_positions.json",
        {
            "paper_trade_mode": True,
            "closed_positions": [
                {
                    "symbol": "SOXL",
                    "entry_date": "2026-07-01",
                    "entry_price": 120.0,
                    "shares": 5.0,
                    "cost_basis": 600.0,
                    "exit_date": "2026-07-18",
                    "exit_price": 132.0,
                    "realized_pnl": 60.0,
                    "realized_pnl_percent": 10.0,
                    "holding_days": 17,
                    "exit_reason": "STRATEGY_A_EXIT_CONFIRMED",
                    "active_strategy": "Strategy A",
                    "status": "CLOSED",
                    "max_drawdown_amount": -24.0,
                    "max_drawdown_percent": -4.0,
                }
            ],
        },
    )

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    row = payload["trade_analytics"]["closed_positions"][0]
    assert row == {
        "symbol": "SOXL",
        "entry_date": "2026-07-01",
        "entry_price": 120.0,
        "shares": 5.0,
        "cost_basis": 600.0,
        "exit_date": "2026-07-18",
        "exit_price": 132.0,
        "realized_pnl": 60.0,
        "realized_pnl_percent": 10.0,
        "holding_days": 17.0,
        "exit_reason": "STRATEGY_A_EXIT_CONFIRMED",
        "active_strategy": "Strategy A",
        "position_status": "CLOSED",
        "max_drawdown_amount": -24.0,
        "max_drawdown_percent": -4.0,
    }
    assert payload["trade_history"]["closed_position_analytics"] == [row]
    assert payload["dashboard_sections"]["trade_analytics"]["closed_positions"] == [row]


def test_v21_uses_registered_opportunity_quality_report_filename(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    _write(
        tmp_path / "opportunity_quality_report.json",
        {
            "strategy_id": "SWING-001",
            "opportunity_quality_score": 77.5,
            "paper_trade_mode": True,
        },
    )

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    row = next(
        item for item in payload["artifact_contract"]
        if item["artifact_id"] == "opportunity_quality"
    )
    assert row["relative_path"] == "opportunity_quality_report.json"
    assert row["available"] is True
    assert payload["strategy_intelligence"]["opportunity_quality_evidence"]["strategy_id"] == "SWING-001"
    assert payload["opportunity_quality"] == 77.5


def test_v21_extracts_current_opportunity_quality_from_report_rows(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    _write(
        tmp_path / "opportunity_quality_report.json",
        {
            "paper_trade_mode": True,
            "rows": [
                {"symbol": "NBIS", "opportunity_quality_score": 15.458},
                {"symbol": "OTHER", "opportunity_quality_score": 9.0},
            ],
        },
    )

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["opportunity_quality"] == 15.458
    assert payload["dashboard_sections"]["opportunity_quality"]["score"] == 15.458


def test_watchlist_win_rate_never_becomes_strategy_win_rate(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    _write(
        tmp_path / "watchlist_report.json",
        {
            "paper_trade_mode": True,
            "rows": [{"underlying_symbol": "NBIS", "win_rate": 45.0}],
        },
    )

    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["win_rate_percent"] is None
    assert payload["performance_summary"]["win_rate_percent"] is None


def test_v21_optional_missing_evidence_is_disclosed_not_fabricated(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    assert payload["evidence_status"] == "PARTIAL"
    assert payload["performance_summary"]["win_rate_percent"] is None
    assert payload["strategy_intelligence"]["opportunity_quality"] is None
    assert payload["trade_analytics"]["open_positions"] == []
    assert payload["trade_analytics"]["closed_positions"] == []
    assert payload["missing_optional_artifacts"]
    assert any("Optional evidence unavailable" in warning for warning in payload["warnings"])


def test_v21_atomic_publication(tmp_path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = publisher.build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )
    payload["artifact_contract"] = sorted(payload["artifact_contract"], key=lambda row: row["artifact_id"])
    output = tmp_path / "enterprise_strategy_kpis.json"
    published = publisher.write_enterprise_strategy_kpis_v21(payload, output)
    assert published == output
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["kpi_contract_version"] == "2.1"
    assert "trade_analytics" in stored
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
