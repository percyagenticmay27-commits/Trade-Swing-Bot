from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.entry_score_evidence_refresh import (
    active_entry_underlyings,
    build_entry_market_data_config,
    enforce_fresh_entry_evidence,
    _provider_factory_config,
)
from swing_trade_bot.entry_score_engine import ENTRY_MINIMUM


def _score_row(symbol: str, score: float = 82.0) -> dict:
    return {
        "symbol": symbol,
        "entry_score": score,
        "entry_minimum": ENTRY_MINIMUM,
        "entry_score_gate_passed": score >= ENTRY_MINIMUM,
        "entry_status": "PASS" if score >= ENTRY_MINIMUM else "FAIL",
        "completed_bar_date": "2026-09-02",
        "bar_status": "COMPLETED_DAILY_BAR",
        "evidence_status": "AVAILABLE",
        "components": {
            "daily_rsi_direction": {"points": 20.0},
            "daily_stochastic_rsi_k_d_relationship": {"points": 20.0},
            "momentum_direction": {"points": 20.0},
            "volume_confirmation": {"points": 12.0},
            "price_trend_confirmation": {"points": 10.0},
            "extension_and_pullback_risk": {"points": 0.0},
        },
        "error": None,
    }


def _score_payload(*rows: dict) -> dict:
    return {
        "paper_trade_mode": True,
        "entry_minimum": ENTRY_MINIMUM,
        "frozen_strategy_signal_not_part_of_entry_score": True,
        "rows": list(rows),
    }


def _refresh_row(symbol: str, freshness: str, *, errors: list[str] | None = None) -> dict:
    return {
        "symbol": symbol,
        "freshness_status": freshness,
        "latest_completed_date": "2026-09-02",
        "errors": errors or [],
    }


def test_active_underlyings_selects_only_active_underlying_symbols(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_report.json"
    path.write_text(
        json.dumps({
            "rows": [
                {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "capacity_status": "ACTIVE"},
                {"underlying_symbol": "NBIS", "leveraged_symbol": "NEBX", "capacity_status": "ACTIVE"},
                {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "capacity_status": "ACTIVE"},
                {"underlying_symbol": "PLTR", "leveraged_symbol": "PLTU", "capacity_status": "REMOVED"},
            ]
        }),
        encoding="utf-8",
    )
    assert active_entry_underlyings(path) == ("NBIS", "NVDA")


def test_leveraged_vehicle_is_not_selected_as_entry_evidence(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_report.json"
    path.write_text(
        json.dumps({"rows": [
            {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "capacity_status": "ACTIVE"}
        ]}),
        encoding="utf-8",
    )
    symbols = active_entry_underlyings(path)
    assert symbols == ("NVDA",)
    assert "NVDX" not in symbols


def test_dynamic_market_data_config_uses_current_entry_underlyings() -> None:
    base = {
        "configured_strategy_symbols": ["SOXL", "TQQQ"],
        "portfolio_symbols": ["SOXL"],
        "watchlist_symbols": [],
        "candidate_symbols": ["ABC"],
        "paper_trade_mode": True,
    }
    configured = build_entry_market_data_config(base, symbols=("NVDA", "NBIS"))
    assert configured["configured_strategy_symbols"] == ["NBIS", "NVDA"]
    assert configured["portfolio_symbols"] == []
    assert configured["watchlist_symbols"] == []
    assert configured["candidate_symbols"] == []
    assert base["configured_strategy_symbols"] == ["SOXL", "TQQQ"]


def test_prior_local_csv_is_not_passed_as_network_provider() -> None:
    configured = _provider_factory_config({
        "provider_order": ["YFINANCE", "ROBINHOOD_AGENT_READ_ONLY", "PRIOR_LOCAL_CSV"]
    })
    assert configured["provider_order"] == ["YFINANCE", "ROBINHOOD_AGENT_READ_ONLY"]


def test_fresh_daily_evidence_preserves_numeric_entry_score() -> None:
    payload = enforce_fresh_entry_evidence(
        _score_payload(_score_row("NVDA", 82.0)),
        {"symbol_results": [_refresh_row("NVDA", "FRESH")]},
    )
    row = payload["rows"][0]
    assert row["entry_score"] == 82.0
    assert row["entry_score_gate_passed"] is True
    assert row["entry_status"] == "PASS"
    assert row["components"]


def test_warning_daily_evidence_cannot_authorize_entry() -> None:
    payload = enforce_fresh_entry_evidence(
        _score_payload(_score_row("NVDA", 82.0)),
        {"symbol_results": [_refresh_row("NVDA", "WARNING")]},
    )
    row = payload["rows"][0]
    assert row["entry_score"] is None
    assert row["entry_score_gate_passed"] is False
    assert row["entry_status"] == "EVIDENCE_PENDING"
    assert row["components"] == {}
    assert "WARNING" in row["error"]


def test_stale_daily_evidence_cannot_authorize_entry() -> None:
    payload = enforce_fresh_entry_evidence(
        _score_payload(_score_row("NVDA", 82.0)),
        {"symbol_results": [_refresh_row("NVDA", "STALE")]},
    )
    row = payload["rows"][0]
    assert row["entry_score"] is None
    assert row["entry_status"] == "EVIDENCE_PENDING"
    assert "STALE" in row["error"]


def test_missing_nbis_style_refresh_row_is_evidence_pending() -> None:
    payload = enforce_fresh_entry_evidence(
        _score_payload(_score_row("NBIS", 90.0)),
        {"symbol_results": []},
    )
    row = payload["rows"][0]
    assert row["entry_score"] is None
    assert row["entry_score_gate_passed"] is False
    assert row["entry_status"] == "EVIDENCE_PENDING"
    assert row["completed_bar_date"] is None
    assert "MISSING" in row["error"]


def test_provider_failure_cannot_fall_through_to_old_numeric_score() -> None:
    payload = enforce_fresh_entry_evidence(
        _score_payload(_score_row("BE", 75.0)),
        {"symbol_results": [
            _refresh_row("BE", "WARNING", errors=["provider chain failed; preserved prior valid file"])
        ]},
    )
    row = payload["rows"][0]
    assert row["entry_score"] is None
    assert row["entry_status"] == "EVIDENCE_PENDING"
    assert "provider chain failed" in row["error"]


def test_failed_symbol_does_not_suppress_fresh_symbol() -> None:
    payload = enforce_fresh_entry_evidence(
        _score_payload(_score_row("NVDA", 82.0), _score_row("NBIS", 78.0)),
        {"symbol_results": [
            _refresh_row("NVDA", "FRESH"),
            _refresh_row("NBIS", "MISSING", errors=["no provider bars"]),
        ]},
    )
    by_symbol = {row["symbol"]: row for row in payload["rows"]}
    assert by_symbol["NVDA"]["entry_score"] == 82.0
    assert by_symbol["NVDA"]["entry_score_gate_passed"] is True
    assert by_symbol["NBIS"]["entry_score"] is None
    assert by_symbol["NBIS"]["entry_status"] == "EVIDENCE_PENDING"


def test_entry_governance_metadata_remains_frozen_and_paper_only() -> None:
    payload = enforce_fresh_entry_evidence(
        {
            "paper_trade_mode": True,
            "advisory_only": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "order_placement_enabled": False,
            "capital_movement_enabled": False,
            "entry_minimum": ENTRY_MINIMUM,
            "frozen_strategy_signal_not_part_of_entry_score": True,
            "rows": [_score_row("NVDA", 82.0)],
        },
        {"symbol_results": [_refresh_row("NVDA", "FRESH")]},
    )
    assert payload["entry_minimum"] == 70.0
    assert payload["paper_trade_mode"] is True
    assert payload["advisory_only"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["frozen_strategy_signal_not_part_of_entry_score"] is True
    assert payload["accepted_market_data_freshness"] == ["FRESH"]
    assert payload["warning_market_data_authorizes_entry_score"] is False
    assert payload["stale_market_data_authorizes_entry_score"] is False
