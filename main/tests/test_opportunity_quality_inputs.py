import json
from pathlib import Path

import pytest

from swing_trade_bot.opportunity_quality_inputs import build_and_write_opportunity_quality_inputs, build_opportunity_quality_inputs


def _evidence(path: Path) -> None:
    (path / "swing_committee_runtime_evidence.json").write_text(json.dumps({"symbol": "TOP", "underlying_symbol": "TOP", "leveraged_symbol": "TOPX"}), encoding="utf-8")


def test_merges_authentic_component_evidence(tmp_path: Path) -> None:
    _evidence(tmp_path)
    (tmp_path / "watchlist_report.json").write_text(json.dumps({"rows": [{"underlying_symbol": "TOP", "financial_health_score": 82}]}), encoding="utf-8")
    (tmp_path / "market_intelligence.json").write_text(json.dumps({"rows": [{"symbol": "TOP", "market_intelligence_score": 75}]}), encoding="utf-8")
    payload = build_opportunity_quality_inputs(tmp_path)
    row = payload["rows"][0]
    assert row["fundamental_analysis_score"] == 82
    assert row["market_intelligence_score"] == 75
    assert row["momentum_score"] is None
    assert payload["component_provenance"]["fundamental_analysis_score"] == "results/watchlist_report.json"


def test_leveraged_symbol_alias_matches(tmp_path: Path) -> None:
    _evidence(tmp_path)
    (tmp_path / "momentum_scores.json").write_text(json.dumps({"rows": [{"symbol": "TOPX", "momentum_score": 71}]}), encoding="utf-8")
    assert build_opportunity_quality_inputs(tmp_path)["rows"][0]["momentum_score"] == 71


def test_missing_evidence_remains_null_for_engine_zero_rule(tmp_path: Path) -> None:
    _evidence(tmp_path)
    row = build_opportunity_quality_inputs(tmp_path)["rows"][0]
    assert row["conviction_score"] is None
    assert row["entry_score"] is None


def test_writes_paper_only_payload(tmp_path: Path) -> None:
    _evidence(tmp_path)
    output = build_and_write_opportunity_quality_inputs(tmp_path)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["paper_trade_mode"] is True
    assert payload["entry_score_display_only"] is True


def test_missing_runtime_evidence_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_opportunity_quality_inputs(tmp_path)


def test_live_mode_rejected(tmp_path: Path) -> None:
    _evidence(tmp_path)
    with pytest.raises(ValueError):
        build_opportunity_quality_inputs(tmp_path, paper_trade_mode=False)
