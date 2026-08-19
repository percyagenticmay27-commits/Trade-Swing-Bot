from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.mapped_underlying_fundamental_data_refresh import (
    COMPANYFACTS_URL,
    TICKER_MAP_URL,
    derive_fundamental_metrics,
    refresh_mapped_underlying_fundamental_data,
)


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [
            {"underlying_symbol": "NVDA", "preferred_vehicle": "NVDX", "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}]},
            {"underlying_symbol": "SNDK", "preferred_vehicle": "SNXX", "vehicles": [{"symbol": "SNXX", "verified": True, "enabled": True}]},
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
    assert metrics["revenue_growth_pct"] == 20.0
    assert metrics["earnings_growth_pct"] == 50.0
    assert metrics["operating_margin_pct"] == 20.0
    assert metrics["free_cash_flow_margin_pct"] == 20.0
    assert metrics["return_on_equity_pct"] == 15.0
    assert metrics["current_ratio"] == 2.0
    assert metrics["debt_to_equity"] == 0.25


def test_refresh_fetches_only_underlying_company_facts(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        if url == TICKER_MAP_URL:
            return {
                "0": {"ticker": "NVDA", "cik_str": 1045810},
                "1": {"ticker": "SNDK", "cik_str": 2008287},
            }
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(
        registry_path=registry,
        fetch_json=fetch,
    )
    assert report["underlyings_with_fundamental_metrics"] == 2
    assert any(COMPANYFACTS_URL.format(cik=1045810) == call for call in calls)
    assert all("NVDX" not in call and "SNXX" not in call for call in calls)


def test_missing_cik_fails_closed_for_that_underlying(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fetch(url: str):
        if url == TICKER_MAP_URL:
            return {"0": {"ticker": "NVDA", "cik_str": 1045810}}
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    sndk = next(row for row in report["rows"] if row["underlying_symbol"] == "SNDK")
    assert sndk["status"] == "CIK_NOT_FOUND"
    assert sndk["metrics"] == {}


def test_fetch_error_is_visible_and_does_not_create_metrics(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fetch(url: str):
        if url == TICKER_MAP_URL:
            return {
                "0": {"ticker": "NVDA", "cik_str": 1045810},
                "1": {"ticker": "SNDK", "cik_str": 2008287},
            }
        if "0001045810" in url:
            raise OSError("network unavailable")
        return _companyfacts()

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    nvda = next(row for row in report["rows"] if row["underlying_symbol"] == "NVDA")
    assert nvda["status"] == "FETCH_OR_PARSE_ERROR"
    assert nvda["metrics"] == {}
    assert report["underlyings_with_fundamental_metrics"] == 1


def test_fundamental_data_refresh_is_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fetch(url: str):
        if url == TICKER_MAP_URL:
            return {}
        return {}

    report = refresh_mapped_underlying_fundamental_data(registry_path=registry, fetch_json=fetch)
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False
    assert report["ai_cio_discovery_status_used_as_fundamental_data"] is False
