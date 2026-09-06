import json
from pathlib import Path

from swing_trade_bot.shadow_hypothetical_allocation import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    CAPITAL_RESERVATION_ENABLED,
    FIRST_FUNDED_LIFECYCLE_LEVEL,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    PORTFOLIO_ALLOCATION_WRITE_ENABLED,
    resolve_shadow_allocation,
)


def _allocation(path: Path, *, include_nflu: bool = False) -> None:
    rows = [
        {"symbol": "SOXL", "confidence_level": "HIGH", "active_strategy": "Strategy A", "rank": None, "allocation_percent": 14.285714, "theme": "Unclassified", "theme_allocation": 28.571428, "cash_equivalent": ""},
        {"symbol": "TQQQ", "confidence_level": "HIGH", "active_strategy": "Strategy A", "rank": None, "allocation_percent": 14.285714, "theme": "Unclassified", "theme_allocation": 28.571428, "cash_equivalent": ""},
    ]
    if include_nflu:
        rows.append({"symbol": "NFLU", "confidence_level": "LOW", "active_strategy": "Manual", "rank": 2, "allocation_percent": 7.0, "theme": "AI", "theme_allocation": 7.0, "cash_equivalent": ""})
    rows.append({"symbol": "SGOV", "confidence_level": "RESERVE", "active_strategy": "", "rank": "", "allocation_percent": 71.428572 if not include_nflu else 64.428572, "theme": "Cash Equivalent", "theme_allocation": 71.428572, "cash_equivalent": "SGOV"})
    path.write_text(json.dumps({"paper_trade_mode": True, "allocations": rows}), encoding="utf-8")


def _watchlist(path: Path) -> None:
    path.write_text(json.dumps({"rows": [{"underlying_symbol": "NFLX", "leveraged_symbol": "NFLU", "watchlist_status": "WATCHLIST", "watchlist_rank": 2, "themes": "AI;Cloud"}]}), encoding="utf-8")


def _summary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paper_trade_mode": True, "account_capital": 4500.0, "account_capital_source": "AI_CIO_ENTERPRISE_EVIDENCE"}), encoding="utf-8")


def test_current_funded_allocation_is_used_exactly(tmp_path: Path) -> None:
    allocations = tmp_path / "alloc.json"
    watchlist = tmp_path / "watch.json"
    summary = tmp_path / "paper" / "summary.json"
    _allocation(allocations, include_nflu=True)
    _watchlist(watchlist)
    _summary(summary)

    result = resolve_shadow_allocation(
        underlying_symbol="NFLX",
        vehicle_symbol="NFLU",
        portfolio_allocations_path=allocations,
        watchlist_path=watchlist,
        paper_portfolio_summary_path=summary,
    )
    assert result.allocation_percent == 7.0
    assert result.simulated_allocation == 315.0
    assert result.allocation_source == "CURRENT_FUNDED_SWING_ALLOCATION"
    assert result.capital_reserved is False


def test_unfunded_watchlist_uses_existing_allocator_at_low_activation(tmp_path: Path) -> None:
    allocations = tmp_path / "alloc.json"
    watchlist = tmp_path / "watch.json"
    summary = tmp_path / "paper" / "summary.json"
    _allocation(allocations)
    _watchlist(watchlist)
    _summary(summary)

    result = resolve_shadow_allocation(
        underlying_symbol="NFLX",
        vehicle_symbol="NFLU",
        portfolio_allocations_path=allocations,
        watchlist_path=watchlist,
        paper_portfolio_summary_path=summary,
    )
    assert result.activation_level == "LOW"
    assert result.allocation_percent == 7.0
    assert result.simulated_allocation == 315.0
    assert result.allocation_source == "HYPOTHETICAL_CURRENT_SWING_POLICY_LOW_ACTIVATION"
    assert result.capital_reserved is False


def test_resolver_has_no_capital_or_execution_authority() -> None:
    assert FIRST_FUNDED_LIFECYCLE_LEVEL == "LOW"
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert CAPITAL_RESERVATION_ENABLED is False
    assert PORTFOLIO_ALLOCATION_WRITE_ENABLED is False
