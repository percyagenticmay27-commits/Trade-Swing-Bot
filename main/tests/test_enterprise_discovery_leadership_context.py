from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.enterprise_discovery_leadership_context import (
    build_discovery_leadership_context,
    refresh_enterprise_discovery_leadership_context,
)


def _bucket(candidate: dict) -> dict:
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "generated_at_utc": "2026-08-21T20:00:00Z",
        "candidates": [candidate],
    }


def _enriched_candidate() -> dict:
    return {
        "underlying_symbol": "AMAT",
        "discovery_status": "RISING",
        "evidence_sources": [],
        "discovery_leadership_score": 67.692308,
        "discovery_leadership_classification": "STRONG",
        "relative_leadership": {
            "benchmark_symbol": "SPY",
            "evidence_status": "AVAILABLE",
            "leadership_score": 72.5,
            "leadership_classification": "LEADER",
            "evaluated_horizons": 4,
            "leader_horizons": 3,
            "leadership_persistence": 0.75,
            "stock_history_source": "AI_CIO_MARKET_HISTORY",
            "benchmark_history_source": "AI_CIO_MARKET_HISTORY",
            "warnings": [],
            "horizons": {
                "3m": {
                    "stock_return_pct": 30.0,
                    "benchmark_return_pct": 10.0,
                    "relative_outperformance_pct": 20.0,
                    "relative_multiple": 3.0,
                    "leadership_classification": "LEADER",
                    "trapper_2x_spy_evidence": True,
                    "period_start": "2026-05-21",
                    "period_end": "2026-08-21",
                    "freshness_days": 0,
                }
            },
        },
        "sector_leadership": {"classification": "LEADING"},
        "industry_leadership": {"classification": "LEADING"},
        "theme_leadership": {"classification": "RISING"},
        "discovery_reasons": ["OUTPERFORMING_SPY", "LEADING_INDUSTRY"],
        "discovery_warnings": ["PARTIAL_1M_HISTORY"],
    }


def test_legacy_schema_1_bucket_without_leadership_still_builds_context() -> None:
    payload = build_discovery_leadership_context(
        _bucket({"underlying_symbol": "NVDA", "discovery_status": "RISING", "evidence_sources": []})
    )
    assert payload["schema_version"] == "1.0"
    assert payload["strategy_id"] == "SWING-001"
    assert payload["candidate_count"] == 1
    assert payload["leadership_enriched_candidate_count"] == 0
    assert payload["candidates"][0] == {
        "underlying_symbol": "NVDA",
        "discovery_status": "RISING",
    }


def test_enriched_leadership_fields_survive_ingestion_unchanged() -> None:
    candidate = _enriched_candidate()
    payload = build_discovery_leadership_context(_bucket(candidate))
    row = payload["candidates"][0]

    for field in (
        "discovery_leadership_score",
        "discovery_leadership_classification",
        "relative_leadership",
        "sector_leadership",
        "industry_leadership",
        "theme_leadership",
        "discovery_reasons",
        "discovery_warnings",
    ):
        assert row[field] == candidate[field]

    assert row["relative_leadership"]["horizons"]["3m"]["trapper_2x_spy_evidence"] is True
    assert row["relative_leadership"]["leadership_persistence"] == 0.75


def test_missing_leadership_is_not_converted_to_zero() -> None:
    payload = build_discovery_leadership_context(
        _bucket({"underlying_symbol": "ULTA", "discovery_status": "EMERGING", "evidence_sources": []})
    )
    row = payload["candidates"][0]
    assert "discovery_leadership_score" not in row
    assert "relative_leadership" not in row


def test_discovery_warnings_survive_context_unchanged() -> None:
    candidate = _enriched_candidate()
    payload = build_discovery_leadership_context(_bucket(candidate))
    assert payload["candidates"][0]["discovery_warnings"] == ["PARTIAL_1M_HISTORY"]
    assert payload["discovery_warning_count"] == 1


def test_trapper_evidence_remains_upstream_context_only() -> None:
    payload = build_discovery_leadership_context(_bucket(_enriched_candidate()))
    assert payload["leadership_owner"] == "AI_CIO"
    assert payload["leadership_recalculated_by_swing"] is False
    assert payload["leadership_used_as_automatic_buy_signal"] is False
    assert payload["opportunity_quality_weights_changed"] is False
    assert payload["entry_score_changed"] is False


def test_strong_or_leader_classification_does_not_create_buy_or_execution_fields() -> None:
    payload = build_discovery_leadership_context(_bucket(_enriched_candidate()))
    serialized = json.dumps(payload).lower()
    forbidden = (
        '"buy"',
        '"paper_buy"',
        '"entry_eligible"',
        '"place_order"',
        '"execute_trade"',
        '"broker_order"',
    )
    assert all(term not in serialized for term in forbidden)
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False


def test_refresh_reads_existing_consumer_contract_and_writes_context(tmp_path: Path) -> None:
    swing = tmp_path / "swing"
    ai_cio = tmp_path / "ai-cio"
    (swing / "results").mkdir(parents=True)
    bucket_path = ai_cio / "results/enterprise_swing_discovery_bucket.json"
    bucket_path.parent.mkdir(parents=True)
    bucket_path.write_text(json.dumps(_bucket(_enriched_candidate())), encoding="utf-8")

    report = refresh_enterprise_discovery_leadership_context(
        swing_root=swing,
        ai_cio_repository=ai_cio,
    )

    assert report["source_bucket_available"] is True
    assert report["source_bucket_schema_version"] == "1.0"
    assert report["source_bucket_strategy_id"] == "SWING-001"
    output = swing / "results/enterprise_discovery_leadership_context.json"
    assert output.is_file()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["candidates"][0]["discovery_leadership_score"] == 67.692308


def test_missing_bucket_writes_empty_backward_compatible_context(tmp_path: Path) -> None:
    swing = tmp_path / "swing"
    ai_cio = tmp_path / "ai-cio"
    (swing / "results").mkdir(parents=True)

    report = refresh_enterprise_discovery_leadership_context(
        swing_root=swing,
        ai_cio_repository=ai_cio,
    )

    assert report["source_bucket_available"] is False
    assert report["candidate_count"] == 0
    assert report["leadership_enriched_candidate_count"] == 0
