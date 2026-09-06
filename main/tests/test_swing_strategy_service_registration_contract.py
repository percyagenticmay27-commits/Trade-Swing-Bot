import json
from pathlib import Path


REGISTRATION = Path("configs/swing_strategy_service_registration.json")
EXPECTED_ROOT = "/home/tradebot/Trade-Swing-Bot/main"
EXPECTED_ARTIFACTS = {
    "daily_cycle_status": "results/swing_daily_cycle_report.json",
    "executive_dashboard": "results/executive_dashboard.json",
    "manual_entry_strategy_form_contract": "results/manual_entry_strategy_form_contract.json",
    "market_data_status": "results/market_data_refresh_status.json",
    "monthly_command_center": "results/monthly_command_center.json",
    "opportunity_quality": "results/opportunity_quality_report.json",
    "portfolio_allocations": "results/portfolio_allocations.json",
    "position_lifecycle": "results/trade_lifecycle_report.json",
    "stock_performance": "results/stock_performance_report.json",
    "strategy_kpis": "results/enterprise_strategy_kpis.json",
    "swing_strategy_alerts_report": "results/swing_strategy_alerts_report.json",
    "swing_decision_journal_report": "results/swing_decision_journal_report.json",
    "swing_trade_analytics_report": "results/swing_trade_analytics_report.json",
    "watchlist": "results/watchlist_report.json",
    "weekly_stock_report": "results/weekly_stock_report.json",
}


def _registration() -> dict:
    return json.loads(REGISTRATION.read_text(encoding="utf-8"))


def test_registration_declares_authoritative_repository_root_and_relative_paths():
    payload = _registration()
    assert payload["strategy_id"] == "SWING-001"
    assert payload["repository_root"] == EXPECTED_ROOT

    artifacts = {
        row["artifact_id"]: row["path"]
        for row in payload["dashboard_artifacts"]
    }
    assert artifacts == EXPECTED_ARTIFACTS
    assert all(not Path(path).is_absolute() for path in artifacts.values())
    assert all(path.startswith("results/") for path in artifacts.values())


def test_registration_does_not_declare_unproduced_portfolio_risk_placeholder():
    payload = _registration()
    assert "portfolio_risk" not in payload["capabilities"]
    assert all(row["artifact_id"] != "portfolio_risk" for row in payload["dashboard_artifacts"])


def test_registration_uses_authentic_trade_lifecycle_producer_path():
    payload = _registration()
    artifacts = {row["artifact_id"]: row["path"] for row in payload["dashboard_artifacts"]}
    assert artifacts["position_lifecycle"] == "results/trade_lifecycle_report.json"


def test_registration_safety_flags_are_locked_for_paper_only_operation():
    payload = _registration()
    assert payload["paper_trade_mode"] is True
    assert payload["paper_compatible"] is True
    assert payload["advisory_only"] is True
    assert payload["reporting_only"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["automatic_activation_allowed"] is False
    assert payload["direct_database_writes"] is False


def test_registration_declares_only_paths_inside_swing_repository_contract():
    payload = _registration()
    for row in payload["dashboard_artifacts"]:
        relative = Path(row["path"])
        assert ".." not in relative.parts
        assert row["scope"] == "STRATEGY"
        assert row["authoritative"] is True
        assert row["format"].lower() == "json"
