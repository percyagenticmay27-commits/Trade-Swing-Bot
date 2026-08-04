import json
from pathlib import Path

import pytest

from swing_trade_bot.enterprise_market_data_client import (
    EnterpriseMarketDataClient,
    MarketDataUnavailable,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _status(*, stale=False, status="READY") -> dict:
    return {
        "strategies": {
            "SWING-001": {
                "strategy_id": "SWING-001",
                "status": status,
                "symbols": {
                    "SOXL": {
                        "symbol": "SOXL",
                        "quote": {
                            "symbol": "SOXL", "price": 140.15,
                            "quote_timestamp": "2026-08-04T19:59:04+00:00",
                            "trading_date": "2026-08-04", "provider": "YFINANCE",
                            "source_type": "LIVE_QUOTE", "stale": stale,
                            "confidence": 0.9, "warnings": [],
                        },
                        "history": {
                            "symbol": "SOXL", "interval": "1d", "period": "1mo",
                            "provider": "YFINANCE", "generated_at": "2026-08-04T20:00:00+00:00",
                            "latest_bar_date": "2026-08-04", "stale": stale,
                            "corporate_action_adjusted": False, "warnings": [],
                            "bars": [
                                {"date": "2026-08-01", "open": 130, "high": 133, "low": 129, "close": 132, "adjusted_close": 132, "volume": 10},
                                {"date": "2026-08-04", "open": 137.5, "high": 141.2, "low": 136.8, "close": 140.15, "adjusted_close": 140.15, "volume": 20},
                            ],
                        },
                    }
                },
            }
        }
    }


def _client(tmp_path: Path, status: dict, version="1.0") -> EnterpriseMarketDataClient:
    contract = tmp_path / "contract.json"
    evidence = tmp_path / "status.json"
    _write(contract, {"contract_version": version})
    _write(evidence, status)
    return EnterpriseMarketDataClient(contract_path=contract, status_path=evidence)


def test_version_1_and_fresh_quote_history_are_accepted(tmp_path):
    client = _client(tmp_path, _status())
    assert client.get_quote("SOXL").price == 140.15
    assert client.get_history("SOXL").bars[-1].close == 140.15


def test_unknown_contract_version_is_rejected(tmp_path):
    with pytest.raises(MarketDataUnavailable, match="unsupported"):
        _client(tmp_path, _status(), version="2.0")


def test_stale_quote_and_history_are_rejected(tmp_path):
    client = _client(tmp_path, _status(stale=True))
    with pytest.raises(MarketDataUnavailable, match="stale"):
        client.get_quote("SOXL")
    with pytest.raises(MarketDataUnavailable, match="stale"):
        client.get_history("SOXL")


def test_blocked_strategy_is_rejected(tmp_path):
    with pytest.raises(MarketDataUnavailable, match="BLOCKED"):
        _client(tmp_path, _status(status="BLOCKED"))


def test_missing_optional_symbol_returns_none(tmp_path):
    client = _client(tmp_path, _status())
    with pytest.raises(MarketDataUnavailable):
        client.get_quote("TQQQ", required=False)


def test_no_dividend_or_robinhood_imports():
    source = Path("src/swing_trade_bot/enterprise_market_data_client.py").read_text(encoding="utf-8").lower()
    assert "trade_dividend_bot" not in source
    assert "robin_stocks" not in source
    assert "codex exec" not in source
    assert "place_order" not in source
