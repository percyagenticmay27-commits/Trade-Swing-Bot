import json
from datetime import date

import pytest

from swing_trade_bot.enterprise_theme_strength import (
    load_enterprise_theme_strength,
    parse_enterprise_theme_strength,
)


def _block(**overrides):
    payload = {
        "score": 72.5,
        "components": {
            "evidence_breadth": 75.0,
            "source_class_diversity": 66.67,
            "catalyst_support": 60.0,
            "market_confirmation": 80.0,
            "sector_confirmation": 70.0,
        },
        "evidence_timestamp": "2026-09-04T17:37:51Z",
        "provenance": "AI_CIO_ENTERPRISE_DISCOVERY:test",
    }
    payload.update(overrides)
    return payload


def test_parse_complete_current_theme_strength():
    evidence = parse_enterprise_theme_strength("nvda", _block(), as_of=date(2026, 9, 4))
    assert evidence.underlying_symbol == "NVDA"
    assert evidence.score == 72.5
    assert evidence.components["catalyst_support"] == 60.0
    assert evidence.freshness_status == "CURRENT"


def test_missing_component_fails_closed():
    block = _block()
    del block["components"]["market_confirmation"]
    with pytest.raises(ValueError, match="missing required theme-strength component market_confirmation"):
        parse_enterprise_theme_strength("NVDA", block, as_of=date(2026, 9, 4))


def test_missing_provenance_fails_closed():
    with pytest.raises(ValueError, match="provenance is required"):
        parse_enterprise_theme_strength("NVDA", _block(provenance=""), as_of=date(2026, 9, 4))


def test_stale_theme_strength_is_rejected():
    with pytest.raises(ValueError, match="stale"):
        parse_enterprise_theme_strength(
            "NVDA",
            _block(evidence_timestamp="2026-08-20T12:00:00Z"),
            as_of=date(2026, 9, 4),
        )


def test_load_bucket_accepts_valid_and_rejects_missing(tmp_path):
    bucket = tmp_path / "bucket.json"
    bucket.write_text(json.dumps({
        "candidates": [
            {"underlying_symbol": "NVDA", "theme_strength": _block()},
            {"underlying_symbol": "AMZN"},
        ]
    }), encoding="utf-8")

    accepted, audit, warnings = load_enterprise_theme_strength(bucket, as_of=date(2026, 9, 4))

    assert accepted["NVDA"].score == 72.5
    assert "AMZN" not in accepted
    assert any(row["underlying_symbol"] == "NVDA" and row["accepted"] is True for row in audit)
    assert any(row["underlying_symbol"] == "AMZN" and row["status"] == "MISSING_ENTERPRISE_THEME_STRENGTH" for row in audit)
    assert "MISSING_REQUIRED_THEME_STRENGTH:AMZN" in warnings
