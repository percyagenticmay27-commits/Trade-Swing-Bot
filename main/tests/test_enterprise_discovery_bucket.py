from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from swing_trade_bot.discovery_engine import CandidateState, SourceMention
from swing_trade_bot.enterprise_discovery_bucket import (
    bucket_mentions,
    discover_bucket_path,
    load_discovery_bucket,
    load_leveraged_mapping,
    merge_bucket_candidates,
    merge_mentions,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _bucket(*candidates: dict) -> dict:
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "generated_at_utc": "2026-08-17T20:00:00Z",
        "candidates": list(candidates),
    }


def _mapping(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "mappings": [
                {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "enabled": True},
                {"underlying_symbol": "PLTR", "leveraged_symbol": "PLTU", "enabled": True},
            ],
        },
    )


def test_discover_bucket_path_is_read_only_repository_relative(tmp_path: Path) -> None:
    assert discover_bucket_path(repository_root=tmp_path) == tmp_path / "results/enterprise_swing_discovery_bucket.json"


def test_bucket_requires_schema_strategy_and_candidate_list(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "bucket.json", {"schema_version": "0.9", "candidates": []})
    with pytest.raises(ValueError, match="schema_version"):
        load_discovery_bucket(path)

    path = _write_json(
        tmp_path / "bucket.json",
        {"schema_version": "1.0", "strategy_id": "DIVIDEND-001", "candidates": []},
    )
    with pytest.raises(ValueError, match="SWING-001"):
        load_discovery_bucket(path)


def test_duplicate_underlying_is_rejected(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "bucket.json",
        _bucket(
            {"underlying_symbol": "NVDA", "discovery_status": "HOT"},
            {"underlying_symbol": "nvda", "discovery_status": "RISING"},
        ),
    )
    with pytest.raises(ValueError, match="duplicate underlying_symbol NVDA"):
        load_discovery_bucket(path)


def test_mapping_is_explicit_and_rejects_duplicate_underlying(tmp_path: Path) -> None:
    mapping = load_leveraged_mapping(_mapping(tmp_path / "mapping.json"))
    assert mapping == {"NVDA": "NVDX", "PLTR": "PLTU"}

    path = _write_json(
        tmp_path / "bad.json",
        {
            "schema_version": "1.0",
            "mappings": [
                {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX"},
                {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDL"},
            ],
        },
    )
    with pytest.raises(ValueError, match="duplicate leveraged mapping"):
        load_leveraged_mapping(path)


def test_hot_rising_emerging_mapped_underlyings_enter_discovery_only(tmp_path: Path) -> None:
    mapping = load_leveraged_mapping(_mapping(tmp_path / "mapping.json"))
    bucket = _bucket(
        {
            "underlying_symbol": "NVDA",
            "discovery_status": "HOT",
            "themes": ["AI Infrastructure", "Semiconductors"],
        },
        {
            "underlying_symbol": "PLTR",
            "discovery_status": "RISING",
            "themes": ["Defense Tech"],
        },
    )
    merged, warnings = merge_bucket_candidates([], bucket, mapping)
    assert warnings == []
    assert [(row.underlying_symbol, row.leveraged_symbol, row.status) for row in merged] == [
        ("NVDA", "NVDX", "DISCOVERY"),
        ("PLTR", "PLTU", "DISCOVERY"),
    ]
    assert all(row.number_of_trades == 0 and row.trading_days == 0 for row in merged)


def test_bucket_cannot_promote_or_reset_existing_swing_state() -> None:
    existing = [
        CandidateState(
            underlying_symbol="NVDA",
            leveraged_symbol="NVDX",
            status="WATCHLIST",
            paper_return=12.0,
            win_rate=55.0,
            profit_factor=1.8,
            number_of_trades=12,
            trading_days=95,
            days_in_status=20,
            themes=("Semiconductors",),
        )
    ]
    bucket = _bucket(
        {
            "underlying_symbol": "NVDA",
            "discovery_status": "HOT",
            "themes": ["AI Infrastructure"],
        }
    )
    merged, warnings = merge_bucket_candidates(existing, bucket, {"NVDA": "OTHER"})
    assert warnings == []
    row = merged[0]
    assert row.status == "WATCHLIST"
    assert row.leveraged_symbol == "NVDX"
    assert row.paper_return == 12.0
    assert row.number_of_trades == 12
    assert row.themes == ("Semiconductors", "AI Infrastructure")


def test_unmapped_new_underlying_is_not_inserted_and_warns() -> None:
    bucket = _bucket(
        {"underlying_symbol": "UNKNOWN", "discovery_status": "HOT", "themes": ["AI Infrastructure"]}
    )
    merged, warnings = merge_bucket_candidates([], bucket, {})
    assert merged == []
    assert warnings == ["NO_APPROVED_LEVERAGED_MAPPING:UNKNOWN"]


def test_cooling_and_declining_are_not_new_swing_candidates() -> None:
    bucket = _bucket(
        {"underlying_symbol": "NVDA", "discovery_status": "COOLING"},
        {"underlying_symbol": "PLTR", "discovery_status": "DECLINING"},
    )
    merged, warnings = merge_bucket_candidates([], bucket, {"NVDA": "NVDX", "PLTR": "PLTU"})
    assert merged == []
    assert warnings == []


def test_bucket_evidence_translates_to_source_mentions() -> None:
    bucket = _bucket(
        {
            "underlying_symbol": "NVDA",
            "discovery_status": "RISING",
            "themes": ["Semiconductors"],
            "evidence_sources": [
                {
                    "source": "Reuters",
                    "mentioned_on": "2026-08-16",
                    "themes": ["AI Infrastructure"],
                    "earnings_growth_related": True,
                },
                {
                    "source": "Bloomberg",
                    "mentioned_on": "2026-08-17",
                    "analyst_upgrade_related": True,
                },
            ],
        }
    )
    mentions = bucket_mentions(bucket)
    assert len(mentions) == 2
    assert mentions[0].underlying_symbol == "NVDA"
    assert mentions[0].mentioned_on == date(2026, 8, 16)
    assert mentions[0].themes == ("Semiconductors", "AI Infrastructure")
    assert mentions[0].earnings_growth_related is True
    assert mentions[1].analyst_upgrade_related is True


def test_duplicate_local_and_enterprise_mentions_are_deduplicated() -> None:
    mention = SourceMention(
        underlying_symbol="NVDA",
        source="Reuters",
        mentioned_on=date(2026, 8, 16),
        themes=("Semiconductors",),
    )
    merged = merge_mentions([mention], [mention])
    assert merged == [mention]


def test_no_broker_execution_or_order_api_is_exposed() -> None:
    import swing_trade_bot.enterprise_discovery_bucket as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("robinhood", "place_order", "submit_order", "execute_trade", "broker_adapter")
    assert all(term not in source for term in forbidden)
