from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.discovery_engine import CandidateState
from swing_trade_bot.enterprise_candidate_state import load_candidate_state, persist_candidate_state
from swing_trade_bot.oq_watchlist_sync import synchronize_oq_watchlist_state


def _registry(root: Path) -> None:
    path = root / "configs" / "swing_leveraged_vehicle_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [
            {"underlying_symbol": "NVDA", "preferred_vehicle": "NVDX", "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}]},
            {"underlying_symbol": "PLTR", "preferred_vehicle": "PLTU", "vehicles": [{"symbol": "PLTU", "verified": True, "enabled": True}]},
            {"underlying_symbol": "AMZN", "preferred_vehicle": "AMZU", "vehicles": [{"symbol": "AMZU", "verified": True, "enabled": True}]},
            {"underlying_symbol": "GOOGL", "preferred_vehicle": "GGLL", "vehicles": [{"symbol": "GGLL", "verified": True, "enabled": True}]},
        ],
    }), encoding="utf-8")


def _review(root: Path, selected: list[str]) -> None:
    path = root / "results" / "weekly_mapped_universe_review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "rows": [
            {"underlying_symbol": symbol, "selected_for_watchlist": symbol in selected}
            for symbol in ("NVDA", "PLTR", "AMZN", "GOOGL")
        ],
    }), encoding="utf-8")


def _state(root: Path, candidates: list[CandidateState]) -> None:
    persist_candidate_state(candidates, root=root)


def test_selected_discovery_and_monitor_are_promoted_to_watchlist(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["NVDA", "PLTR"])
    _state(tmp_path, [
        CandidateState("NVDA", "NVDX", status="DISCOVERY", days_in_status=8),
        CandidateState("PLTR", "PLTU", status="MONITOR", days_in_status=3),
    ])
    report = synchronize_oq_watchlist_state(root=tmp_path)
    candidates, _ = load_candidate_state(root=tmp_path)
    by_symbol = {row.underlying_symbol: row for row in candidates}
    assert by_symbol["NVDA"].status == "WATCHLIST"
    assert by_symbol["PLTR"].status == "WATCHLIST"
    assert by_symbol["NVDA"].days_in_status == 0
    assert sorted(report["promoted_to_watchlist"]) == ["NVDA", "PLTR"]


def test_existing_low_medium_high_and_watchlist_states_are_preserved(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["NVDA", "PLTR", "AMZN"])
    _state(tmp_path, [
        CandidateState("NVDA", "NVDX", status="LOW", paper_return=12.0, win_rate=58.0, days_in_status=40),
        CandidateState("PLTR", "PLTU", status="HIGH", paper_return=22.0, win_rate=70.0, days_in_status=10),
        CandidateState("AMZN", "AMZU", status="WATCHLIST", days_in_status=9),
    ])
    report = synchronize_oq_watchlist_state(root=tmp_path)
    candidates, _ = load_candidate_state(root=tmp_path)
    by_symbol = {row.underlying_symbol: row for row in candidates}
    assert by_symbol["NVDA"].status == "LOW"
    assert by_symbol["NVDA"].paper_return == 12.0
    assert by_symbol["NVDA"].days_in_status == 40
    assert by_symbol["PLTR"].status == "HIGH"
    assert by_symbol["AMZN"].status == "WATCHLIST"
    assert sorted(report["retained_existing_lifecycle"]) == ["AMZN", "NVDA", "PLTR"]


def test_nonselected_candidate_is_not_promoted_or_demoted(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["NVDA"])
    _state(tmp_path, [
        CandidateState("NVDA", "NVDX", status="DISCOVERY"),
        CandidateState("GOOGL", "GGLL", status="MONITOR", days_in_status=12),
    ])
    synchronize_oq_watchlist_state(root=tmp_path)
    candidates, _ = load_candidate_state(root=tmp_path)
    by_symbol = {row.underlying_symbol: row for row in candidates}
    assert by_symbol["GOOGL"].status == "MONITOR"
    assert by_symbol["GOOGL"].days_in_status == 12


def test_active_veto_blocks_oq_progression_and_preserves_state(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["NVDA"])
    _state(tmp_path, [CandidateState("NVDA", "NVDX", status="DISCOVERY", days_in_status=7)])
    ledger = tmp_path / "results" / "user_veto_ledger.json"
    ledger.write_text(json.dumps({
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "approval_required": False,
        "events": [{"symbol": "NVDA", "action": "VETO"}],
    }), encoding="utf-8")
    report = synchronize_oq_watchlist_state(root=tmp_path)
    candidates, _ = load_candidate_state(root=tmp_path)
    assert candidates[0].status == "DISCOVERY"
    assert candidates[0].days_in_status == 7
    assert report["veto_blocked"] == ["NVDA"]


def test_removed_candidate_is_not_resurrected(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["NVDA"])
    _state(tmp_path, [CandidateState("NVDA", "NVDX", status="REMOVED")])
    report = synchronize_oq_watchlist_state(root=tmp_path)
    candidates, _ = load_candidate_state(root=tmp_path)
    assert candidates[0].status == "REMOVED"
    assert report["removed_state_preserved"] == ["NVDA"]


def test_missing_selected_candidate_is_added_from_verified_mapping_only(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["AMZN"])
    _state(tmp_path, [CandidateState("GOOGL", "GGLL", status="DISCOVERY")])
    report = synchronize_oq_watchlist_state(root=tmp_path)
    candidates, _ = load_candidate_state(root=tmp_path)
    by_symbol = {row.underlying_symbol: row for row in candidates}
    assert by_symbol["AMZN"].leveraged_symbol == "AMZU"
    assert by_symbol["AMZN"].status == "WATCHLIST"
    assert report["added_to_watchlist"] == ["AMZN"]


def test_sync_is_paper_only_and_does_not_bypass_entry_or_create_positions(tmp_path: Path) -> None:
    _registry(tmp_path)
    _review(tmp_path, ["NVDA"])
    _state(tmp_path, [CandidateState("NVDA", "NVDX", status="DISCOVERY")])
    report = synchronize_oq_watchlist_state(root=tmp_path)
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False
    assert report["capital_movement_enabled"] is False
    assert report["position_creation_allowed"] is False
    assert report["entry_score_bypassed"] is False
    assert not (tmp_path / "results" / "paper_ledger" / "open_positions.json").exists()
