from __future__ import annotations

import json
from pathlib import Path

import swing_trade_bot.weekend_vehicle_maintenance as module


def test_maintenance_writes_review_then_persists_approved_preferences(tmp_path, monkeypatch) -> None:
    review = {
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "reviewed_on": "2026-08-23",
        "selection_scope": "FUTURE_NEW_CANDIDATES_ONLY",
        "existing_positions_unchanged": True,
        "verified_vehicle_evidence_count": 3,
        "unverified_vehicle_candidate_count": 1,
        "preferred_vehicle_mapping": {"NVDA": "NVDX"},
    }
    calls: list[str] = []

    monkeypatch.setattr(module, "build_weekend_vehicle_review", lambda **kwargs: review)

    def fake_write(payload, path):
        calls.append("review")
        Path(path).write_text(json.dumps(payload), encoding="utf-8")
        return Path(path)

    def fake_apply(payload, **kwargs):
        assert calls == ["review"]
        calls.append("persist")
        return {
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "preference_change_count": 0,
            "changes": [],
        }

    monkeypatch.setattr(module, "write_weekend_vehicle_review", fake_write)
    monkeypatch.setattr(module, "apply_reviewed_preferences", fake_apply)

    result = module.run_weekend_vehicle_maintenance(
        review_output_path=tmp_path / "review.json",
        persistence_report_path=tmp_path / "persist.json",
        force=True,
    )
    assert calls == ["review", "persist"]
    assert result["preference_change_count"] == 0
    assert result["selection_scope"] == "FUTURE_NEW_CANDIDATES_ONLY"
    assert result["existing_positions_unchanged"] is True
    assert json.loads((tmp_path / "persist.json").read_text(encoding="utf-8"))["preference_change_count"] == 0


def test_no_broker_or_order_execution_is_introduced() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("place_order", "submit_order", "execute_trade", "broker_adapter", "robinhood")
    assert all(term not in source for term in forbidden)
