from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.enterprise_strategy_kpi_publisher import (
    CAPABILITIES,
    build_enterprise_strategy_kpis,
    validate_enterprise_strategy_kpis,
    write_enterprise_strategy_kpis,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _safe(**values):
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
        **values,
    }


def _swing_allocation(amount: float = 4500.0) -> dict:
    return {"strategy_allocations": {"SWING-001": amount}}


def _full_results(root: Path) -> None:
    _write(root / "portfolio_allocations.json", {"allocations": []})
    _write(
        root / "paper_ledger" / "paper_portfolio_summary.json",
        _safe(
            valuation_source="PAPER_LEDGER_MARK_TO_MARKET",
            account_capital=4500.0,
            portfolio_value=4575.0,
            cash_balance=2700.0,
            invested_capital=1800.0,
            positions_market_value=1875.0,
            unrealized_pnl=75.0,
            portfolio_return_percent=1.666667,
            position_count=2,
        ),
    )
    _write(
        root / "paper_ledger" / "paper_portfolio_positions.json",
        _safe(
            positions=[
                {
                    "symbol": "TQQQ",
                    "shares": 5.0,
                    "entry_price": 100.0,
                    "current_price": 105.0,
                    "market_value": 525.0,
                    "unrealized_pnl": 25.0,
                    "unrealized_pnl_percent": 5.0,
                    "active_strategy": "Strategy A",
                },
                {
                    "symbol": "SOXL",
                    "shares": 10.0,
                    "entry_price": 130.0,
                    "current_price": 135.0,
                    "market_value": 1350.0,
                    "unrealized_pnl": 50.0,
                    "unrealized_pnl_percent": 3.846154,
                    "active_strategy": "Strategy B",
                },
            ]
        ),
    )
    _write(
        root / "paper_ledger" / "trade_history_summary.json",
        _safe(total_trade_events=6, closed_trade_count=2, realized_pnl=50.0),
    )
    _write(
        root / "paper_ledger" / "paper_performance.json",
        _safe(
            evidence_status="AVAILABLE",
            total_trade_events=6,
            closed_trade_count=2,
            realized_pnl=50.0,
            unrealized_pnl=75.0,
            total_pnl=125.0,
            win_rate_percent=50.0,
            portfolio_return_percent=2.777778,
        ),
    )
    _write(root / "opportunity_quality.json", {"opportunity_quality_score": 82.5})
    _write(root / "watchlist_report.json", {"watchlist": [{"symbol": "AMD"}, {"symbol": "NVDA"}]})


def test_v2_publishes_portfolio_holdings_performance_and_strategy_evidence(tmp_path: Path):
    _full_results(tmp_path)
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations=_swing_allocation(),
    )

    assert payload["kpi_contract_version"] == "2.0"
    assert payload["portfolio_value_source"] == "PAPER_LEDGER_MARK_TO_MARKET"
    assert payload["portfolio_value"] == 4575.0
    assert payload["position_count"] == 2
    assert [row["symbol"] for row in payload["open_positions"]] == ["SOXL", "TQQQ"]
    assert payload["trade_count"] == 6
    assert payload["closed_trade_count"] == 2
    assert payload["win_rate_percent"] == 50.0
    assert payload["realized_pnl"] == 50.0
    assert payload["total_pnl"] == 125.0
    assert payload["opportunity_quality"] == 82.5
    assert payload["watchlist_count"] == 2
    assert payload["evidence_status"] == "AVAILABLE"
    assert validate_enterprise_strategy_kpis(payload) == ()


def test_capabilities_are_deterministic_sorted_and_unique(tmp_path: Path):
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations=_swing_allocation(),
    )
    assert payload["capabilities"] == sorted(set(CAPABILITIES))


def test_missing_optional_analytics_are_disclosed_not_fabricated(tmp_path: Path):
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations=_swing_allocation(),
    )
    assert payload["evidence_status"] == "PARTIAL"
    assert payload["win_rate_percent"] is None
    assert payload["realized_pnl"] is None
    assert payload["open_positions"] == []
    assert any("Performance analytics" in warning for warning in payload["warnings"])


def test_unsafe_performance_evidence_is_rejected(tmp_path: Path):
    _full_results(tmp_path)
    performance = json.loads((tmp_path / "paper_ledger" / "paper_performance.json").read_text())
    performance["broker_execution_enabled"] = True
    _write(tmp_path / "paper_ledger" / "paper_performance.json", performance)
    with pytest.raises(ValueError, match="unsafe value"):
        build_enterprise_strategy_kpis(
            tmp_path,
            strategy_allocations=_swing_allocation(),
        )


def test_ledger_capital_cannot_use_total_account_capital(tmp_path: Path):
    _full_results(tmp_path)
    summary = json.loads((tmp_path / "paper_ledger" / "paper_portfolio_summary.json").read_text())
    summary["account_capital"] = 10000.0
    _write(tmp_path / "paper_ledger" / "paper_portfolio_summary.json", summary)
    with pytest.raises(ValueError, match="SWING-001 allocation"):
        build_enterprise_strategy_kpis(
            tmp_path,
            strategy_allocations=_swing_allocation(),
        )


def test_atomic_publication_and_v2_validation(tmp_path: Path):
    _full_results(tmp_path)
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations=_swing_allocation(),
    )
    output = write_enterprise_strategy_kpis(payload, tmp_path / "enterprise_strategy_kpis.json")
    assert output.exists()
    assert not list(tmp_path.glob("*.tmp"))
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["kpi_contract_version"] == "2.0"


def test_unsafe_top_level_safety_values_are_rejected(tmp_path: Path):
    payload = build_enterprise_strategy_kpis(
        tmp_path,
        strategy_allocations=_swing_allocation(),
    )
    payload["live_trading_enabled"] = True
    assert "live_trading_enabled must be false" in validate_enterprise_strategy_kpis(payload)


def test_no_dividend_production_imports_exist():
    source = Path("src/swing_trade_bot/enterprise_strategy_kpi_publisher.py").read_text(encoding="utf-8").lower()
    assert "trade_dividend_bot" not in source
    assert "trade-dividend-bot" not in source
    assert "import dividend" not in source
    assert "from dividend" not in source
