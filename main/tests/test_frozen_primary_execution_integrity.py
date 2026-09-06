from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import swing_trade_bot.frozen_primary_signal_execution_workflow as workflow
from swing_trade_bot.intraday_chart_bars import IntradayBar


NY = ZoneInfo("America/New_York")


def _bar(h, m, o=100.0, hi=101.0, lo=99.0, c=100.0):
    return IntradayBar(
        timestamp=datetime(2026, 9, 1, h, m, tzinfo=NY),
        open=o,
        high=hi,
        low=lo,
        close=c,
        volume=1000.0,
    )


def _write_open_position(path: Path, *, entry=100.0, strategy_id="TEST_PRIMARY") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "open_positions.json").write_text(
        '{"paper_trade_mode":true,"positions":[{'
        f'"symbol":"NFLU","entry_price":{entry},"active_strategy":"{strategy_id}"'
        '}]}',
        encoding="utf-8",
    )


def test_sparse_next_open_uses_actual_first_vehicle_print(monkeypatch, tmp_path):
    primary = SimpleNamespace(
        strategy_id="TEST_PRIMARY",
        engine_id="ZERO_LAG",
        parameters={},
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
        catastrophic_stop_percent=20.0,
    )
    signal_bars = [_bar(9, 30), _bar(10, 30), _bar(11, 30)]
    vehicle_bars = [_bar(9, 30), _bar(10, 30), _bar(11, 30)]
    raw = [
        _bar(10, 32, 20.0, 20.2, 19.9, 20.1),
        _bar(11, 47, 21.0, 21.2, 20.9, 21.1),
    ]
    state = {
        "last_processed_chart_bar": signal_bars[0].timestamp.isoformat(),
        "last_processed_stop_raw_bar": raw[-1].timestamp.isoformat(),
        "pending_signal": None,
        "allocation_notional": 1000.0,
    }

    class Decision:
        entry_signal = True
        exit_signal = False

    monkeypatch.setattr(workflow, "evaluate_frozen_signal", lambda *args, **kwargs: Decision())
    monkeypatch.setattr(workflow, "_process_catastrophic_stop_bucket", lambda **kwargs: None)
    monkeypatch.setattr(workflow, "_has_open_position", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        workflow,
        "execute_frozen_primary_event",
        lambda event, **kwargs: {
            "side": event.side,
            "execution_timestamp": event.execution_timestamp,
            "price": event.price,
        },
    )

    result = workflow._process_symbol(
        symbol="NFLU",
        primary=primary,
        signal_chart_bars=signal_bars,
        completed_signal_bars=[signal_bars[1]],
        vehicle_chart_bars=vehicle_bars,
        vehicle_raw_rows=raw,
        ledger_dir=tmp_path / "ledger",
        config_path=tmp_path / "config.json",
        symbol_state=state,
    )

    event = result["executed_events"][0]
    assert event["execution_timestamp"] == "2026-09-01T11:47:00-04:00"
    assert event["price"] == 21.0
    assert result["execution_timing"] == "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"


def test_strategy_f_primary_executes_at_observed_signal_bucket_close(monkeypatch, tmp_path):
    primary = SimpleNamespace(
        strategy_id="TEST_PRIMARY",
        engine_id="STRATEGY_F",
        parameters={},
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
        catastrophic_stop_percent=20.0,
    )
    signal_bars = [_bar(9, 30), _bar(10, 30)]
    vehicle_bars = [_bar(9, 30), _bar(10, 30)]
    raw = [
        _bar(10, 32, 20.0, 20.2, 19.9, 20.1),
        _bar(11, 29, 21.0, 21.3, 20.8, 21.25),
    ]
    state = {
        "last_processed_chart_bar": signal_bars[0].timestamp.isoformat(),
        "last_processed_stop_raw_bar": raw[-1].timestamp.isoformat(),
        "pending_signal": None,
        "allocation_notional": 1000.0,
    }

    class Decision:
        entry_signal = True
        exit_signal = False

    monkeypatch.setattr(workflow, "evaluate_frozen_signal", lambda *args, **kwargs: Decision())
    monkeypatch.setattr(workflow, "_process_catastrophic_stop_bucket", lambda **kwargs: None)
    monkeypatch.setattr(workflow, "_has_open_position", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        workflow,
        "execute_frozen_primary_event",
        lambda event, **kwargs: {
            "side": event.side,
            "execution_timestamp": event.execution_timestamp,
            "price": event.price,
            "reason": event.reason,
        },
    )

    result = workflow._process_symbol(
        symbol="NFLU",
        primary=primary,
        signal_chart_bars=signal_bars,
        completed_signal_bars=[signal_bars[1]],
        vehicle_chart_bars=vehicle_bars,
        vehicle_raw_rows=raw,
        ledger_dir=tmp_path / "ledger",
        config_path=tmp_path / "config.json",
        symbol_state=state,
    )

    event = result["executed_events"][0]
    assert event["execution_timestamp"] == "2026-09-01T11:29:00-04:00"
    assert event["price"] == 21.25
    assert event["reason"] == "FROZEN_DIRECT_PRIMARY_CONFIRMED_ENTRY_BAR_CLOSE"
    assert result["pending_signal"] is None
    assert result["execution_timing"] == "CONFIRMED_SIGNAL_BAR_CLOSE"


def test_standard_profit_protection_sells_after_five_percent_giveback(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger"
    _write_open_position(ledger)
    rows = [
        _bar(10, 31, 120.0, 125.0, 120.0, 124.0),
        _bar(10, 32, 124.0, 124.0, 118.0, 119.0),
    ]
    state = {
        "last_processed_stop_raw_bar": _bar(10, 30).timestamp.isoformat(),
        "vehicle_high_water_mark": 120.0,
    }
    captured = []

    def fake_execute(event, **kwargs):
        captured.append(event)
        return {"side": event.side, "price": event.price, "reason": event.reason}

    monkeypatch.setattr(workflow, "execute_frozen_primary_event", fake_execute)
    result = workflow._process_catastrophic_stop_bucket(
        symbol="NFLU",
        strategy_id="TEST_PRIMARY",
        catastrophic_stop_percent=20.0,
        bucket_start=_bar(10, 30).timestamp,
        bucket_end=_bar(11, 30).timestamp,
        raw_rows=rows,
        ledger_dir=ledger,
        config_path=tmp_path / "config.json",
        symbol_state=state,
    )

    assert result["side"] == "SELL"
    assert result["price"] == 118.75
    assert result["reason"] == "FROZEN_DIRECT_PRIMARY_PROFIT_PROTECTION_STANDARD_GIVEBACK"
    assert state["vehicle_high_water_mark"] is None


def test_strong_profit_protection_uses_ten_percent_giveback(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger"
    _write_open_position(ledger)
    rows = [_bar(10, 31, 132.0, 133.0, 116.0, 118.0)]
    state = {
        "last_processed_stop_raw_bar": _bar(10, 30).timestamp.isoformat(),
        "vehicle_high_water_mark": 132.0,
    }

    monkeypatch.setattr(
        workflow,
        "execute_frozen_primary_event",
        lambda event, **kwargs: {"side": event.side, "price": event.price, "reason": event.reason},
    )
    result = workflow._process_catastrophic_stop_bucket(
        symbol="NFLU",
        strategy_id="TEST_PRIMARY",
        catastrophic_stop_percent=20.0,
        bucket_start=_bar(10, 30).timestamp,
        bucket_end=_bar(11, 30).timestamp,
        raw_rows=rows,
        ledger_dir=ledger,
        config_path=tmp_path / "config.json",
        symbol_state=state,
    )

    assert result["price"] == 118.8
    assert result["reason"] == "FROZEN_DIRECT_PRIMARY_PROFIT_PROTECTION_STRONG_GIVEBACK"


def test_catastrophic_minus_twenty_floor_remains_active(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger"
    _write_open_position(ledger)
    rows = [_bar(10, 31, 90.0, 91.0, 79.0, 80.0)]
    state = {
        "last_processed_stop_raw_bar": _bar(10, 30).timestamp.isoformat(),
        "vehicle_high_water_mark": None,
    }

    monkeypatch.setattr(
        workflow,
        "execute_frozen_primary_event",
        lambda event, **kwargs: {"side": event.side, "price": event.price, "reason": event.reason},
    )
    result = workflow._process_catastrophic_stop_bucket(
        symbol="NFLU",
        strategy_id="TEST_PRIMARY",
        catastrophic_stop_percent=20.0,
        bucket_start=_bar(10, 30).timestamp,
        bucket_end=_bar(11, 30).timestamp,
        raw_rows=rows,
        ledger_dir=ledger,
        config_path=tmp_path / "config.json",
        symbol_state=state,
    )

    assert result["price"] == 80.0
    assert result["reason"] == "FROZEN_DIRECT_PRIMARY_CATASTROPHIC_STOP_RAW_INTRADAY"
