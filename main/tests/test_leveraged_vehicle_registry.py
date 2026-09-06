from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.leveraged_vehicle_registry import (
    UnderlyingVehicleRegistry,
    VehicleDefinition,
    VehicleEvidence,
    build_weekly_review,
    choose_preferred_vehicle,
    load_vehicle_registry,
    preferred_vehicle_mapping,
    score_vehicle_group,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _registry_payload() -> dict:
    return {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mappings": [
            {
                "underlying_symbol": "NVDA",
                "preferred_vehicle": "NVDX",
                "vehicles": [
                    {"symbol": "NVDX", "verified": True, "enabled": True, "leverage_multiple": 2.0},
                    {"symbol": "NVDL", "verified": True, "enabled": True, "leverage_multiple": 2.0},
                    {"symbol": "NVDU", "verified": True, "enabled": True, "leverage_multiple": 2.0},
                ],
            },
            {
                "underlying_symbol": "SNDK",
                "preferred_vehicle": "SNXX",
                "vehicles": [
                    {"symbol": "SNXX", "verified": True, "enabled": True, "leverage_multiple": 2.0}
                ],
            },
        ],
    }


def _evidence(
    symbol: str,
    *,
    volume: float,
    dollar: float,
    spread: float,
    aum: float,
    expense: float,
    price: float,
    history: int,
    active: bool = True,
) -> VehicleEvidence:
    return VehicleEvidence(
        underlying_symbol="NVDA",
        vehicle_symbol=symbol,
        price=price,
        average_daily_volume=volume,
        average_daily_dollar_volume=dollar,
        bid_ask_spread_pct=spread,
        aum=aum,
        expense_ratio_pct=expense,
        history_days=history,
        product_active=active,
    )


def test_registry_supports_one_underlying_to_many_verified_vehicles(tmp_path: Path) -> None:
    registry = load_vehicle_registry(_write(tmp_path / "registry.json", _registry_payload()))
    nvda = registry["NVDA"]
    assert nvda.preferred_vehicle == "NVDX"
    assert [vehicle.symbol for vehicle in nvda.vehicles] == ["NVDX", "NVDL", "NVDU"]
    assert registry["SNDK"].preferred_vehicle == "SNXX"


def test_preferred_vehicle_mapping_exposes_only_enabled_verified_preferences(tmp_path: Path) -> None:
    payload = _registry_payload()
    payload["mappings"][1]["vehicles"][0]["verified"] = False
    mapping = preferred_vehicle_mapping(_write(tmp_path / "registry.json", payload))
    assert mapping == {"NVDA": "NVDX"}


def test_registry_rejects_guessed_or_ambiguous_relationships(tmp_path: Path) -> None:
    payload = _registry_payload()
    payload["mappings"].append(
        {
            "underlying_symbol": "OTHER",
            "preferred_vehicle": "NVDX",
            "vehicles": [{"symbol": "NVDX", "verified": True}],
        }
    )
    with pytest.raises(ValueError, match="mapped to multiple underlyings"):
        load_vehicle_registry(_write(tmp_path / "registry.json", payload))


def test_preferred_must_be_one_of_registered_vehicles(tmp_path: Path) -> None:
    payload = _registry_payload()
    payload["mappings"][0]["preferred_vehicle"] = "MADEUP"
    with pytest.raises(ValueError, match="preferred_vehicle MADEUP"):
        load_vehicle_registry(_write(tmp_path / "registry.json", payload))


def test_vehicle_scoring_rewards_liquidity_spread_cost_and_stability() -> None:
    entry = UnderlyingVehicleRegistry(
        underlying_symbol="NVDA",
        preferred_vehicle="NVDX",
        vehicles=(
            VehicleDefinition("NVDX"),
            VehicleDefinition("NVDL"),
            VehicleDefinition("NVDU"),
        ),
    )
    rows = [
        _evidence("NVDX", volume=10_000_000, dollar=180_000_000, spread=0.03, aum=400_000_000, expense=1.05, price=18, history=1000),
        _evidence("NVDL", volume=15_000_000, dollar=900_000_000, spread=0.02, aum=6_000_000_000, expense=1.15, price=60, history=1300),
        _evidence("NVDU", volume=2_000_000, dollar=220_000_000, spread=0.08, aum=500_000_000, expense=1.04, price=110, history=1000),
    ]
    scores = score_vehicle_group(entry, rows)
    assert scores[0].vehicle_symbol == "NVDL"
    assert scores[0].score > scores[-1].score


def test_weekly_review_can_change_future_preference_when_challenger_clearly_wins() -> None:
    entry = UnderlyingVehicleRegistry(
        underlying_symbol="NVDA",
        preferred_vehicle="NVDX",
        vehicles=(VehicleDefinition("NVDX"), VehicleDefinition("NVDL")),
    )
    rows = [
        _evidence("NVDX", volume=1_000_000, dollar=20_000_000, spread=0.20, aum=100_000_000, expense=1.50, price=100, history=500),
        _evidence("NVDL", volume=10_000_000, dollar=500_000_000, spread=0.02, aum=5_000_000_000, expense=1.00, price=50, history=1200),
    ]
    selected, scores = choose_preferred_vehicle(entry, rows, switch_threshold_points=5.0)
    assert selected == "NVDL"
    assert scores[0].vehicle_symbol == "NVDL"


def test_switch_threshold_prevents_weekly_preference_churn() -> None:
    entry = UnderlyingVehicleRegistry(
        underlying_symbol="NVDA",
        preferred_vehicle="NVDX",
        vehicles=(VehicleDefinition("NVDX"), VehicleDefinition("NVDL")),
    )
    rows = [
        _evidence("NVDX", volume=1_000_000, dollar=20_000_000, spread=0.20, aum=100_000_000, expense=1.50, price=100, history=500),
        _evidence("NVDL", volume=10_000_000, dollar=500_000_000, spread=0.02, aum=5_000_000_000, expense=1.00, price=50, history=1200),
    ]
    selected, _ = choose_preferred_vehicle(entry, rows, switch_threshold_points=101.0)
    assert selected == "NVDX"


def test_inactive_incumbent_can_be_replaced_without_switch_margin() -> None:
    entry = UnderlyingVehicleRegistry(
        underlying_symbol="NVDA",
        preferred_vehicle="NVDX",
        vehicles=(VehicleDefinition("NVDX"), VehicleDefinition("NVDL")),
    )
    rows = [
        _evidence("NVDX", volume=10_000_000, dollar=400_000_000, spread=0.01, aum=5_000_000_000, expense=1.0, price=20, history=1000, active=False),
        _evidence("NVDL", volume=1_000_000, dollar=50_000_000, spread=0.10, aum=100_000_000, expense=1.5, price=50, history=500),
    ]
    selected, _ = choose_preferred_vehicle(entry, rows, switch_threshold_points=100.0)
    assert selected == "NVDL"


def test_weekly_review_is_future_candidate_only_and_does_not_change_positions() -> None:
    registry = {
        "NVDA": UnderlyingVehicleRegistry(
            underlying_symbol="NVDA",
            preferred_vehicle="NVDX",
            vehicles=(VehicleDefinition("NVDX"), VehicleDefinition("NVDL")),
        )
    }
    rows = [
        _evidence("NVDX", volume=1_000_000, dollar=20_000_000, spread=0.20, aum=100_000_000, expense=1.50, price=100, history=500),
        _evidence("NVDL", volume=10_000_000, dollar=500_000_000, spread=0.02, aum=5_000_000_000, expense=1.00, price=50, history=1200),
    ]
    report = build_weekly_review(registry, rows, reviewed_at="2026-08-22T12:00:00Z")
    assert report["selection_scope"] == "FUTURE_NEW_CANDIDATES_ONLY"
    assert report["existing_positions_unchanged"] is True
    assert report["preferred_vehicle_mapping"]["NVDA"] == "NVDL"


def test_no_broker_or_order_execution_is_introduced() -> None:
    import swing_trade_bot.leveraged_vehicle_registry as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("robinhood", "place_order", "submit_order", "execute_trade", "broker_adapter")
    assert all(term not in source for term in forbidden)
