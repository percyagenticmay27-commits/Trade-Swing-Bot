import json
from pathlib import Path

import pytest

from swing_trade_bot.thesis_monitor_v2 import build_and_write_thesis_monitor_v2, build_thesis_monitor_v2


def _write(path: Path, name: str, payload: object) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def _base(tmp_path: Path, *, score: float = 80.0) -> Path:
    results = tmp_path / "results"
    _write(results, "watchlist_report.json", {"rows": [{"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "capacity_status": "ACTIVE", "watchlist_status": "WATCHLIST"}]})
    components = {
        "symbol": "NVDA",
        "fundamental_analysis_score": score,
        "market_intelligence_score": score,
        "conviction_score": score,
        "momentum_score": score,
        "technical_analysis_score": score,
        "market_regime_support_score": score,
        "portfolio_risk_adjustment_score": score,
        "entry_score": 0,
    }
    provenance = {key: f"results/{key}.json" for key in components if key.endswith("_score")}
    _write(results, "opportunity_quality_inputs.json", {"component_provenance_by_symbol": {"NVDA": provenance}, "rows": [components]})
    _write(results, "opportunity_quality_report.json", {"rows": [{"symbol": "NVDA", "opportunity_quality_score": score}]})
    configs = tmp_path / "configs"
    _write(configs, "frozen_strategy_assignments.json", {"strategies": [{"strategy_id": "NVDX_NVDA_STRATEGY_F_1H_PRIMARY", "signal_symbol": "NVDA", "vehicle_symbol": "NVDX", "assignment_mode": "DIRECT", "enabled": True}]})
    return results


def test_dynamic_current_universe_and_primary_mapping(tmp_path: Path) -> None:
    results = _base(tmp_path)
    payload = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")
    review = payload["reviews"][0]
    assert review["underlying_symbol"] == "NVDA"
    assert review["vehicle_symbol"] == "NVDX"
    assert review["primary_strategy_id"] == "NVDX_NVDA_STRATEGY_F_1H_PRIMARY"
    assert payload["dynamic_universe"] is True
    assert payload["handwritten_symbol_theses_used"] is False


def test_entry_score_does_not_affect_thesis_health(tmp_path: Path) -> None:
    results = _base(tmp_path, score=80)
    first = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")
    inputs = json.loads((results / "opportunity_quality_inputs.json").read_text(encoding="utf-8"))
    inputs["rows"][0]["entry_score"] = 100
    (results / "opportunity_quality_inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    second = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")
    assert first["reviews"][0]["thesis_health_score"] == second["reviews"][0]["thesis_health_score"]
    assert second["entry_score_used_in_thesis_health"] is False


def test_insufficient_evidence_is_pending_not_false(tmp_path: Path) -> None:
    results = _base(tmp_path)
    inputs = json.loads((results / "opportunity_quality_inputs.json").read_text(encoding="utf-8"))
    row = inputs["rows"][0]
    for key in (
        "conviction_score", "momentum_score", "technical_analysis_score",
        "market_regime_support_score", "portfolio_risk_adjustment_score",
    ):
        row[key] = None
    (results / "opportunity_quality_inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    review = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")["reviews"][0]
    assert review["thesis_state"] == "unknown"
    assert review["thesis_intact"] is None
    assert review["evidence_status"] == "EVIDENCE_PENDING"


def test_three_weak_components_force_weakening(tmp_path: Path) -> None:
    results = _base(tmp_path, score=80)
    inputs = json.loads((results / "opportunity_quality_inputs.json").read_text(encoding="utf-8"))
    row = inputs["rows"][0]
    row["momentum_score"] = 40
    row["technical_analysis_score"] = 40
    row["market_regime_support_score"] = 40
    (results / "opportunity_quality_inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    review = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")["reviews"][0]
    assert review["weak_evidence_count"] == 3
    assert review["thesis_state"] == "weakening"
    assert review["thesis_intact"] is False


def test_previous_report_creates_dynamic_change_metrics(tmp_path: Path) -> None:
    results = _base(tmp_path, score=80)
    _write(results, "thesis_monitor_v2_report.json", {"reviews": [{"underlying_symbol": "NVDA", "thesis_health_score": 92, "opportunity_quality_score": 90}]})
    review = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")["reviews"][0]
    assert review["thesis_health_change"] == -12
    assert review["opportunity_quality_change"] == -10
    assert review["thesis_state"] == "weakening"


def test_inactive_watchlist_symbol_is_not_reviewed(tmp_path: Path) -> None:
    results = _base(tmp_path)
    watchlist = json.loads((results / "watchlist_report.json").read_text(encoding="utf-8"))
    watchlist["rows"].append({"underlying_symbol": "OLD", "capacity_status": "INACTIVE", "watchlist_status": "REMOVED"})
    (results / "watchlist_report.json").write_text(json.dumps(watchlist), encoding="utf-8")
    payload = build_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")
    assert [row["underlying_symbol"] for row in payload["reviews"]] == ["NVDA"]


def test_outputs_are_paper_only_and_do_not_overwrite_legacy(tmp_path: Path) -> None:
    results = _base(tmp_path)
    legacy = results / "thesis_monitor_report.json"
    legacy.write_text('{"legacy": true}', encoding="utf-8")
    payload = build_and_write_thesis_monitor_v2(results_dir=results, assignments_path=tmp_path / "configs" / "frozen_strategy_assignments.json")
    assert (results / "thesis_monitor_v2_report.json").is_file()
    assert (results / "thesis_monitor_v2_report.md").is_file()
    assert json.loads(legacy.read_text(encoding="utf-8")) == {"legacy": True}
    assert payload["paper_trade_mode"] is True
    assert payload["broker_execution_enabled"] is False
    assert payload["capital_movement_enabled"] is False


def test_live_mode_rejected(tmp_path: Path) -> None:
    results = _base(tmp_path)
    with pytest.raises(ValueError):
        build_thesis_monitor_v2(results_dir=results, paper_trade_mode=False)
