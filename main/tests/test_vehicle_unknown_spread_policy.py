from __future__ import annotations

from swing_trade_bot.leveraged_vehicle_registry import (
    UnderlyingVehicleRegistry,
    VehicleDefinition,
    VehicleEvidence,
    choose_preferred_vehicle,
    score_vehicle_group,
)


def _evidence(
    symbol: str,
    *,
    spread: float | None,
    volume: float,
    dollar: float,
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


def _entry() -> UnderlyingVehicleRegistry:
    return UnderlyingVehicleRegistry(
        underlying_symbol="NVDA",
        preferred_vehicle="NVDX",
        vehicles=(VehicleDefinition("NVDX"), VehicleDefinition("NVDL")),
    )


def test_unknown_spread_remains_eligible_with_reduced_confidence() -> None:
    rows = [
        _evidence(
            "NVDX",
            spread=0.15,
            volume=5_000_000,
            dollar=120_000_000,
            aum=400_000_000,
            expense=1.05,
            price=20.0,
            history=700,
        ),
        _evidence(
            "NVDL",
            spread=None,
            volume=12_000_000,
            dollar=400_000_000,
            aum=3_000_000_000,
            expense=1.05,
            price=36.0,
            history=900,
        ),
    ]
    scores = score_vehicle_group(_entry(), rows)
    nvdl = next(score for score in scores if score.vehicle_symbol == "NVDL")
    assert nvdl.eligible is True
    assert nvdl.score > 0


def test_unknown_spread_challenger_cannot_displace_known_spread_incumbent() -> None:
    rows = [
        _evidence(
            "NVDX",
            spread=0.15,
            volume=5_000_000,
            dollar=120_000_000,
            aum=400_000_000,
            expense=1.05,
            price=20.0,
            history=700,
        ),
        _evidence(
            "NVDL",
            spread=None,
            volume=20_000_000,
            dollar=900_000_000,
            aum=6_000_000_000,
            expense=0.95,
            price=30.0,
            history=1200,
        ),
    ]
    selected, scores = choose_preferred_vehicle(_entry(), rows, switch_threshold_points=0.0)
    assert scores[0].vehicle_symbol == "NVDL"
    assert selected == "NVDX"


def test_unknown_spread_can_be_selected_when_no_eligible_incumbent_exists() -> None:
    entry = UnderlyingVehicleRegistry(
        underlying_symbol="NVDA",
        preferred_vehicle="NVDX",
        vehicles=(VehicleDefinition("NVDX"), VehicleDefinition("NVDL")),
    )
    rows = [
        _evidence(
            "NVDX",
            spread=0.05,
            volume=10_000_000,
            dollar=400_000_000,
            aum=2_000_000_000,
            expense=1.0,
            price=20.0,
            history=1000,
            active=False,
        ),
        _evidence(
            "NVDL",
            spread=None,
            volume=5_000_000,
            dollar=150_000_000,
            aum=500_000_000,
            expense=1.05,
            price=35.0,
            history=800,
        ),
    ]
    selected, _ = choose_preferred_vehicle(entry, rows)
    assert selected == "NVDL"
