from __future__ import annotations

import csv
import json
from pathlib import Path

from swing_trade_bot.enterprise_candidate_state import load_candidate_state
from swing_trade_bot.enterprise_candidate_state_sync import sync_candidate_state_from_watchlist
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs


def _tree(root: Path) -> None:
    (root / "examples").mkdir(parents=True)
    (root / "results").mkdir(parents=True)
    (root / "configs").mkdir(parents=True)
    (root / "examples/discovery_candidates.csv").write_text(
        "underlying_symbol,leveraged_symbol,status,paper_return,win_rate,profit_factor,number_of_trades,trading_days,days_in_status,earnings_stability_score,leveraged_vehicle_exists,themes\n"
        "NBIS,NBIL,DISCOVERY,0,0,0,0,0,0,50,true,AI Infrastructure\n",
        encoding="utf-8",
    )
    (root / "results/discovery_mentions.csv").write_text(
        "underlying_symbol,source,mentioned_on,themes,earnings_growth_related,analyst_upgrade_related\n"
        "NBIS,Reuters,2026-08-15,AI Infrastructure,false,false\n",
        encoding="utf-8",
    )
    (root / "configs/swing_discovery_leveraged_mapping.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "SWING-001",
                "mappings": [{"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "enabled": True}],
            }
        ),
        encoding="utf-8",
    )


def _bucket(root: Path) -> Path:
    path = root / "ai/results/enterprise_swing_discovery_bucket.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "SWING-001",
                "generated_at_utc": "2026-08-18T12:00:00Z",
                "candidates": [
                    {
                        "underlying_symbol": "NVDA",
                        "discovery_status": "HOT",
                        "themes": ["Semiconductors"],
                        "evidence_sources": [
                            {"source": "Reuters", "mentioned_on": "2026-08-18"},
                            {"source": "Bloomberg", "mentioned_on": "2026-08-18"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_enterprise_candidate_is_persisted_on_first_intake(tmp_path: Path) -> None:
    _tree(tmp_path)
    _bucket(tmp_path)
    report = refresh_enterprise_discovery_inputs(swing_root=tmp_path, ai_cio_repository=tmp_path / "ai")
    assert report["candidate_state_authority"] == "SWING_OWNED_DURABLE_STATE"
    assert report["imported_new_candidate_count"] == 1
    candidates, metadata = load_candidate_state(root=tmp_path)
    nvda = next(row for row in candidates if row.underlying_symbol == "NVDA")
    assert nvda.status == "DISCOVERY"
    assert nvda.leveraged_symbol == "NVDX"
    assert metadata["NVDA"]["first_enterprise_discovered_on"] == "2026-08-18"
    assert metadata["NVDA"]["last_enterprise_nominated_on"] == "2026-08-18"


def test_cycle_progression_survives_repeated_ai_cio_nomination_and_restart(tmp_path: Path) -> None:
    _tree(tmp_path)
    _bucket(tmp_path)
    refresh_enterprise_discovery_inputs(swing_root=tmp_path, ai_cio_repository=tmp_path / "ai")

    # Simulate a legitimate DiscoveryEngine result from cycle 1.
    (tmp_path / "results/watchlist_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "underlying_symbol": "NVDA",
                        "watchlist_status": "WATCHLIST",
                        "paper_return": 0,
                        "win_rate": 0,
                        "profit_factor": 0,
                        "trading_days": 0,
                        "themes": "Semiconductors",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    sync_candidate_state_from_watchlist(root=tmp_path)

    # Cycle 2/restart: same AI CIO HOT nomination must not reset Swing state.
    report = refresh_enterprise_discovery_inputs(swing_root=tmp_path, ai_cio_repository=tmp_path / "ai")
    assert report["imported_new_candidate_count"] == 0
    assert report["existing_swing_candidates_refreshed_count"] == 1
    candidates, metadata = load_candidate_state(root=tmp_path)
    nvda = next(row for row in candidates if row.underlying_symbol == "NVDA")
    assert nvda.status == "WATCHLIST"
    assert metadata["NVDA"]["lifecycle_reason"] == "DISCOVERY_ENGINE_EVALUATION"

    with (tmp_path / "results/discovery_candidates_runtime.csv").open(newline="", encoding="utf-8") as handle:
        runtime = {row["underlying_symbol"]: row for row in csv.DictReader(handle)}
    assert runtime["NVDA"]["status"] == "WATCHLIST"


def test_ai_cio_nomination_cannot_directly_create_paper_position(tmp_path: Path) -> None:
    _tree(tmp_path)
    _bucket(tmp_path)
    refresh_enterprise_discovery_inputs(swing_root=tmp_path, ai_cio_repository=tmp_path / "ai")
    assert not (tmp_path / "results/paper_ledger/open_positions.json").exists()


def test_state_store_is_not_the_examples_fixture(tmp_path: Path) -> None:
    _tree(tmp_path)
    original = (tmp_path / "examples/discovery_candidates.csv").read_text(encoding="utf-8")
    _bucket(tmp_path)
    refresh_enterprise_discovery_inputs(swing_root=tmp_path, ai_cio_repository=tmp_path / "ai")
    assert (tmp_path / "results/discovery_candidate_state.csv").is_file()
    assert (tmp_path / "examples/discovery_candidates.csv").read_text(encoding="utf-8") == original
