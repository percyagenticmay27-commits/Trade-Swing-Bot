from datetime import date
from pathlib import Path

from swing_trade_bot.discovery_engine import CandidateState, DiscoveryEngine, FinancialHealth, load_candidates


def _health(value: float) -> FinancialHealth:
    return FinancialHealth(value, value, value, value, value, value, value)


def _candidate_map() -> dict[str, CandidateState]:
    path = Path(__file__).resolve().parents[1] / "examples" / "discovery_candidates.csv"
    return {row.underlying_symbol: row for row in load_candidates(path)}


def test_be_resolves_to_bex_and_declares_vehicle_available() -> None:
    candidates = _candidate_map()
    be = candidates["BE"]

    assert be.leveraged_symbol == "BEX"
    assert be.leveraged_vehicle_exists is True


def test_be_is_not_removed_only_for_missing_vehicle_metadata() -> None:
    be = _candidate_map()["BE"]
    row = DiscoveryEngine(paper_trade_mode=True).evaluate(
        [be],
        [],
        {"BE": _health(62.14)},
        as_of=date(2026, 8, 14),
    )[0]

    assert row.leveraged_symbol == "BEX"
    assert row.watchlist_status == "DISCOVERY"
    assert row.capacity_status == "ACTIVE"


def test_genuinely_unsupported_candidate_remains_removed() -> None:
    unsupported = CandidateState(
        underlying_symbol="UNSUPPORTED",
        leveraged_symbol=None,
        leveraged_vehicle_exists=False,
    )
    row = DiscoveryEngine(paper_trade_mode=True).evaluate(
        [unsupported],
        [],
        {"UNSUPPORTED": _health(80.0)},
        as_of=date(2026, 8, 14),
    )[0]

    assert row.watchlist_status == "REMOVED"
    assert row.capacity_status == "REMOVED"


def test_existing_nbis_and_iren_vehicle_mappings_are_unchanged() -> None:
    candidates = _candidate_map()

    assert candidates["NBIS"].leveraged_symbol == "NEBX"
    assert candidates["NBIS"].leveraged_vehicle_exists is True
    assert candidates["IREN"].leveraged_symbol == "IREL"
    assert candidates["IREN"].leveraged_vehicle_exists is True
