"""Persistent one-to-many leveraged vehicle registry and weekly preference review.

This module is advisory and paper-only. It never places trades, changes an existing
position, or infers ticker relationships from symbol spelling. The registry stores
verified underlying-to-vehicle relationships and chooses a preferred vehicle for
future candidate evaluation from explicit weekly market/product evidence.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

STRATEGY_ID = "SWING-001"
REGISTRY_SCHEMA_VERSION = "2.0"
DEFAULT_SWITCH_THRESHOLD_POINTS = 5.0


@dataclass(frozen=True, slots=True)
class VehicleDefinition:
    symbol: str
    enabled: bool = True
    verified: bool = True
    leverage_multiple: float | None = None
    issuer: str | None = None


@dataclass(frozen=True, slots=True)
class UnderlyingVehicleRegistry:
    underlying_symbol: str
    preferred_vehicle: str | None
    vehicles: tuple[VehicleDefinition, ...]


@dataclass(frozen=True, slots=True)
class VehicleEvidence:
    underlying_symbol: str
    vehicle_symbol: str
    price: float
    average_daily_volume: float
    average_daily_dollar_volume: float
    bid_ask_spread_pct: float
    aum: float
    expense_ratio_pct: float
    history_days: int
    product_active: bool = True


@dataclass(frozen=True, slots=True)
class VehicleScore:
    underlying_symbol: str
    vehicle_symbol: str
    score: float
    eligible: bool


def _json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def load_vehicle_registry(path: str | Path) -> dict[str, UnderlyingVehicleRegistry]:
    """Load the persistent Swing vehicle registry.

    Version 2.0 allows multiple verified vehicles per underlying. Existing lifecycle
    or open-position state is intentionally absent from this registry.
    """
    payload = _json_object(path)
    if str(payload.get("schema_version", "")).strip() != REGISTRY_SCHEMA_VERSION:
        raise ValueError("leveraged vehicle registry schema_version must be 2.0")
    if str(payload.get("strategy_id", STRATEGY_ID)).strip() != STRATEGY_ID:
        raise ValueError(f"leveraged vehicle registry strategy_id must be {STRATEGY_ID}")
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("leveraged vehicle registry mappings must be a list")

    result: dict[str, UnderlyingVehicleRegistry] = {}
    global_vehicle_owner: dict[str, str] = {}
    for index, item in enumerate(mappings):
        if not isinstance(item, Mapping):
            raise ValueError(f"mappings[{index}] must be an object")
        underlying = str(item.get("underlying_symbol", "")).strip().upper()
        if not underlying:
            raise ValueError(f"mappings[{index}].underlying_symbol is required")
        if underlying in result:
            raise ValueError(f"duplicate underlying mapping {underlying}")
        raw_vehicles = item.get("vehicles")
        if not isinstance(raw_vehicles, list) or not raw_vehicles:
            raise ValueError(f"mappings[{index}].vehicles must be a non-empty list")

        vehicles: list[VehicleDefinition] = []
        local_seen: set[str] = set()
        for vehicle_index, raw in enumerate(raw_vehicles):
            if not isinstance(raw, Mapping):
                raise ValueError(f"mappings[{index}].vehicles[{vehicle_index}] must be an object")
            symbol = str(raw.get("symbol", "")).strip().upper()
            if not symbol:
                raise ValueError(f"mappings[{index}].vehicles[{vehicle_index}].symbol is required")
            if symbol in local_seen:
                raise ValueError(f"duplicate vehicle {symbol} for {underlying}")
            prior_owner = global_vehicle_owner.get(symbol)
            if prior_owner and prior_owner != underlying:
                raise ValueError(f"vehicle {symbol} mapped to multiple underlyings")
            local_seen.add(symbol)
            global_vehicle_owner[symbol] = underlying
            leverage = raw.get("leverage_multiple")
            vehicles.append(
                VehicleDefinition(
                    symbol=symbol,
                    enabled=raw.get("enabled", True) is True,
                    verified=raw.get("verified", True) is True,
                    leverage_multiple=float(leverage) if leverage is not None else None,
                    issuer=str(raw.get("issuer")).strip() if raw.get("issuer") else None,
                )
            )

        preferred = str(item.get("preferred_vehicle", "")).strip().upper() or None
        if preferred is not None and preferred not in local_seen:
            raise ValueError(f"preferred_vehicle {preferred} is not registered for {underlying}")
        result[underlying] = UnderlyingVehicleRegistry(
            underlying_symbol=underlying,
            preferred_vehicle=preferred,
            vehicles=tuple(vehicles),
        )
    return result


def preferred_vehicle_mapping(path: str | Path) -> dict[str, str]:
    """Return only current preferred vehicles for new Swing discovery candidates."""
    registry = load_vehicle_registry(path)
    result: dict[str, str] = {}
    for underlying, entry in registry.items():
        eligible = {v.symbol for v in entry.vehicles if v.enabled and v.verified}
        if entry.preferred_vehicle and entry.preferred_vehicle in eligible:
            result[underlying] = entry.preferred_vehicle
    return result


def _relative_score(value: float, values: Sequence[float], *, higher_is_better: bool) -> float:
    if not values:
        return 0.0
    low = min(values)
    high = max(values)
    if high == low:
        return 100.0
    normalized = (value - low) / (high - low) * 100.0
    return normalized if higher_is_better else 100.0 - normalized


def score_vehicle_group(
    entry: UnderlyingVehicleRegistry,
    evidence: Sequence[VehicleEvidence],
) -> list[VehicleScore]:
    """Score verified active vehicles against peers for the same underlying.

    Weighting favors tradability first, then product cost/stability:
    25% average dollar volume, 20% share volume, 15% spread, 10% AUM,
    10% expense ratio, 10% price accessibility, and 10% trading history.
    """
    definitions = {v.symbol: v for v in entry.vehicles}
    rows = [
        row
        for row in evidence
        if row.underlying_symbol.strip().upper() == entry.underlying_symbol
        and row.vehicle_symbol.strip().upper() in definitions
    ]
    eligible_rows = [
        row
        for row in rows
        if row.product_active
        and definitions[row.vehicle_symbol.strip().upper()].enabled
        and definitions[row.vehicle_symbol.strip().upper()].verified
        and row.price > 0
        and row.average_daily_volume >= 0
        and row.average_daily_dollar_volume >= 0
        and row.bid_ask_spread_pct >= 0
        and row.aum >= 0
        and row.expense_ratio_pct >= 0
        and row.history_days >= 0
    ]
    if not eligible_rows:
        return [
            VehicleScore(entry.underlying_symbol, row.vehicle_symbol.strip().upper(), 0.0, False)
            for row in rows
        ]

    dollar = [r.average_daily_dollar_volume for r in eligible_rows]
    volume = [r.average_daily_volume for r in eligible_rows]
    spreads = [r.bid_ask_spread_pct for r in eligible_rows]
    aum = [r.aum for r in eligible_rows]
    expense = [r.expense_ratio_pct for r in eligible_rows]
    prices = [r.price for r in eligible_rows]
    history = [float(r.history_days) for r in eligible_rows]

    scores: list[VehicleScore] = []
    eligible_symbols = {r.vehicle_symbol.strip().upper() for r in eligible_rows}
    for row in rows:
        symbol = row.vehicle_symbol.strip().upper()
        if symbol not in eligible_symbols:
            scores.append(VehicleScore(entry.underlying_symbol, symbol, 0.0, False))
            continue
        score = (
            0.25 * _relative_score(row.average_daily_dollar_volume, dollar, higher_is_better=True)
            + 0.20 * _relative_score(row.average_daily_volume, volume, higher_is_better=True)
            + 0.15 * _relative_score(row.bid_ask_spread_pct, spreads, higher_is_better=False)
            + 0.10 * _relative_score(row.aum, aum, higher_is_better=True)
            + 0.10 * _relative_score(row.expense_ratio_pct, expense, higher_is_better=False)
            + 0.10 * _relative_score(row.price, prices, higher_is_better=False)
            + 0.10 * _relative_score(float(row.history_days), history, higher_is_better=True)
        )
        scores.append(VehicleScore(entry.underlying_symbol, symbol, round(score, 2), True))
    return sorted(scores, key=lambda item: (-item.score, item.vehicle_symbol))


def choose_preferred_vehicle(
    entry: UnderlyingVehicleRegistry,
    evidence: Sequence[VehicleEvidence],
    *,
    switch_threshold_points: float = DEFAULT_SWITCH_THRESHOLD_POINTS,
) -> tuple[str | None, list[VehicleScore]]:
    """Choose the preferred vehicle for future candidates only.

    The incumbent remains preferred unless a challenger beats it by at least the
    switch threshold. If the incumbent is no longer eligible, the best eligible
    challenger may replace it immediately.
    """
    if switch_threshold_points < 0:
        raise ValueError("switch_threshold_points must be nonnegative")
    scores = score_vehicle_group(entry, evidence)
    eligible = [score for score in scores if score.eligible]
    if not eligible:
        return None, scores
    best = eligible[0]
    incumbent = next(
        (score for score in eligible if score.vehicle_symbol == entry.preferred_vehicle),
        None,
    )
    if incumbent is None:
        return best.vehicle_symbol, scores
    if best.vehicle_symbol == incumbent.vehicle_symbol:
        return incumbent.vehicle_symbol, scores
    if best.score >= incumbent.score + switch_threshold_points:
        return best.vehicle_symbol, scores
    return incumbent.vehicle_symbol, scores


def build_weekly_review(
    registry: Mapping[str, UnderlyingVehicleRegistry],
    evidence: Sequence[VehicleEvidence],
    *,
    reviewed_at: str,
    switch_threshold_points: float = DEFAULT_SWITCH_THRESHOLD_POINTS,
) -> dict[str, Any]:
    """Build a paper-only weekend review report without changing positions."""
    rows: list[dict[str, Any]] = []
    preferred: dict[str, str] = {}
    for underlying in sorted(registry):
        entry = registry[underlying]
        selected, scores = choose_preferred_vehicle(
            entry,
            evidence,
            switch_threshold_points=switch_threshold_points,
        )
        if selected:
            preferred[underlying] = selected
        rows.append(
            {
                "underlying_symbol": underlying,
                "previous_preferred_vehicle": entry.preferred_vehicle,
                "reviewed_preferred_vehicle": selected,
                "preference_changed": bool(selected and selected != entry.preferred_vehicle),
                "vehicle_scores": [asdict(score) for score in scores],
            }
        )
    return {
        "schema_version": "1.0",
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "reviewed_at": reviewed_at,
        "switch_threshold_points": switch_threshold_points,
        "selection_scope": "FUTURE_NEW_CANDIDATES_ONLY",
        "existing_positions_unchanged": True,
        "preferred_vehicle_mapping": preferred,
        "rows": rows,
    }
