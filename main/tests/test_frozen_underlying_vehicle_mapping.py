import json
from pathlib import Path

import swing_trade_bot.frozen_primary_signal_execution_workflow as execution_workflow
from swing_trade_bot.intraday_market_data_refresh import refresh_intraday_market_data
from swing_trade_bot.intraday_chart_bars import IntradayBar
from datetime import datetime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
PRIMARY = "TQQQ_QQQ_TEST_PRIMARY"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(path: Path) -> None:
    _write_json(path, {
        "schema_version": "1.1",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "strategies": [{
            "strategy_id": PRIMARY,
            "name": "QQQ signal / TQQQ vehicle",
            "signal_symbol": "QQQ",
            "vehicle_symbol": "TQQQ",
            "timeframe": "1H",
            "engine_id": "ZERO_LAG",
            "parameters": {"length": 10, "multiplier": 1.0},
            "catastrophic_stop_percent": 20.0,
            "assignment_mode": "DIRECT",
            "enabled": True,
            "paper_trade_mode": True,
        }],
        "symbols": [{
            "symbol": "TQQQ",
            "primary_strategy_id": PRIMARY,
            "shadow_strategy_ids": [],
            "shadow_slot_3": None,
            "research_status": "TEST",
        }],
    })


def _intraday(path: Path, opens: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["Timestamp,Open,High,Low,Close,Volume"]
    for index, price in enumerate(opens):
        minutes = 30 + index * 60
        hour = 9 + minutes // 60
        minute = minutes % 60
        rows.append(
            f"2026-09-01T{hour:02d}:{minute:02d}:00-04:00,{price},{price+1},{price-1},{price+0.5},1000"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _ledger(path: Path) -> None:
    _write_json(path / "open_positions.json", {"paper_trade_mode": True, "positions": []})
    _write_json(path / "trade_history.json", {"paper_trade_mode": True, "trades": []})


def test_confirmed_qqq_signal_fills_at_matching_tqqq_next_bar_open(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    intraday = tmp_path / "intraday"
    ledger = tmp_path / "ledger"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    _config(config)
    _ledger(ledger)
    _intraday(intraday / "QQQ.csv", [100.0, 101.0, 102.0])
    _intraday(intraday / "TQQQ.csv", [200.0, 210.0, 220.0])
    _write_json(state, {
        "paper_trade_mode": True,
        "symbols": {"TQQQ": {
            "strategy_id": PRIMARY,
            "signal_symbol": "QQQ",
            "vehicle_symbol": "TQQQ",
            "last_processed_chart_bar": "2026-09-01T09:30:00-04:00",
            "last_processed_stop_raw_bar": "2026-09-01T09:30:00-04:00",
            "pending_signal": None,
            "allocation_notional": 1000.0,
        }},
    })

    class Decision:
        entry_signal = True
        exit_signal = False

    original = execution_workflow.evaluate_frozen_signal
    execution_workflow.evaluate_frozen_signal = lambda *args, **kwargs: Decision()
    try:
        result = execution_workflow.run_frozen_primary_signal_execution(
            config_path=config,
            intraday_dir=intraday,
            ledger_dir=ledger,
            state_path=state,
            report_path=report,
        )
    finally:
        execution_workflow.evaluate_frozen_signal = original

    row = result["rows"][0]
    event = row["executed_events"][0]
    assert row["signal_symbol"] == "QQQ"
    assert row["vehicle_symbol"] == "TQQQ"
    assert event["symbol"] == "TQQQ"
    assert event["side"] == "BUY"
    assert event["price"] == 220.0
    assert event["notional"] == 1000.0
    position = json.loads((ledger / "open_positions.json").read_text(encoding="utf-8"))["positions"][0]
    assert position["symbol"] == "TQQQ"
    assert position["entry_price"] == 220.0
    assert position["active_strategy"] == PRIMARY


def test_intraday_refresh_fetches_both_qqq_signal_and_tqqq_vehicle(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    _config(config)
    calls: list[str] = []

    def fetch(symbol: str):
        calls.append(symbol)
        base = 100.0 if symbol == "QQQ" else 200.0
        return tuple(
            IntradayBar(
                datetime(2026, 9, 1, 9, 30, tzinfo=NY),
                base,
                base + 1,
                base - 1,
                base + 0.5,
                1000,
            )
            for _ in range(1)
        )

    payload = refresh_intraday_market_data(
        config_path=config,
        data_dir=tmp_path / "intraday",
        status_path=tmp_path / "status.json",
        fetch_recent=fetch,
    )

    assert calls == ["QQQ", "TQQQ"]
    assert {row["symbol"] for row in payload["symbols"]} == {"QQQ", "TQQQ"}
    assert (tmp_path / "intraday" / "QQQ.csv").is_file()
    assert (tmp_path / "intraday" / "TQQQ.csv").is_file()
