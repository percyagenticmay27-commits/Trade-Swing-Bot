import json
from pathlib import Path

import pytest

from swing_trade_bot.opportunity_quality_runtime_report import (
    build_inputs_from_evidence,
    collect_runtime_evidence,
    generate_runtime_opportunity_quality_report,
)


def test_collects_and_merges_symbol_evidence(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "portfolio_allocations.json").write_text(
        json.dumps({"allocations": [{"symbol": "AAA", "conviction_score": 80, "entry_score": 75}]}),
        encoding="utf-8",
    )
    (results / "momentum_scores.json").write_text(
        json.dumps({"rows": [{"symbol": "AAA", "momentum_score": 70}]}),
        encoding="utf-8",
    )

    evidence = collect_runtime_evidence(results_dir=results)

    assert evidence["AAA"]["conviction_score"] == 80.0
    assert evidence["AAA"]["momentum_score"] == 70.0
    assert evidence["AAA"]["entry_score"] == 75.0


def test_mapped_underlying_evidence_precedes_stale_generic_snapshots(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "mapped_underlying_fundamental_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "AAA", "fundamental_analysis_score": 93.0}]}),
        encoding="utf-8",
    )
    (results / "mapped_underlying_quantitative_evidence.json").write_text(
        json.dumps({"rows": [{"underlying_symbol": "AAA", "momentum_score": 77.0, "technical_analysis_score": 81.0}]}),
        encoding="utf-8",
    )
    (results / "opportunity_quality_inputs.json").write_text(
        json.dumps({"rows": [{"symbol": "AAA", "fundamental_analysis_score": 0.0, "momentum_score": 0.0, "technical_analysis_score": 0.0}]}),
        encoding="utf-8",
    )

    evidence = collect_runtime_evidence(results_dir=results)

    assert evidence["AAA"]["fundamental_analysis_score"] == 93.0
    assert evidence["AAA"]["momentum_score"] == 77.0
    assert evidence["AAA"]["technical_analysis_score"] == 81.0


def test_build_inputs_preserves_missing_evidence_as_none() -> None:
    inputs = build_inputs_from_evidence({"AAA": {"symbol": "AAA", "conviction_score": 80.0}})

    assert len(inputs) == 1
    assert inputs[0].symbol == "AAA"
    assert inputs[0].conviction_score == 80.0
    assert inputs[0].fundamental_analysis_score is None


def test_generates_atomic_runtime_report_set(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    source = results / "opportunity_quality_inputs.json"
    source.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "symbol": "AAA",
                        "fundamental_analysis_score": 80,
                        "market_intelligence_score": 70,
                        "conviction_score": 90,
                        "momentum_score": 75,
                        "technical_analysis_score": 65,
                        "market_regime_support_score": 60,
                        "portfolio_risk_adjustment_score": 55,
                        "entry_score": 72,
                    },
                    {"symbol": "BBB", "conviction_score": 50},
                ]
            }
        ),
        encoding="utf-8",
    )

    report = generate_runtime_opportunity_quality_report(results_dir=results)

    assert len(report.rows) == 2
    assert (results / "opportunity_quality_report.json").exists()
    assert (results / "opportunity_quality_report.csv").exists()
    assert (results / "opportunity_quality_report.md").exists()

    payload = json.loads((results / "opportunity_quality_report.json").read_text(encoding="utf-8"))
    assert payload["paper_trade_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["entry_score_not_part_of_opportunity_quality"] is True
    assert payload["missing_evidence_rule"] == "missing evidence = 0"
    assert payload["rows"][0]["rank"] == 1
    assert payload["rows"][0]["symbol"] == "AAA"


def test_fails_safely_when_no_symbol_evidence_exists(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()

    with pytest.raises(FileNotFoundError, match="No symbol-level"):
        generate_runtime_opportunity_quality_report(results_dir=results)

    assert not (results / "opportunity_quality_report.json").exists()


def test_rejects_out_of_range_scores(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    source = results / "opportunity_quality_inputs.json"
    source.write_text(json.dumps([{"symbol": "AAA", "conviction_score": 101}]), encoding="utf-8")

    with pytest.raises(ValueError, match="between 0 and 100"):
        generate_runtime_opportunity_quality_report(results_dir=results)


def test_no_live_or_broker_execution_surface() -> None:
    import swing_trade_bot.opportunity_quality_runtime_report as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "robinhood" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
