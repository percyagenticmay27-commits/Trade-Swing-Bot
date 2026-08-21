from __future__ import annotations

from datetime import date

from swing_trade_bot.discovery_engine import CandidateState, DiscoveryEngine, FinancialHealth


AS_OF = date(2026, 8, 21)


def _healthy(score: float = 80.0) -> FinancialHealth:
    return FinancialHealth(
        revenue_growth=score,
        eps_growth=score,
        operating_cash_flow=score,
        gross_margin_trend=score,
        debt_health=score,
        analyst_revisions=score,
        sector_strength=score,
    )


def test_stale_watchlist_candidate_with_valid_mapping_returns_to_monitor_not_removed() -> None:
    engine = DiscoveryEngine()
    candidate = CandidateState(
        underlying_symbol="AMD",
        leveraged_symbol="AMDL",
        status="WATCHLIST",
        days_in_status=90,
        leveraged_vehicle_exists=True,
    )

    row = engine.evaluate([candidate], [], {"AMD": _healthy()}, as_of=AS_OF)[0]

    assert row.watchlist_status == "MONITOR"
    assert row.capacity_status == "ACTIVE"
    assert row.leveraged_symbol == "AMDL"


def test_removed_is_reserved_for_missing_or_unavailable_leveraged_vehicle() -> None:
    engine = DiscoveryEngine()
    unavailable = CandidateState(
        underlying_symbol="AMD",
        leveraged_symbol="AMDL",
        status="WATCHLIST",
        days_in_status=90,
        leveraged_vehicle_exists=False,
    )
    missing = CandidateState(
        underlying_symbol="NVDA",
        leveraged_symbol=None,
        status="WATCHLIST",
        days_in_status=90,
        leveraged_vehicle_exists=False,
    )
    unavailable_low = CandidateState(
        underlying_symbol="PLTR",
        leveraged_symbol="PLTU",
        status="LOW",
        days_in_status=20,
        leveraged_vehicle_exists=False,
    )

    rows = engine.evaluate(
        [unavailable, missing, unavailable_low],
        [],
        {"AMD": _healthy(), "NVDA": _healthy(), "PLTR": _healthy()},
        as_of=AS_OF,
    )
    by_symbol = {row.underlying_symbol: row for row in rows}

    assert by_symbol["AMD"].watchlist_status == "REMOVED"
    assert by_symbol["AMD"].capacity_status == "REMOVED"
    assert by_symbol["NVDA"].watchlist_status == "REMOVED"
    assert by_symbol["NVDA"].capacity_status == "REMOVED"
    assert by_symbol["PLTR"].watchlist_status == "REMOVED"
    assert by_symbol["PLTR"].capacity_status == "REMOVED"


def test_monitor_candidate_with_valid_mapping_can_requalify_for_watchlist() -> None:
    from swing_trade_bot.discovery_engine import SourceMention

    engine = DiscoveryEngine()
    candidate = CandidateState(
        underlying_symbol="AMD",
        leveraged_symbol="AMDL",
        status="MONITOR",
        leveraged_vehicle_exists=True,
    )
    mentions = [
        SourceMention("AMD", "Bloomberg", AS_OF),
        SourceMention("AMD", "Reuters", AS_OF),
    ]

    row = engine.evaluate([candidate], mentions, {"AMD": _healthy()}, as_of=AS_OF)[0]

    assert row.watchlist_status == "WATCHLIST"
    assert row.leveraged_symbol == "AMDL"
