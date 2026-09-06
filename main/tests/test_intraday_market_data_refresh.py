from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from swing_trade_bot.intraday_chart_bars import IntradayBar, load_intraday_csv
from swing_trade_bot.intraday_market_data_refresh import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    ROBINHOOD_MARKET_DATA_ENABLED,
    merge_intraday_archive,
    refresh_intraday_market_data,
)

NY = ZoneInfo("America/New_York")


def _config(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "strategies": [
            {
                "strategy_id": "P",
                "name": "P",
                "signal_symbol": "SOXL",
                "vehicle_symbol": "SOXL",
                "timeframe": "1H",
                "engine_id": "ZERO_LAG",
                "parameters": {"length": 10, "multiplier": 1.0},
                "assignment_mode": "DIRECT",
                "paper_trade_mode": True,
            }
        ],
        "symbols": [{"symbol": "SOXL", "primary_strategy_id": "P", "shadow_strategy_ids": []}],
    }), encoding="utf-8")


def _minute_rows(day: datetime, count: int = 390, start_price: float = 100.0) -> tuple[IntradayBar, ...]:
    rows = []
    for i in range(count):
        stamp = day.replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(minutes=i)
        price = start_price + (i * 0.01)
        rows.append(IntradayBar(stamp, price, price + 0.2, price - 0.2, price + 0.05, 1000 + i))
    return tuple(rows)


def test_merge_preserves_old_history_and_replaces_overlap() -> None:
    first_day = datetime(2026, 8, 31, tzinfo=NY)
    second_day = datetime(2026, 9, 1, tzinfo=NY)
    existing = _minute_rows(first_day, 2, 100.0) + _minute_rows(second_day, 1, 110.0)
    replacement = IntradayBar(second_day.replace(hour=9, minute=30), 120.0, 121.0, 119.0, 120.5, 2000)
    recent = (replacement, IntradayBar(second_day.replace(hour=9, minute=31), 121.0, 122.0, 120.0, 121.5, 2100))

    merged = merge_intraday_archive(existing, recent)

    assert len(merged) == 4
    assert merged[0].timestamp.date().isoformat() == "2026-08-31"
    replaced = [row for row in merged if row.timestamp == replacement.timestamp][0]
    assert replaced.open == 120.0


def test_refresh_writes_timestamped_archive_and_status(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    data = tmp_path / "intraday"
    status = tmp_path / "status.json"
    _config(config)
    rows = _minute_rows(datetime(2026, 9, 1, tzinfo=NY))

    payload = refresh_intraday_market_data(
        config_path=config,
        data_dir=data,
        status_path=status,
        fetch_recent=lambda symbol: rows,
        generated_at_utc="2026-09-02T17:00:00Z",
    )

    assert payload["status"] == "AVAILABLE"
    assert payload["provider"] == "YFINANCE"
    assert payload["interval"] == "1m"
    assert status.is_file()
    archive = data / "SOXL.csv"
    assert archive.is_file()
    loaded = load_intraday_csv(archive)
    assert len(loaded) == 390
    assert loaded[0].timestamp.hour == 9 and loaded[0].timestamp.minute == 30
    saved = json.loads(status.read_text(encoding="utf-8"))
    assert saved["symbols"][0]["session_row_counts"]["2026-09-01"] == 390


def test_refresh_appends_new_session_without_losing_old_session(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    data = tmp_path / "intraday"
    _config(config)
    day1 = _minute_rows(datetime(2026, 8, 31, tzinfo=NY))
    day2 = _minute_rows(datetime(2026, 9, 1, tzinfo=NY), start_price=150.0)

    refresh_intraday_market_data(
        config_path=config,
        data_dir=data,
        status_path=tmp_path / "status1.json",
        fetch_recent=lambda symbol: day1,
    )
    refresh_intraday_market_data(
        config_path=config,
        data_dir=data,
        status_path=tmp_path / "status2.json",
        fetch_recent=lambda symbol: day2,
    )

    loaded = load_intraday_csv(data / "SOXL.csv")
    assert len(loaded) == 780
    assert loaded[0].timestamp.date().isoformat() == "2026-08-31"
    assert loaded[-1].timestamp.date().isoformat() == "2026-09-01"


def test_provider_failure_preserves_existing_archive_and_fails_closed(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    data = tmp_path / "intraday"
    _config(config)
    day1 = _minute_rows(datetime(2026, 8, 31, tzinfo=NY))
    refresh_intraday_market_data(
        config_path=config,
        data_dir=data,
        status_path=tmp_path / "ok.json",
        fetch_recent=lambda symbol: day1,
    )

    def fail(symbol: str):
        raise RuntimeError("provider unavailable")

    payload = refresh_intraday_market_data(
        config_path=config,
        data_dir=data,
        status_path=tmp_path / "blocked.json",
        fetch_recent=fail,
    )

    assert payload["status"] == "BLOCKED"
    row = payload["symbols"][0]
    assert row["status"] == "BLOCKED"
    assert row["existing_rows"] == 390
    assert len(load_intraday_csv(data / "SOXL.csv")) == 390


def test_intraday_refresh_is_paper_only() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert ROBINHOOD_MARKET_DATA_ENABLED is False
