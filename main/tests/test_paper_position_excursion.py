from datetime import date
from pathlib import Path

import pytest

from swing_trade_bot.paper_position_excursion import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    DIRECT_DATABASE_WRITES,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    calculate_long_position_excursion,
)


def _write_csv(path: Path, rows: list[tuple[str, float, float | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "Date,Open,High,Low,Close,Adj Close,Volume\n"
    for day, close, adjusted in rows:
        adj = "" if adjusted is None else str(adjusted)
        text += f"{day},{close},{close},{close},{close},{adj},1000\n"
    path.write_text(text, encoding="utf-8")


def test_calculates_peak_to_trough_drawdown_from_completed_history(tmp_path: Path) -> None:
    path = tmp_path / "AAA.csv"
    _write_csv(
        path,
        [
            ("2026-08-01", 100.0, 100.0),
            ("2026-08-02", 120.0, 120.0),
            ("2026-08-03", 90.0, 90.0),
            ("2026-08-04", 110.0, 110.0),
        ],
    )

    evidence = calculate_long_position_excursion(
        market_data_path=path,
        entry_date=date(2026, 8, 1),
        as_of=date(2026, 8, 4),
        normalized_entry_price=100.0,
        normalized_shares=10.0,
    )

    assert evidence is not None
    assert evidence.max_drawdown_amount == 300.0
    assert evidence.max_drawdown_percent == 25.0
    assert evidence.max_drawdown_peak_price == 120.0
    assert evidence.max_drawdown_peak_date == "2026-08-02"
    assert evidence.max_drawdown_trough_price == 90.0
    assert evidence.max_drawdown_trough_date == "2026-08-03"


def test_future_bars_are_excluded(tmp_path: Path) -> None:
    path = tmp_path / "AAA.csv"
    _write_csv(
        path,
        [
            ("2026-08-01", 100.0, 100.0),
            ("2026-08-02", 110.0, 110.0),
            ("2026-08-10", 10.0, 10.0),
        ],
    )

    evidence = calculate_long_position_excursion(
        market_data_path=path,
        entry_date=date(2026, 8, 1),
        as_of=date(2026, 8, 2),
        normalized_entry_price=100.0,
        normalized_shares=10.0,
    )

    assert evidence is not None
    assert evidence.max_drawdown_amount == 0.0
    assert evidence.max_drawdown_percent == 0.0


def test_truncated_history_returns_none_instead_of_understating_drawdown(tmp_path: Path) -> None:
    path = tmp_path / "AAA.csv"
    _write_csv(
        path,
        [
            ("2026-08-03", 90.0, 90.0),
            ("2026-08-04", 110.0, 110.0),
        ],
    )

    assert calculate_long_position_excursion(
        market_data_path=path,
        entry_date=date(2026, 8, 1),
        as_of=date(2026, 8, 4),
        normalized_entry_price=100.0,
        normalized_shares=10.0,
    ) is None


def test_adjusted_close_is_used_when_available(tmp_path: Path) -> None:
    path = tmp_path / "AAA.csv"
    _write_csv(
        path,
        [
            ("2026-08-01", 200.0, 100.0),
            ("2026-08-02", 240.0, 120.0),
            ("2026-08-03", 180.0, 90.0),
        ],
    )

    evidence = calculate_long_position_excursion(
        market_data_path=path,
        entry_date=date(2026, 8, 1),
        as_of=date(2026, 8, 3),
        normalized_entry_price=100.0,
        normalized_shares=20.0,
    )

    assert evidence is not None
    assert evidence.max_drawdown_percent == 25.0
    assert evidence.max_drawdown_amount == 600.0


def test_paper_safety_constants_are_locked() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert DIRECT_DATABASE_WRITES is False
    source = Path("src/swing_trade_bot/paper_position_excursion.py").read_text(encoding="utf-8").lower()
    assert "robinhood" not in source
    assert "place_order" not in source
    assert "trade_dividend_bot" not in source
