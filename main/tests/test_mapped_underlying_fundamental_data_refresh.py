from __future__ import annotations

import json
from pathlib import Path

import pytest

import swing_trade_bot.mapped_underlying_fundamental_data_refresh as module
from swing_trade_bot.mapped_underlying_fundamental_data_refresh import (
    COMPANYFACTS_URL,
    KNOWN_CIKS,
    TICKER_MAP_URL,
    derive_fundamental_metrics,
    refresh_mapped_underlying_fundamental_data,
)


def _registry(path: Path, symbols: tuple[str, ...] = ("NVDA", "SNDK")) -> Path:
    vehicles = {"NVDA": "NVDX", "SNDK": "SNXX", "ZZZZ": "ZZZL"}
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [
            {
                "underlying_symbol": symbol,
                "preferred_vehicle": vehicles[symbol],
                "vehicles": [{"symbol": vehicles[symbol], "verified": True, "enabled": True}],
            }
            for symbol in symbols
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fact(values):
    return {"units": {"USD": values}}


def _companyfacts():
    def annual(v2024, v2025):
        return [
            {"form": "10-K", "fp": "FY", "end": "2024-01-28", "filed": "2024-03-01", "val": v2024},
            {"form": "10-K", "fp": "FY", "end": "2025-01-26", "filed": "2025-03-01", "val": v2025},
        ]

    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _fact(annual(100.0, 120.0)),
                "NetIncomeLoss": _fact(annual(10.0, 15.0)),
                "OperatingIncomeLoss": _fact(annual(18.0, 24.0)),
                "NetCashProvidedByUsedInOperatingActivities": _fact(annual(20.0, 30.0)),
                "PaymentsToAcquirePropertyPlantAndEquipment": _fact(annual(5.0, 6.0)),
                "AssetsCurrent": _fact(annual(50.0, 60.0)),
                "LiabilitiesCurrent": _fact(annual(25.0, 30.0)),
                "StockholdersEquity": _fact(annual(80.0, 100.0)),
                "LongTermDebt": _fact(annual(30.0, 25.0)),
            }
        }
    }


def test_companyfacts_derives_transparent_raw_metrics() -> None:
    metrics = derive_fundamental_metrics(_companyfacts())
    assert metrics["fiscal_end"] == "2025-01-26"
    assert metrics["revenue_growth_pct"] == 20.0
    assert metrics["earnings_growth_pct"] == 50.0
    assert metrics["operating_margin_pct"] == 20.0
    assert metrics["free_cash_flow_margin_pct"] == 20.0
    assert metrics["return_on_equity_pct"] == 15.0
    assert metrics["current_ratio"] == 2.0
    assert metrics["debt_to_equity"] == 0.25


def test_alternative_revenue_tag_uses_freshest_annual_series() -> None:
    facts = _companyfacts()
    facts["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"] = _fact([
        {"form": "10-K", "fp": "FY", "end": "2023-01-29", "filed": "2023-03-01", "val": 25.0},
        {"form": "10-K", "fp": "FY", "end": "2024-01-28", "filed": "2024-03-01", "val": 30.0},
    ])
    facts["facts"]["us-gaap"]["Revenues"] = _fact([
        {"form": "10-K", "fp": "FY", "end": "2024-01-28", "filed": "2024-03-01", "val": 100.0},
        {"form": "10-K", "fp": "FY", "end": "2025-01-26", "filed": "2025-03-01", "val": 120.0},
    ])
    metrics = derive_fundamental_metrics(facts)
    assert metrics["fiscal_end"] == "2025-01-26"
    assert metrics["revenue_growth_pct"] == 20.0
    assert metrics["operating_margin_pct"] == 20.0


def test_ratios_use_same_fiscal_end_as_revenue() -> None:
    facts = _companyfacts()
    facts["facts"]["us-gaap"]["OperatingIncomeLoss"] = _fact([
        {"form": "10-K", "fp": "FY", "end": "2025-01-26", "filed": "2025-03-01", "val": 24.0},
        {"form": "10-K", "fp": "FY", "end": "2026-01-25", "filed": "2026-03-01", "val": 500.0},
    ])
    metrics = derive_fundamental_metrics(facts)
    assert metrics["fiscal_end"] == "2025-01-26"
    assert metrics["operating_margin_pct"] == 20.0


def test_known_mapped_symbols_skip_ticker_map_and_fetch_only_underlying_companyfacts(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    assert report["underlyings_with_fundamental_metrics"] == 2
    assert TICKER_MAP_URL not in calls
    assert COMPANYFACTS_URL.format(cik=KNOWN_CIKS["NVDA"]) in calls
    assert COMPANYFACTS_URL.format(cik=KNOWN_CIKS["SNDK"]) in calls
    assert all("NVDX" not in call and "SNXX" not in call for call in calls)


def test_unknown_symbol_uses_sec_ticker_map_then_companyfacts(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json", symbols=("ZZZZ",))
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        if url == TICKER_MAP_URL:
            return {"0": {"ticker": "ZZZZ", "cik_str": 9999999}}
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    assert report["underlyings_with_fundamental_metrics"] == 1
    assert calls[0] == TICKER_MAP_URL
    assert COMPANYFACTS_URL.format(cik=9999999) in calls


def test_unknown_symbol_missing_cik_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json", symbols=("ZZZZ",))

    def fetch(url: str):
        if url == TICKER_MAP_URL:
            return {}
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    row = report["rows"][0]
    assert row["status"] == "CIK_NOT_FOUND"
    assert row["metrics"] == {}


def test_fetch_error_is_visible_and_does_not_create_metrics(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fetch(url: str):
        if f"{KNOWN_CIKS['NVDA']:010d}" in url:
            raise OSError("network unavailable")
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    nvda = next(row for row in report["rows"] if row["underlying_symbol"] == "NVDA")
    assert nvda["status"] == "FETCH_OR_PARSE_ERROR"
    assert nvda["metrics"] == {}
    assert report["underlyings_with_fundamental_metrics"] == 1


def test_live_sec_fetch_requires_declared_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        module._declared_user_agent()
    monkeypatch.setenv("SEC_USER_AGENT", "Trade-Swing-Bot operations@example.com")
    assert module._declared_user_agent() == "Trade-Swing-Bot operations@example.com"


def test_fundamental_data_refresh_is_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = refresh_mapped_underlying_fundamental_data(
        registry_path=registry,
        fetch_json=lambda url: _companyfacts(),
    )
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False
    assert report["ai_cio_discovery_status_used_as_fundamental_data"] is False
