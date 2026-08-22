import csv
import json
from pathlib import Path

from swing_trade_bot.manual_strategy_shadow_workflow import (
    AUTO_PROMOTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    CAPITAL_RESERVATION_ENABLED,
    SGOV_MOVEMENT_ENABLED,
    build_shadow_allocation_evidence,
)


def _registry(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.4",
        "paper_trade_mode": True,
        "default_strategy_id": None,
        "strategies": [{
            "strategy_id": "SHADOW_A", "name": "Shadow A", "timeframe": "1D",
            "rule_logic": "ALL", "rules": [{"left": "close", "operator": ">", "right": "ema", "period": 14}],
            "number_of_entries": 1, "enabled": True, "direction": "LONG", "session": "REGULAR_SESSION",
            "confirmation_bars": 1, "regime_logic": "ALL", "regime_filters": [],
            "normal_exit_logic": "ANY", "normal_exit_rules": [], "conditional_exits": [], "paper_trade_mode": True,
        }],
        "assignments": [{"underlying_symbol": "NFLX", "strategy_id": "SHADOW_A", "assignment_mode": "SHADOW", "enabled": True, "note": "research"}],
    }), encoding="utf-8")


def _mapping(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["underlying_symbol", "leveraged_symbol"])
        writer.writeheader()
        writer.writerow({"underlying_symbol": "NFLX", "leveraged_symbol": "NFLU"})


def _portfolio(path: Path) -> None:
    path.write_text(json.dumps({
        "paper_trade_mode": True,
        "allocations": [
            {"symbol": "SOXL", "confidence_level": "HIGH", "active_strategy": "Strategy A", "rank": None, "allocation_percent": 14.285714, "theme": "Unclassified", "cash_equivalent": ""},
            {"symbol": "TQQQ", "confidence_level": "HIGH", "active_strategy": "Strategy A", "rank": None, "allocation_percent": 14.285714, "theme": "Unclassified", "cash_equivalent": ""},
            {"symbol": "SGOV", "confidence_level": "RESERVE", "active_strategy": "", "rank": "", "allocation_percent": 71.428572, "theme": "Cash Equivalent", "cash_equivalent": "SGOV"},
        ],
    }), encoding="utf-8")


def _watchlist(path: Path) -> None:
    path.write_text(json.dumps({"rows": [{"underlying_symbol": "NFLX", "watchlist_status": "WATCHLIST", "watchlist_rank": 2, "themes": "Cloud"}]}), encoding="utf-8")


def _summary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paper_trade_mode": True, "account_capital": 4500.0}), encoding="utf-8")


def test_workflow_builds_hypothetical_shadow_allocation_without_reserving_capital(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    portfolio = tmp_path / "portfolio.json"
    watchlist = tmp_path / "watchlist.json"
    summary = tmp_path / "paper" / "summary.json"
    output = tmp_path / "shadow_allocations.json"
    _registry(registry); _mapping(mapping); _portfolio(portfolio); _watchlist(watchlist); _summary(summary)

    payload = build_shadow_allocation_evidence(
        registry_path=registry,
        mapping_path=mapping,
        portfolio_allocations_path=portfolio,
        watchlist_path=watchlist,
        paper_portfolio_summary_path=summary,
        output_path=output,
    )
    row = payload["rows"][0]
    assert row["evidence_status"] == "AVAILABLE"
    assert row["allocated_capital"] == 315.0
    assert row["allocation_percent"] == 7.0
    assert row["activation_level"] == "LOW"
    assert row["allocation_source"] == "HYPOTHETICAL_CURRENT_SWING_POLICY_LOW_ACTIVATION"
    assert row["capital_reserved"] is False
    assert payload["portfolio_allocations_modified"] is False
    assert output.is_file()


def test_workflow_has_no_capital_sgov_or_promotion_authority() -> None:
    assert CAPITAL_RESERVATION_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert SGOV_MOVEMENT_ENABLED is False
    assert AUTO_PROMOTION_ENABLED is False
