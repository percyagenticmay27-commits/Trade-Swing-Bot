import json
from datetime import date

from swing_trade_bot.promotion_readiness_runtime import build_promotion_readiness_from_runtime


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _theme_block(score=75):
    return {
        "score": score,
        "components": {
            "evidence_breadth": 75,
            "source_class_diversity": 66.67,
            "catalyst_support": 60,
            "market_confirmation": 80,
            "sector_confirmation": 70,
        },
        "evidence_timestamp": "2026-09-04T17:37:51Z",
        "provenance": "AI_CIO_ENTERPRISE_DISCOVERY:test",
    }


def _theme_bucket(tmp_path, symbol="NVDA", score=75, include=True):
    path = tmp_path / "enterprise_swing_discovery_bucket.json"
    candidates = [{"underlying_symbol": symbol, "theme_strength": _theme_block(score)}] if include else [{"underlying_symbol": symbol}]
    _write(path, {"candidates": candidates})
    return path


def _build(tmp_path, **kwargs):
    kwargs.setdefault("theme_strength_path", _theme_bucket(tmp_path))
    kwargs.setdefault("as_of", date(2026, 9, 4))
    return build_promotion_readiness_from_runtime(tmp_path, **kwargs)


def test_runtime_adapter_joins_by_underlying_and_uses_authoritative_theme_strength(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":6,"financial_health_score":80,"themes":"Semiconductors","theme_momentum_score":12.5}]})
    _write(tmp_path / "opportunity_quality_report.json", {"rows":[{"symbol":"NVDA","opportunity_quality_score":82.854}]})
    _write(tmp_path / "entry_score_report.json", {"rows":[{"underlying_symbol":"NVDA","entry_score":70}]})
    _write(tmp_path / "thesis_monitor_v2_report.json", {"reviews":[{"underlying_symbol":"NVDA","evidence_status":"AVAILABLE","thesis_intact":True}]})
    result = _build(tmp_path)[0]
    assert result.underlying_symbol == "NVDA"
    assert result.leveraged_symbol == "NVDX"
    assert result.opportunity_quality.value == 82.854
    assert result.entry.value == 70
    assert result.thesis_integrity.status == "PASS"
    assert result.theme_strength.status == "PASS"
    assert result.theme_strength.value == 75
    assert "enterprise_swing_discovery_bucket.json" in result.theme_strength.evidence_source
    assert result.promotion_ready is True


def test_missing_authoritative_theme_strength_is_pending_without_momentum_fallback(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":6,"financial_health_score":80,"themes":"Semiconductors","theme_momentum_score":99}]})
    bucket = _theme_bucket(tmp_path, include=False)
    result = build_promotion_readiness_from_runtime(tmp_path, theme_strength_path=bucket, as_of=date(2026, 9, 4))[0]
    assert result.theme_strength.status == "PENDING"
    assert result.theme_strength.value is None
    assert result.promotion_ready is False


def test_authoritative_theme_strength_fail_overrides_high_theme_momentum(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":6,"financial_health_score":80,"themes":"Semiconductors","theme_momentum_score":99}]})
    bucket = _theme_bucket(tmp_path, score=52.99)
    result = build_promotion_readiness_from_runtime(tmp_path, theme_strength_path=bucket, as_of=date(2026, 9, 4))[0]
    assert result.theme_strength.status == "FAIL"
    assert result.theme_strength.value == 52.99


def test_missing_authoritative_report_is_pending_not_zero(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":5,"financial_health_score":75,"themes":"Semiconductors","theme_momentum_score":75}]})
    result = _build(tmp_path)[0]
    assert result.theme_strength.status == "PASS"
    assert result.opportunity_quality.status == "PENDING"
    assert result.opportunity_quality.value is None
    assert result.entry.status == "PENDING"
    assert result.thesis_integrity.status == "PENDING"
    assert result.promotion_ready is False


def test_legacy_zero_financial_health_is_pending(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","watchlist_status":"WATCHLIST","source_confluence_score":0,"financial_health_score":0,"themes":"Semiconductors","theme_momentum_score":0}]})
    result = _build(tmp_path)[0]
    assert result.trusted_sources.status == "FAIL"
    assert result.financial_health.status == "PENDING"
    assert result.financial_health.value is None
    assert result.theme_strength.status == "PASS"


def test_stale_watchlist_does_not_mask_current_external_theme_strength(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"STALE","rows":[{"underlying_symbol":"NVDA","watchlist_status":"WATCHLIST","source_confluence_score":7,"financial_health_score":90,"themes":"Semiconductors","theme_momentum_score":90}]})
    result = _build(tmp_path)[0]
    assert result.trusted_sources.status == "PENDING"
    assert result.financial_health.status == "PENDING"
    assert result.theme_strength.status == "PASS"


def test_thesis_v2_reviews_false_is_fail_not_pending(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":6,"financial_health_score":80,"themes":"Semiconductors","theme_momentum_score":75}]})
    _write(tmp_path / "thesis_monitor_v2_report.json", {"reviews":[{"underlying_symbol":"NVDA","evidence_status":"AVAILABLE","thesis_intact":False}]})
    result = _build(tmp_path)[0]
    assert result.thesis_integrity.status == "FAIL"
    assert result.thesis_integrity.value is False


def test_thesis_v2_unavailable_evidence_is_pending_even_if_intact_true(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":6,"financial_health_score":80,"themes":"Semiconductors","theme_momentum_score":75}]})
    _write(tmp_path / "thesis_monitor_v2_report.json", {"reviews":[{"underlying_symbol":"NVDA","evidence_status":"UNAVAILABLE","thesis_intact":True}]})
    result = _build(tmp_path)[0]
    assert result.thesis_integrity.status == "PENDING"
    assert result.thesis_integrity.value is None
