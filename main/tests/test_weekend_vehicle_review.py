from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from swing_trade_bot.weekend_vehicle_review import (
    build_weekend_vehicle_review,
    collect_vehicle_evidence,
    discover_unverified_vehicle_candidates,
    is_weekend,
    write_weekend_vehicle_review,
)


def _registry(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "strategy_id": "SWING-001",
                "paper_trade_mode": True,
                "mappings": [
                    {
                        "underlying_symbol": "NVDA",
                        "preferred_vehicle": "NVDX",
                        "vehicles": [
                            {"symbol": "NVDX", "enabled": True, "verified": True, "leverage_multiple": 2.0},
                            {"symbol": "NVDL", "enabled": True, "verified": True, "leverage_multiple": 2.0},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class FakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, *, period: str, auto_adjust: bool = False):
        if period == "3mo":
            if self.symbol == "NVDX":
                close = [50.0, 51.0, 52.0]
                volume = [1_000_000, 1_100_000, 1_200_000]
            else:
                close = [30.0, 31.0, 32.0]
                volume = [300_000, 320_000, 340_000]
            return pd.DataFrame({"Close": close, "Volume": volume})
        return pd.DataFrame({"Close": [1.0] * 250, "Volume": [1.0] * 250})

    def get_info(self):
        if self.symbol == "NVDX":
            return {
                "bid": 51.95,
                "ask": 52.05,
                "totalAssets": 800_000_000,
                "netExpenseRatio": 1.05,
                "quoteType": "ETF",
            }
        return {
            "bid": 31.80,
            "ask": 32.20,
            "totalAssets": 100_000_000,
            "netExpenseRatio": 1.15,
            "quoteType": "ETF",
        }


class FakeIncompleteTicker(FakeTicker):
    def get_info(self):
        return {"bid": 10.0, "ask": 10.1, "quoteType": "ETF"}


class FakeSearch:
    def __init__(self, query: str, max_results: int = 12) -> None:
        self.quotes = [
            {"symbol": "NVDX", "quoteType": "ETF", "shortname": "Known NVDA ETF", "exchange": "NGM"},
            {"symbol": "NEW2X", "quoteType": "ETF", "shortname": "Possible 2X NVDA ETF", "exchange": "NGM"},
            {"symbol": "NVDA", "quoteType": "EQUITY", "shortname": "NVIDIA", "exchange": "NGM"},
        ]


def test_weekend_detection() -> None:
    assert is_weekend(date(2026, 8, 22)) is True
    assert is_weekend(date(2026, 8, 23)) is True
    assert is_weekend(date(2026, 8, 24)) is False


def test_collect_verified_vehicle_evidence() -> None:
    evidence, warnings = collect_vehicle_evidence("NVDA", "NVDX", ticker_factory=FakeTicker)
    assert warnings == []
    assert evidence is not None
    assert evidence.underlying_symbol == "NVDA"
    assert evidence.vehicle_symbol == "NVDX"
    assert evidence.price == 52.0
    assert evidence.average_daily_volume > 1_000_000
    assert evidence.average_daily_dollar_volume > 50_000_000
    assert evidence.aum == 800_000_000
    assert evidence.expense_ratio_pct == 1.05
    assert evidence.product_active is True


def test_missing_product_facts_fail_closed_instead_of_scoring_fake_zeros() -> None:
    evidence, warnings = collect_vehicle_evidence("NVDA", "NVDX", ticker_factory=FakeIncompleteTicker)
    assert evidence is None
    assert any("INCOMPLETE_PRODUCT_EVIDENCE:NVDX" in warning for warning in warnings)


def test_search_candidates_are_explicitly_unverified() -> None:
    rows = discover_unverified_vehicle_candidates("NVDA", search_factory=FakeSearch)
    symbols = {row["candidate_vehicle_symbol"] for row in rows}
    assert symbols == {"NEW2X", "NVDX"}
    assert all(row["verification_status"] == "UNVERIFIED" for row in rows)


def test_nonweekend_review_is_rejected_without_force(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    with pytest.raises(ValueError, match="Saturday/Sunday"):
        build_weekend_vehicle_review(
            registry_path=registry,
            reviewed_on=date(2026, 8, 24),
            ticker_factory=FakeTicker,
            search_factory=FakeSearch,
        )


def test_weekend_review_scores_only_verified_registry_vehicles_and_queues_new_search_results(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_weekend_vehicle_review(
        registry_path=registry,
        reviewed_on=date(2026, 8, 22),
        ticker_factory=FakeTicker,
        search_factory=FakeSearch,
    )
    assert report["paper_trade_mode"] is True
    assert report["verified_vehicle_evidence_count"] == 2
    assert report["preferred_vehicle_mapping"]["NVDA"] == "NVDX"
    assert report["unverified_vehicle_candidate_count"] == 1
    assert report["unverified_vehicle_candidates"][0]["candidate_vehicle_symbol"] == "NEW2X"
    assert report["new_mapping_auto_registration_allowed"] is False
    assert report["mapping_verification_required"] is True
    assert report["existing_positions_unchanged"] is True


def test_force_allows_manual_validation_without_changing_weekend_policy(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_weekend_vehicle_review(
        registry_path=registry,
        reviewed_on=date(2026, 8, 24),
        ticker_factory=FakeTicker,
        search_factory=FakeSearch,
        force=True,
    )
    assert report["reviewed_on"] == "2026-08-24"
    assert report["selection_scope"] == "FUTURE_NEW_CANDIDATES_ONLY"


def test_review_write_is_atomic(tmp_path: Path) -> None:
    destination = tmp_path / "review.json"
    payload = {"strategy_id": "SWING-001", "paper_trade_mode": True}
    write_weekend_vehicle_review(payload, destination)
    assert json.loads(destination.read_text(encoding="utf-8")) == payload
    assert not (tmp_path / "review.json.tmp").exists()


def test_no_order_or_broker_execution_path_is_introduced() -> None:
    import swing_trade_bot.weekend_vehicle_review as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("place_order", "submit_order", "execute_trade", "broker_adapter", "robinhood")
    assert all(term not in source for term in forbidden)
