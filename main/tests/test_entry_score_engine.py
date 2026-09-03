from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from swing_trade_bot.entry_score_engine import (
    ENTRY_MINIMUM,
    EntryEvidenceSnapshot,
    build_entry_score_report,
    evaluate_symbol_entry_score,
    score_entry_evidence,
)
from swing_trade_bot.position_state import MarketBar


def _snapshot(**overrides: float | str) -> EntryEvidenceSnapshot:
    values: dict[str, float | str] = {
        "symbol": "NVDA",
        "completed_bar_date": "2026-09-01",
        "close": 105.0,
        "previous_close": 103.0,
        "rsi": 55.0,
        "previous_rsi": 52.0,
        "stochastic_rsi_k": 70.0,
        "stochastic_rsi_d": 60.0,
        "previous_stochastic_rsi_k": 55.0,
        "previous_stochastic_rsi_d": 58.0,
        "macd": 2.0,
        "macd_signal": 1.5,
        "macd_histogram": 0.5,
        "previous_macd": 1.4,
        "previous_macd_signal": 1.5,
        "previous_macd_histogram": -0.1,
        "volume": 1_500_000.0,
        "prior_20_day_average_volume": 1_000_000.0,
        "volume_ratio": 1.5,
        "ema20": 102.0,
        "ema50": 95.0,
        "ema20_extension_percent": ((105.0 - 102.0) / 102.0) * 100.0,
    }
    values.update(overrides)
    return EntryEvidenceSnapshot(**values)  # type: ignore[arg-type]


def test_full_bullish_snapshot_scores_100() -> None:
    row = score_entry_evidence(_snapshot())
    assert row.entry_score == 100.0
    assert row.entry_score_gate_passed is True
    assert row.entry_status == "PASS"
    assert sum(component.maximum_points for component in row.components) == 100.0


def test_negative_high_volume_bar_is_capped_at_five_points() -> None:
    row = score_entry_evidence(_snapshot(close=101.0, previous_close=103.0, volume_ratio=1.8))
    volume = next(component for component in row.components if component.component_id == "volume_confirmation")
    assert volume.points == 5.0
    assert "NEGATIVE_BAR_CAPPED_AT_5" in volume.status


def test_extended_setup_receives_zero_extension_points() -> None:
    row = score_entry_evidence(_snapshot(ema20_extension_percent=12.0))
    extension = next(component for component in row.components if component.component_id == "extension_and_pullback_risk")
    assert extension.points == 0.0
    assert extension.status == "MORE_THAN_10_PERCENT_ABOVE_EMA20"


def test_insufficient_daily_history_is_evidence_pending() -> None:
    bars = [
        MarketBar(date=date(2026, 1, 1) + timedelta(days=i), close=100.0 + i, volume=1_000_000.0)
        for i in range(30)
    ]
    row = evaluate_symbol_entry_score("NVDA", bars)
    assert row.entry_score is None
    assert row.entry_score_gate_passed is False
    assert row.entry_status == "EVIDENCE_PENDING"
    assert row.evidence_status == "PENDING"


def test_calculates_score_from_completed_daily_bars() -> None:
    bars = []
    start = date(2026, 1, 1)
    for i in range(90):
        close = 100.0 + (i * 0.5) + ((i % 7) * 0.1)
        bars.append(MarketBar(date=start + timedelta(days=i), close=close, volume=1_000_000.0 + i * 10_000.0))
    row = evaluate_symbol_entry_score("NVDA", bars)
    assert row.entry_score is not None
    assert 0.0 <= row.entry_score <= 100.0
    assert row.completed_bar_date == bars[-1].date.isoformat()
    assert row.bar_status == "COMPLETED_DAILY_BAR"
    assert row.evidence_status == "AVAILABLE"
    assert len(row.components) == 6


def test_report_uses_underlying_symbol_and_missing_data_fails_closed(tmp_path: Path) -> None:
    results = tmp_path / "results"
    data = tmp_path / "data"
    results.mkdir()
    data.mkdir()
    (results / "watchlist_report.json").write_text(
        json.dumps({
            "rows": [
                {
                    "underlying_symbol": "NVDA",
                    "leveraged_symbol": "NVDX",
                    "capacity_status": "ACTIVE",
                    "watchlist_status": "WATCHLIST",
                }
            ]
        }),
        encoding="utf-8",
    )
    payload = build_entry_score_report(results_dir=results, data_dir=data)
    row = payload["rows"][0]
    assert row["symbol"] == "NVDA"
    assert row["entry_score"] is None
    assert row["entry_status"] == "EVIDENCE_PENDING"
    assert payload["entry_minimum"] == ENTRY_MINIMUM == 70.0
    assert payload["price_evidence_authority"] == "UNLEVERAGED_SIGNAL_OR_UNDERLYING_SYMBOL_COMPLETED_DAILY_BARS"
    assert payload["frozen_strategy_signal_not_part_of_entry_score"] is True
