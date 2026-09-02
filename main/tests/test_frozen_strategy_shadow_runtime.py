import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import swing_trade_bot.frozen_strategy_shadow_runtime as runtime
from swing_trade_bot.frozen_ai_signal_engines import FrozenSignalDecision
from swing_trade_bot.frozen_strategy_shadow_runtime import FrozenStrategySpec, run_frozen_shadow_spec, simulate_frozen_strategy
from swing_trade_bot.intraday_chart_bars import IntradayBar

NY = ZoneInfo("America/New_York")


def _minute_rows(day: date, *, base: float = 100.0) -> list[IntradayBar]:
    start = datetime.combine(day, time(9, 30), tzinfo=NY)
    rows = []
    for i in range(390):
        price = base + i * 0.01
        rows.append(IntradayBar(start + timedelta(minutes=i), price, price + 0.1, price - 0.1, price, 1000.0))
    return rows


def _spec(*, stop: float | None = None) -> FrozenStrategySpec:
    return FrozenStrategySpec(
        strategy_id="SOXL_BIGBELUGA_1H",
        name="SOXL BigBeluga 1H",
        signal_symbol="SOXL",
        vehicle_symbol="SOXL",
        timeframe="1H",
        engine_id="BIGBELUGA_RANGE",
        parameters={"hma_entry": 0, "hma_exit": 90},
        catastrophic_stop_percent=stop,
    )


def test_frozen_spec_is_paper_only_and_validates_engine_timeframe() -> None:
    spec = _spec(stop=20.0)
    assert spec.paper_trade_mode is True
    assert runtime.PAPER_TRADE_MODE is True
    assert runtime.LIVE_TRADING_ENABLED is False
    assert runtime.BROKER_EXECUTION_ENABLED is False
    assert runtime.ORDER_PLACEMENT_ENABLED is False
    assert runtime.CAPITAL_MOVEMENT_ENABLED is False
    assert runtime.PAPER_POSITION_CREATION_ENABLED is False
    with pytest.raises(ValueError, match="1H or 4H"):
        FrozenStrategySpec("X", "x", "SOXL", "SOXL", "1D", "BIGBELUGA_RANGE", {})
    with pytest.raises(ValueError, match="unsupported frozen engine"):
        FrozenStrategySpec("X", "x", "SOXL", "SOXL", "1H", "LOOKALIKE", {})


def test_confirmed_entry_and_exit_execute_on_next_chart_bar_open(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _minute_rows(date(2026, 8, 3))

    def fake_engine(engine_id, parameters, bars):
        count = len(bars)
        return FrozenSignalDecision(
            entry_signal=count == 1,
            exit_signal=count == 3,
            engine_id=engine_id,
            diagnostics={"ready": True},
        )

    monkeypatch.setattr(runtime, "evaluate_frozen_signal", fake_engine)
    ledger, performance = simulate_frozen_strategy(_spec(), rows, rows, test_quantity=8.0)
    assert [row["event"] for row in ledger] == ["ENTRY", "EXIT"]
    assert ledger[0]["timestamp"].endswith("10:30:00-04:00")
    assert ledger[0]["entry_reason"] == "CONFIRMED_SIGNAL_NEXT_BAR_OPEN"
    assert ledger[1]["timestamp"].endswith("12:30:00-04:00")
    assert ledger[1]["exit_reason"] == "TECHNICAL_NEXT_BAR_OPEN"
    assert ledger[0]["shares"] == 8.0
    assert performance["shadow_test_quantity"] == 8.0
    assert performance["execution_timing"] == "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"


def test_raw_intraday_catastrophic_stop_preempts_later_technical_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _minute_rows(date(2026, 8, 3), base=100.0)
    # Entry occurs at 10:30. Force a raw minute low below the 20% stop during
    # the 10:30-11:29 bucket. The stop must close the Shadow before any later
    # technical signal can act.
    trigger_index = 90
    original = rows[trigger_index]
    rows[trigger_index] = IntradayBar(original.timestamp, 82.0, 83.0, 70.0, 82.0, original.volume)

    def fake_engine(engine_id, parameters, bars):
        return FrozenSignalDecision(len(bars) == 1, len(bars) == 4, engine_id, {"ready": True})

    monkeypatch.setattr(runtime, "evaluate_frozen_signal", fake_engine)
    ledger, performance = simulate_frozen_strategy(_spec(stop=20.0), rows, rows, test_quantity=5.0)
    assert ledger[0]["event"] == "ENTRY"
    assert ledger[1]["event"] == "EXIT"
    assert ledger[1]["exit_reason"] == "CATASTROPHIC_STOP_RAW_INTRADAY"
    assert ledger[1]["vehicle_price"] == pytest.approx(ledger[0]["vehicle_price"] * 0.8, rel=1e-6)
    assert performance["catastrophic_stop_authority"] == "RAW_INTRADAY_VEHICLE_ROWS"


def _write_intraday(path: Path, rows: list[IntradayBar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "timestamp": row.timestamp.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            })


def _write_positions(path: Path, shares: float = 8.04145854) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
        writer.writeheader()
        writer.writerow({"symbol": "SOXL", "shares": shares, "market_value": 0, "cost_basis": 0})


def test_runtime_uses_current_primary_share_quantity_and_fails_closed_without_data(tmp_path: Path) -> None:
    signal = tmp_path / "SOXL_1min.csv"
    positions = tmp_path / "positions.csv"
    missing = run_frozen_shadow_spec(
        _spec(),
        signal_intraday_path=signal,
        vehicle_intraday_path=signal,
        primary_positions_path=positions,
    )
    assert missing["evidence_status"] == "MISSING_INTRADAY_MARKET_DATA"

    _write_intraday(signal, _minute_rows(date(2026, 8, 3)))
    no_quantity = run_frozen_shadow_spec(
        _spec(),
        signal_intraday_path=signal,
        vehicle_intraday_path=signal,
        primary_positions_path=positions,
    )
    assert no_quantity["evidence_status"] == "MISSING_PRIMARY_SHARE_QUANTITY"

    _write_positions(positions)
    result = run_frozen_shadow_spec(
        _spec(),
        signal_intraday_path=signal,
        vehicle_intraday_path=signal,
        primary_positions_path=positions,
    )
    assert result["paper_trade_mode"] is True
    assert result["capital_movement_enabled"] is False
    assert result["paper_positions_created"] == 0
    assert result["performance"]["primary_reference_quantity"] == 8.04145854
    assert result["performance"]["shadow_test_quantity"] == 8.04145854
    assert result["performance"]["sizing_basis"] == "PRIMARY_SHARE_QUANTITY"
