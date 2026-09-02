import json
from pathlib import Path

import pytest

from swing_trade_bot.opportunity_quality_inputs import build_and_write_opportunity_quality_inputs, build_opportunity_quality_inputs


def _watchlist(path: Path) -> None:
    (path / "watchlist_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "underlying_symbol": "TOP",
                        "leveraged_symbol": "TOPX",
                        "capacity_status": "ACTIVE",
                        "watchlist_status": "WATCHLIST",
                        "watchlist_rank": 1,
                        "composite_score": 80,
                        "financial_health_score": 82,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_merges_authentic_component_evidence(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    (tmp_path / "market_intelligence.json").write_text(json.dumps({"rows": [{"symbol": "TOP", "market_intelligence_score": 75}]}), encoding="utf-8")
    payload = build_opportunity_quality_inputs(tmp_path)
    row = payload["rows"][0]
    assert row["fundamental_analysis_score"] == 82
    assert row["market_intelligence_score"] == 75
    assert row["momentum_score"] is None
    assert payload["component_provenance"]["fundamental_analysis_score"] == "results/watchlist_report.json"
    assert payload["component_provenance_by_symbol"]["TOP"]["market_intelligence_score"] == "results/market_intelligence.json"
    assert payload["selection_source"] == "results/watchlist_report.json"


def test_all_active_ranked_candidates_reach_opportunity_quality_inputs(tmp_path: Path) -> None:
    (tmp_path / "watchlist_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "underlying_symbol": "NVDA",
                        "leveraged_symbol": "NVDX",
                        "capacity_status": "ACTIVE",
                        "watchlist_status": "WATCHLIST",
                        "watchlist_rank": 1,
                        "composite_score": 20.8,
                        "financial_health_score": 70,
                    },
                    {
                        "underlying_symbol": "AMZN",
                        "leveraged_symbol": "AMZU",
                        "capacity_status": "ACTIVE",
                        "watchlist_status": "WATCHLIST",
                        "watchlist_rank": 2,
                        "composite_score": 9.38,
                        "financial_health_score": 60,
                    },
                    {
                        "underlying_symbol": "NFLX",
                        "leveraged_symbol": "NFLU",
                        "capacity_status": "ACTIVE",
                        "watchlist_status": "WATCHLIST",
                        "watchlist_rank": 3,
                        "composite_score": 9.38,
                        "financial_health_score": 0,
                    },
                    {
                        "underlying_symbol": "REMOVED",
                        "leveraged_symbol": "REMOVEDX",
                        "capacity_status": "INACTIVE",
                        "watchlist_status": "WATCHLIST",
                        "watchlist_rank": 4,
                        "composite_score": 99,
                        "financial_health_score": 99,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "market_intelligence.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"symbol": "NVDX", "market_intelligence_score": 80},
                    {"symbol": "AMZN", "market_intelligence_score": 65},
                    {"symbol": "NFLU", "market_intelligence_score": 55},
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_opportunity_quality_inputs(tmp_path)

    assert [row["symbol"] for row in payload["rows"]] == ["NVDA", "AMZN", "NFLX"]
    assert payload["candidate_coverage"] == "all active ranked watchlist candidates"
    assert payload["selected_underlying_symbol"] == "NVDA"
    assert payload["selected_leveraged_symbol"] == "NVDX"
    by_symbol = {row["symbol"]: row for row in payload["rows"]}
    assert by_symbol["NVDA"]["market_intelligence_score"] == 80
    assert by_symbol["AMZN"]["market_intelligence_score"] == 65
    assert by_symbol["NFLX"]["market_intelligence_score"] == 55
    assert by_symbol["NFLX"]["fundamental_analysis_score"] == 0
    assert payload["component_provenance_by_symbol"]["NFLX"]["market_intelligence_score"] == "results/market_intelligence.json"


def test_mapped_underlying_evidence_populates_frozen_oq_components(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    (tmp_path / "mapped_underlying_fundamental_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "preferred_vehicle": "TOPX", "fundamental_analysis_score": 83.92}]}),
        encoding="utf-8",
    )
    (tmp_path / "mapped_underlying_intelligence_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "market_intelligence_score": 56.67, "conviction_score": 45.83}]}),
        encoding="utf-8",
    )
    (tmp_path / "mapped_underlying_quantitative_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "momentum_score": 51.31, "technical_analysis_score": 100.0}]}),
        encoding="utf-8",
    )
    (tmp_path / "mapped_underlying_market_regime_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "market_regime_support_score": 65.0}]}),
        encoding="utf-8",
    )
    (tmp_path / "mapped_underlying_portfolio_risk_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "portfolio_risk_adjustment_score": 100.0}]}),
        encoding="utf-8",
    )

    payload = build_opportunity_quality_inputs(tmp_path)
    row = payload["rows"][0]

    assert row["fundamental_analysis_score"] == 83.92
    assert row["market_intelligence_score"] == 56.67
    assert row["conviction_score"] == 45.83
    assert row["momentum_score"] == 51.31
    assert row["technical_analysis_score"] == 100.0
    assert row["market_regime_support_score"] == 65.0
    assert row["portfolio_risk_adjustment_score"] == 100.0
    assert payload["component_provenance_by_symbol"]["TOP"]["fundamental_analysis_score"] == "results/mapped_underlying_fundamental_evidence.json"
    assert payload["component_provenance_by_symbol"]["TOP"]["technical_analysis_score"] == "results/mapped_underlying_quantitative_evidence.json"
    assert "results/mapped_underlying_intelligence_evidence.json" in payload["source_artifacts"]


def test_dedicated_evidence_precedes_mapped_and_mapped_precedes_watchlist_fallback(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    (tmp_path / "fundamental_analysis.json").write_text(
        json.dumps({"rows": [{"symbol": "TOP", "fundamental_analysis_score": 91.0}]}),
        encoding="utf-8",
    )
    (tmp_path / "mapped_underlying_fundamental_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "fundamental_analysis_score": 83.92}]}),
        encoding="utf-8",
    )
    (tmp_path / "mapped_underlying_quantitative_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "momentum_score": 51.31}]}),
        encoding="utf-8",
    )
    (tmp_path / "momentum_scores.json").write_text(
        json.dumps({"rows": [{"symbol": "TOP", "momentum_score": 72.0}]}),
        encoding="utf-8",
    )

    payload = build_opportunity_quality_inputs(tmp_path)
    row = payload["rows"][0]
    provenance = payload["component_provenance_by_symbol"]["TOP"]

    assert row["fundamental_analysis_score"] == 91.0
    assert provenance["fundamental_analysis_score"] == "results/fundamental_analysis.json"
    assert row["momentum_score"] == 72.0
    assert provenance["momentum_score"] == "results/momentum_scores.json"


def test_mapped_fundamental_overrides_zero_watchlist_placeholder(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    payload = json.loads((tmp_path / "watchlist_report.json").read_text(encoding="utf-8"))
    payload["rows"][0]["financial_health_score"] = 0
    (tmp_path / "watchlist_report.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "mapped_underlying_fundamental_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "TOP", "fundamental_analysis_score": 83.92}]}),
        encoding="utf-8",
    )

    result = build_opportunity_quality_inputs(tmp_path)
    assert result["rows"][0]["fundamental_analysis_score"] == 83.92
    assert result["component_provenance_by_symbol"]["TOP"]["fundamental_analysis_score"] == "results/mapped_underlying_fundamental_evidence.json"


def test_leveraged_symbol_alias_matches(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    (tmp_path / "momentum_scores.json").write_text(json.dumps({"rows": [{"symbol": "TOPX", "momentum_score": 71}]}), encoding="utf-8")
    assert build_opportunity_quality_inputs(tmp_path)["rows"][0]["momentum_score"] == 71


def test_missing_evidence_remains_null_for_engine_zero_rule(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    row = build_opportunity_quality_inputs(tmp_path)["rows"][0]
    assert row["conviction_score"] is None
    assert row["entry_score"] is None
    assert row["thesis_intact"] is None


def test_writes_paper_only_payload(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    output = build_and_write_opportunity_quality_inputs(tmp_path)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["paper_trade_mode"] is True
    assert payload["entry_score_display_only"] is True


def test_missing_watchlist_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_opportunity_quality_inputs(tmp_path)


def test_stale_committee_evidence_cannot_override_current_watchlist_selection(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    (tmp_path / "swing_committee_runtime_evidence.json").write_text(
        json.dumps({"symbol": "OLD", "underlying_symbol": "OLD", "leveraged_symbol": "OLDX"}),
        encoding="utf-8",
    )
    payload = build_opportunity_quality_inputs(tmp_path)
    assert payload["rows"][0]["symbol"] == "TOP"
    assert "results/swing_committee_runtime_evidence.json" not in payload["source_artifacts"]


def test_high_priority_rank_wins_over_standard_rank(tmp_path: Path) -> None:
    (tmp_path / "watchlist_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"underlying_symbol": "STANDARD", "capacity_status": "ACTIVE", "watchlist_status": "WATCHLIST", "watchlist_rank": 1, "composite_score": 99},
                    {"underlying_symbol": "PRIORITY", "capacity_status": "ACTIVE", "watchlist_status": "WATCHLIST", "high_priority_rank": 1, "composite_score": 80},
                ]
            }
        ),
        encoding="utf-8",
    )
    payload = build_opportunity_quality_inputs(tmp_path)
    assert payload["rows"][0]["symbol"] == "PRIORITY"
    assert [row["symbol"] for row in payload["rows"]] == ["PRIORITY", "STANDARD"]


def test_live_mode_rejected(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    with pytest.raises(ValueError):
        build_opportunity_quality_inputs(tmp_path, paper_trade_mode=False)
