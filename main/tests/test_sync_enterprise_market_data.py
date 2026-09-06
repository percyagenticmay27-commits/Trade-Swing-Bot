import csv
import json
from pathlib import Path

import pytest

from sync_enterprise_market_data import sync_exported_history
from swing_trade_bot.enterprise_market_data_client import MarketDataUnavailable


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, latest="2026-08-04") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])
        writer.writerow(["2026-08-01", 100, 105, 99, 104, 104, 1000])
        writer.writerow([latest, 105, 110, 104, 109, 109, 1200])


def _contract(directory="enterprise_market_data_history") -> dict:
    return {
        "contract_version": "1.0",
        "history_exports": {
            "enabled": True,
            "directory": directory,
            "csv_pattern": "{symbol}.csv",
        },
    }


def _status(*, stale=False, strategy_status="READY", latest="2026-08-04") -> dict:
    return {
        "strategy_id": "SWING-001",
        "status": strategy_status,
        "symbols": {
            symbol: {
                "symbol": symbol,
                "history": {
                    "provider": "YFINANCE",
                    "latest_bar_date": latest,
                    "stale": stale,
                },
            }
            for symbol in ("SOXL", "TQQQ")
        },
    }


def test_sync_reads_export_directory_from_contract(tmp_path):
    results = tmp_path / "dividend" / "results"
    contract = results / "enterprise_market_data_contract.json"
    status = results / "enterprise_market_data_status.json"
    _write_json(contract, _contract("enterprise_market_data_history"))
    _write_json(status, _status())
    _write_csv(results / "enterprise_market_data_history" / "SOXL.csv")
    _write_csv(results / "enterprise_market_data_history" / "TQQQ.csv")

    output = tmp_path / "swing" / "results" / "enterprise_market_data"
    result = sync_exported_history(
        contract_path=contract,
        status_path=status,
        output_dir=output,
        required_symbols=["SOXL", "TQQQ"],
        optional_symbols=[],
    )

    assert result["status"] == "READY"
    assert (output / "SOXL.csv").exists()
    assert (output / "TQQQ.csv").exists()
    assert (output / "sync_status.json").exists()


def test_sync_can_publish_canonical_ai_cio_market_data_status(tmp_path):
    results = tmp_path / "dividend" / "results"
    contract = results / "enterprise_market_data_contract.json"
    status = results / "enterprise_market_data_status.json"
    _write_json(contract, _contract("enterprise_market_data_history"))
    _write_json(status, _status())
    _write_csv(results / "enterprise_market_data_history" / "SOXL.csv")
    _write_csv(results / "enterprise_market_data_history" / "TQQQ.csv")

    swing_results = tmp_path / "swing" / "results"
    canonical = swing_results / "market_data_refresh_status.json"
    result = sync_exported_history(
        contract_path=contract,
        status_path=status,
        output_dir=swing_results / "enterprise_market_data",
        required_symbols=["SOXL", "TQQQ"],
        optional_symbols=[],
        canonical_status_path=canonical,
    )

    stored = json.loads(canonical.read_text(encoding="utf-8"))
    assert stored == result
    assert stored["strategy_id"] == "SWING-001"
    assert stored["status"] == "READY"
    assert stored["paper_trade_mode"] is True
    assert stored["advisory_only"] is True
    assert stored["live_trading_enabled"] is False
    assert stored["broker_execution_enabled"] is False
    assert stored["order_placement_enabled"] is False
    assert stored["capital_movement_enabled"] is False
    assert stored["market_data_dependent_publication_allowed"] is True
    assert stored["generated_at"]
    assert stored["contract_source_path"] == str(contract.resolve())
    assert stored["status_source_path"] == str(status.resolve())
    assert not list(canonical.parent.glob(".market_data_refresh_status.json.*.tmp"))


def test_stale_history_is_rejected_even_when_export_exists(tmp_path):
    results = tmp_path / "results"
    contract = results / "enterprise_market_data_contract.json"
    status = results / "enterprise_market_data_status.json"
    _write_json(contract, _contract())
    _write_json(status, _status(stale=True))
    _write_csv(results / "enterprise_market_data_history" / "SOXL.csv")
    _write_csv(results / "enterprise_market_data_history" / "TQQQ.csv")

    with pytest.raises(MarketDataUnavailable, match="fresh history unavailable"):
        sync_exported_history(
            contract_path=contract,
            status_path=status,
            output_dir=tmp_path / "output",
            required_symbols=["SOXL", "TQQQ"],
            optional_symbols=[],
        )


def test_latest_bar_must_match_status_evidence(tmp_path):
    results = tmp_path / "results"
    contract = results / "enterprise_market_data_contract.json"
    status = results / "enterprise_market_data_status.json"
    _write_json(contract, _contract())
    _write_json(status, _status(latest="2026-08-04"))
    _write_csv(results / "enterprise_market_data_history" / "SOXL.csv", latest="2026-08-02")
    _write_csv(results / "enterprise_market_data_history" / "TQQQ.csv")

    with pytest.raises(MarketDataUnavailable, match="latest bar does not match"):
        sync_exported_history(
            contract_path=contract,
            status_path=status,
            output_dir=tmp_path / "output",
            required_symbols=["SOXL", "TQQQ"],
            optional_symbols=[],
        )


def test_export_directory_cannot_escape_contract_root(tmp_path):
    results = tmp_path / "results"
    contract = results / "enterprise_market_data_contract.json"
    status = results / "enterprise_market_data_status.json"
    _write_json(contract, _contract("../outside"))
    _write_json(status, _status())

    with pytest.raises(MarketDataUnavailable, match="escapes the evidence root"):
        sync_exported_history(
            contract_path=contract,
            status_path=status,
            output_dir=tmp_path / "output",
            required_symbols=["SOXL"],
            optional_symbols=[],
        )


def test_optional_missing_export_becomes_warning(tmp_path):
    results = tmp_path / "results"
    contract = results / "enterprise_market_data_contract.json"
    status = results / "enterprise_market_data_status.json"
    payload = _status()
    payload["symbols"]["AMD"] = {
        "symbol": "AMD",
        "history": {"provider": "YFINANCE", "latest_bar_date": "2026-08-04", "stale": False},
    }
    _write_json(contract, _contract())
    _write_json(status, payload)
    _write_csv(results / "enterprise_market_data_history" / "SOXL.csv")

    result = sync_exported_history(
        contract_path=contract,
        status_path=status,
        output_dir=tmp_path / "output",
        required_symbols=["SOXL"],
        optional_symbols=["AMD"],
    )

    assert result["status"] == "WARNING"
    assert any("AMD" in warning for warning in result["warnings"])
