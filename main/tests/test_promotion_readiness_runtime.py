import json

from swing_trade_bot.promotion_readiness_runtime import build_promotion_readiness_from_runtime


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_adapter_joins_by_underlying_and_uses_frozen_theme_gate(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"NVDA","leveraged_symbol":"NVDX","watchlist_status":"WATCHLIST","source_confluence_score":6,"financial_health_score":80,"themes":"Semiconductors","theme_momentum_score":75}]})
    _write(tmp_path / "opportunity_quality_report.json", {"rows":[{"symbol":"NVDA","opportunity_quality_score":82.854}]})
    _write(tmp_path / "entry_score_report.json", {"rows":[{"underlying_symbol":"NVDA","entry_score":70}]})
    _write(tmp_path / "thesis_monitor_v2_report.json", {"reviews":[{"underlying_symbol":"NVDA","evidence_status":"AVAILABLE","thesis_intact":True}]})
    result = build_promotion_readiness_from_runtime(tmp_path)[0]
    assert result.underlying_symbol == "NVDA"
    assert result.leveraged_symbol == "NVDX"
    assert result.opportunity_quality.value == 82.854
    assert result.entry.value == 70
    assert result.thesis_integrity.status == "PASS"
    assert result.theme_strength.status == "PASS"
    assert result.theme_strength.value == 75
    assert result.promotion_ready is True


def test_missing_authoritative_report_is_pending_not_zero(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"BE","leveraged_symbol":"BEX","watchlist_status":"WATCHLIST","source_confluence_score":5,"financial_health_score":75,"themes":"Clean Energy","theme_momentum_score":75}]})
    result = build_promotion_readiness_from_runtime(tmp_path)[0]
    assert result.theme_strength.status == "PASS"
    assert result.opportunity_quality.status == "PENDING"
    assert result.opportunity_quality.value is None
    assert result.entry.status == "PENDING"
    assert result.thesis_integrity.status == "PENDING"
    assert result.promotion_ready is False


def test_legacy_zero_financial_health_and_missing_theme_are_pending(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"AMZN","watchlist_status":"WATCHLIST","source_confluence_score":0,"financial_health_score":0,"themes":"","theme_momentum_score":0}]})
    result = build_promotion_readiness_from_runtime(tmp_path)[0]
    assert result.trusted_sources.status == "FAIL"
    assert result.financial_health.status == "PENDING"
    assert result.financial_health.value is None
    assert result.theme_strength.status == "PENDING"
    assert result.theme_strength.value is None


def test_measured_zero_theme_with_real_theme_is_fail_not_pending(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"CURRENT_CYCLE","rows":[{"underlying_symbol":"AMZN","watchlist_status":"WATCHLIST","source_confluence_score":5,"financial_health_score":80,"themes":"Cloud Computing","theme_momentum_score":0}]})
    result = build_promotion_readiness_from_runtime(tmp_path)[0]
    assert result.theme_strength.status == "FAIL"
    assert result.theme_strength.value == 0


def test_stale_report_masks_value_to_pending(tmp_path):
    _write(tmp_path / "watchlist_report.json", {"freshness_status":"STALE","rows":[{"underlying_symbol":"NVDA","watchlist_status":"WATCHLIST","source_confluence_score":7,"financial_health_score":90,"themes":"Semiconductors","theme_momentum_score":90}]})
    result = build_promotion_readiness_from_runtime(tmp_path)[0]
    assert result.trusted_sources.status == "PENDING"
    assert result.financial_health.status == "PENDING"
    assert result.theme_strength.status == "PENDING"


def test_thesis_v2_reviews_false_is_fail_not_pending(tmp_path):
    _write(
        tmp_path / "watchlist_report.json",
        {
            "freshness_status": "CURRENT_CYCLE",
            "rows": [{
                "underlying_symbol": "AMZN",
                "leveraged_symbol": "AMZU",
                "watchlist_status": "WATCHLIST",
                "source_confluence_score": 6,
                "financial_health_score": 80,
                "themes": "Cloud Computing",
                "theme_momentum_score": 75,
            }],
        },
    )
    _write(
        tmp_path / "thesis_monitor_v2_report.json",
        {
            "reviews": [{
                "underlying_symbol": "AMZN",
                "evidence_status": "AVAILABLE",
                "thesis_intact": False,
            }]
        },
    )

    result = build_promotion_readiness_from_runtime(tmp_path)[0]

    assert result.thesis_integrity.status == "FAIL"
    assert result.thesis_integrity.value is False


def test_thesis_v2_unavailable_evidence_is_pending_even_if_intact_true(tmp_path):
    _write(
        tmp_path / "watchlist_report.json",
        {
            "freshness_status": "CURRENT_CYCLE",
            "rows": [{
                "underlying_symbol": "NVDA",
                "leveraged_symbol": "NVDX",
                "watchlist_status": "WATCHLIST",
                "source_confluence_score": 6,
                "financial_health_score": 80,
                "themes": "Semiconductors",
                "theme_momentum_score": 75,
            }],
        },
    )
    _write(
        tmp_path / "thesis_monitor_v2_report.json",
        {
            "reviews": [{
                "underlying_symbol": "NVDA",
                "evidence_status": "UNAVAILABLE",
                "thesis_intact": True,
            }]
        },
    )

    result = build_promotion_readiness_from_runtime(tmp_path)[0]

    assert result.thesis_integrity.status == "PENDING"
    assert result.thesis_integrity.value is None
