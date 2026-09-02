from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from swing_trade_bot.intraday_chart_bars import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    IntradayBar,
    build_chart_bars,
    load_intraday_csv,
    regular_session_rows,
)

NY = ZoneInfo("America/New_York")


def _bar(ts: datetime, price: float, *, volume: float = 100.0) -> IntradayBar:
    return IntradayBar(
        timestamp=ts,
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        close=price + 0.5,
        volume=volume,
    )


def test_regular_session_excludes_premarket_and_after_hours() -> None:
    day = datetime(2026, 9, 1, tzinfo=NY)
    rows = [
        _bar(day.replace(hour=9, minute=29), 100),
        _bar(day.replace(hour=9, minute=30), 101),
        _bar(day.replace(hour=15, minute=59), 102),
        _bar(day.replace(hour=16, minute=0), 103),
    ]
    kept = regular_session_rows(rows)
    assert [bar.timestamp.time().strftime("%H:%M") for bar in kept] == ["09:30", "15:59"]


def test_one_hour_bars_are_anchored_at_0930_and_keep_final_partial_hour() -> None:
    start = datetime(2026, 9, 1, 9, 30, tzinfo=NY)
    rows = [_bar(start + timedelta(minutes=minute), 100 + minute / 100.0) for minute in range(390)]
    bars = build_chart_bars(rows, "1H")

    assert [bar.timestamp.strftime("%H:%M") for bar in bars] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"
    ]
    assert len(bars) == 7
    assert bars[0].open == rows[0].open
    assert bars[0].close == rows[59].close
    assert bars[-1].close == rows[-1].close
    assert bars[-1].volume == pytest.approx(30 * 100.0)


def test_four_hour_bars_match_frozen_stock_contract() -> None:
    start = datetime(2026, 9, 1, 9, 30, tzinfo=NY)
    rows = [_bar(start + timedelta(minutes=minute), 100 + minute / 100.0) for minute in range(390)]
    bars = build_chart_bars(rows, "4H")

    assert [bar.timestamp.strftime("%H:%M") for bar in bars] == ["09:30", "13:30"]
    assert len(bars) == 2
    assert bars[0].close == rows[239].close
    assert bars[1].open == rows[240].open
    assert bars[1].close == rows[-1].close
    assert bars[0].volume == pytest.approx(240 * 100.0)
    assert bars[1].volume == pytest.approx(150 * 100.0)


def test_daily_bar_uses_only_full_regular_session() -> None:
    day = datetime(2026, 9, 1, tzinfo=NY)
    rows = [_bar(day.replace(hour=8, minute=0), 50)]
    start = day.replace(hour=9, minute=30)
    rows.extend(_bar(start + timedelta(minutes=minute), 100 + minute / 100.0) for minute in range(390))
    rows.append(_bar(day.replace(hour=16, minute=30), 200))

    bars = build_chart_bars(rows, "1D")
    assert len(bars) == 1
    assert bars[0].timestamp.strftime("%H:%M") == "09:30"
    assert bars[0].open == rows[1].open
    assert bars[0].close == rows[-2].close


def test_intraday_csv_loader_accepts_naive_and_offset_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-09-01T09:30:00,100,101,99,100.5,10\n"
        "2026-09-01T13:31:00+00:00,101,102,100,101.5,20\n",
        encoding="utf-8",
    )
    rows = load_intraday_csv(path)
    assert rows[0].timestamp.tzinfo is not None
    assert rows[0].timestamp.strftime("%H:%M") == "09:30"
    assert rows[1].timestamp.strftime("%H:%M") == "09:31"


def test_intraday_support_is_paper_only() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
