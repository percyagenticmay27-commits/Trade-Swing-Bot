from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.weekend_vehicle_preference_persistence import apply_reviewed_preferences


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _registry() -> dict:
    return {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mappings": [
            {
                "underlying_symbol": "NVDA",
                "preferred_vehicle": "NVDX",
                "vehicles": [
                    {"symbol": "NVDX", "enabled": True, "verified": True},
                    {"symbol": "NVDL", "enabled": True, "verified": True},
                    {"symbol": "BAD", "enabled": True, "verified": False},
                ],
            }
        ],
    }


def _legacy() -> dict:
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mappings": [
            {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "enabled": True}
        ],
    }


def _review(vehicle: str = "NVDL") -> dict:
    return {
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "selection_scope": "FUTURE_NEW_CANDIDATES_ONLY",
        "existing_positions_unchanged": True,
        "preferred_vehicle_mapping": {"NVDA": vehicle},
    }


def test_approved_preference_updates_registry_and_legacy_mapping_atomically(tmp_path: Path) -> None:
    registry = _write(tmp_path / "registry.json", _registry())
    legacy = _write(tmp_path / "legacy.json", _legacy())
    result = apply_reviewed_preferences(_review(), registry_path=registry, legacy_mapping_path=legacy)

    registry_data = json.loads(registry.read_text(encoding="utf-8"))
    legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
    assert registry_data["mappings"][0]["preferred_vehicle"] == "NVDL"
    assert legacy_data["mappings"][0]["leveraged_symbol"] == "NVDL"
    assert result["preference_change_count"] == 1
    assert result["existing_positions_unchanged"] is True
    assert not (tmp_path / "registry.json.tmp").exists()
    assert not (tmp_path / "legacy.json.tmp").exists()


def test_no_change_is_idempotent(tmp_path: Path) -> None:
    registry_payload = _registry()
    registry_payload["mappings"][0]["preferred_vehicle"] = "NVDL"
    legacy_payload = _legacy()
    legacy_payload["mappings"][0]["leveraged_symbol"] = "NVDL"
    registry = _write(tmp_path / "registry.json", registry_payload)
    legacy = _write(tmp_path / "legacy.json", legacy_payload)
    result = apply_reviewed_preferences(_review(), registry_path=registry, legacy_mapping_path=legacy)
    assert result["preference_change_count"] == 0


def test_unverified_vehicle_cannot_be_persisted(tmp_path: Path) -> None:
    registry = _write(tmp_path / "registry.json", _registry())
    legacy = _write(tmp_path / "legacy.json", _legacy())
    with pytest.raises(ValueError, match="not enabled and verified"):
        apply_reviewed_preferences(_review("BAD"), registry_path=registry, legacy_mapping_path=legacy)


def test_unknown_underlying_cannot_be_persisted(tmp_path: Path) -> None:
    registry = _write(tmp_path / "registry.json", _registry())
    legacy = _write(tmp_path / "legacy.json", _legacy())
    review = _review()
    review["preferred_vehicle_mapping"] = {"UNKNOWN": "XYZ"}
    with pytest.raises(ValueError, match="unregistered underlying"):
        apply_reviewed_preferences(review, registry_path=registry, legacy_mapping_path=legacy)


def test_review_must_preserve_future_candidate_only_scope(tmp_path: Path) -> None:
    registry = _write(tmp_path / "registry.json", _registry())
    legacy = _write(tmp_path / "legacy.json", _legacy())
    review = _review()
    review["selection_scope"] = "OPEN_POSITIONS"
    with pytest.raises(ValueError, match="FUTURE_NEW_CANDIDATES_ONLY"):
        apply_reviewed_preferences(review, registry_path=registry, legacy_mapping_path=legacy)


def test_no_broker_or_order_execution_is_introduced() -> None:
    import swing_trade_bot.weekend_vehicle_preference_persistence as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("place_order", "submit_order", "execute_trade", "broker_adapter", "robinhood")
    assert all(term not in source for term in forbidden)
