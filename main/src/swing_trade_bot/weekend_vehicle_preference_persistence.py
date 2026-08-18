"""Persist approved weekend leveraged-vehicle preferences for future candidates only.

This module updates Swing-owned mapping configuration after a completed weekend
review. It never changes open positions, lifecycle state, portfolio state, broker
state, or order state. Only already-verified registered vehicles may become the
preferred vehicle. Writes are atomic and the legacy discovery mapping is kept in
sync for backward-compatible candidate intake.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

STRATEGY_ID = "SWING-001"
REGISTRY_SCHEMA_VERSION = "2.0"
LEGACY_MAPPING_SCHEMA_VERSION = "1.0"
DEFAULT_REGISTRY_PATH = Path("configs/swing_leveraged_vehicle_registry.json")
DEFAULT_LEGACY_MAPPING_PATH = Path("configs/swing_discovery_leveraged_mapping.json")


def _load_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    temp.write_text(json.dumps(dict(payload), indent=2) + "\n", encoding="utf-8")
    temp.replace(destination)
    return destination


def _validated_review_preferences(review: Mapping[str, Any]) -> dict[str, str]:
    if str(review.get("strategy_id", "")).strip() != STRATEGY_ID:
        raise ValueError(f"review strategy_id must be {STRATEGY_ID}")
    if review.get("paper_trade_mode") is not True:
        raise ValueError("review must be paper_trade_mode=true")
    if review.get("existing_positions_unchanged") is not True:
        raise ValueError("review must preserve existing positions")
    if str(review.get("selection_scope", "")).strip() != "FUTURE_NEW_CANDIDATES_ONLY":
        raise ValueError("review selection_scope must be FUTURE_NEW_CANDIDATES_ONLY")
    raw = review.get("preferred_vehicle_mapping")
    if not isinstance(raw, Mapping):
        raise ValueError("review preferred_vehicle_mapping must be an object")
    result: dict[str, str] = {}
    for underlying, vehicle in raw.items():
        u = str(underlying).strip().upper()
        v = str(vehicle).strip().upper()
        if not u or not v:
            raise ValueError("review preferred vehicle entries must be non-empty")
        result[u] = v
    return result


def apply_reviewed_preferences(
    review: Mapping[str, Any],
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    legacy_mapping_path: str | Path = DEFAULT_LEGACY_MAPPING_PATH,
) -> dict[str, Any]:
    """Persist approved preferences without touching positions or unverified mappings."""
    preferred = _validated_review_preferences(review)
    registry = _load_object(registry_path)
    legacy = _load_object(legacy_mapping_path)

    if str(registry.get("schema_version", "")) != REGISTRY_SCHEMA_VERSION:
        raise ValueError("vehicle registry schema_version must be 2.0")
    if str(registry.get("strategy_id", "")) != STRATEGY_ID:
        raise ValueError(f"vehicle registry strategy_id must be {STRATEGY_ID}")
    if registry.get("paper_trade_mode") is not True:
        raise ValueError("vehicle registry must be paper_trade_mode=true")
    if str(legacy.get("schema_version", "")) != LEGACY_MAPPING_SCHEMA_VERSION:
        raise ValueError("legacy leveraged mapping schema_version must be 1.0")
    if str(legacy.get("strategy_id", "")) != STRATEGY_ID:
        raise ValueError(f"legacy leveraged mapping strategy_id must be {STRATEGY_ID}")

    updated_registry = deepcopy(registry)
    updated_legacy = deepcopy(legacy)
    registry_rows = updated_registry.get("mappings")
    legacy_rows = updated_legacy.get("mappings")
    if not isinstance(registry_rows, list) or not isinstance(legacy_rows, list):
        raise ValueError("mapping files must contain mappings lists")

    registry_index = {
        str(row.get("underlying_symbol", "")).strip().upper(): row
        for row in registry_rows
        if isinstance(row, dict)
    }
    legacy_index = {
        str(row.get("underlying_symbol", "")).strip().upper(): row
        for row in legacy_rows
        if isinstance(row, dict)
    }

    changes: list[dict[str, str]] = []
    for underlying, reviewed_vehicle in sorted(preferred.items()):
        row = registry_index.get(underlying)
        if row is None:
            raise ValueError(f"review references unregistered underlying {underlying}")
        vehicles = row.get("vehicles")
        if not isinstance(vehicles, list):
            raise ValueError(f"registry vehicles missing for {underlying}")
        approved = {
            str(vehicle.get("symbol", "")).strip().upper()
            for vehicle in vehicles
            if isinstance(vehicle, Mapping)
            and vehicle.get("enabled", True) is True
            and vehicle.get("verified", True) is True
        }
        if reviewed_vehicle not in approved:
            raise ValueError(
                f"reviewed preference {underlying}->{reviewed_vehicle} is not enabled and verified"
            )
        previous = str(row.get("preferred_vehicle", "")).strip().upper() or None
        if previous != reviewed_vehicle:
            changes.append(
                {
                    "underlying_symbol": underlying,
                    "previous_preferred_vehicle": previous or "",
                    "new_preferred_vehicle": reviewed_vehicle,
                }
            )
        row["preferred_vehicle"] = reviewed_vehicle

        legacy_row = legacy_index.get(underlying)
        if legacy_row is None:
            legacy_row = {
                "underlying_symbol": underlying,
                "leveraged_symbol": reviewed_vehicle,
                "enabled": True,
            }
            legacy_rows.append(legacy_row)
            legacy_index[underlying] = legacy_row
        else:
            legacy_row["leveraged_symbol"] = reviewed_vehicle
            legacy_row["enabled"] = True

    _atomic_write_json(registry_path, updated_registry)
    _atomic_write_json(legacy_mapping_path, updated_legacy)
    return {
        "schema_version": "1.0",
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "selection_scope": "FUTURE_NEW_CANDIDATES_ONLY",
        "existing_positions_unchanged": True,
        "preference_change_count": len(changes),
        "changes": changes,
        "registry_path": str(registry_path),
        "legacy_mapping_path": str(legacy_mapping_path),
        "broker_execution_allowed": False,
        "order_placement_allowed": False,
    }
