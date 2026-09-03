import json
from pathlib import Path

from swing_trade_bot.swing_daily_cycle import _publish_static_artifacts
from swing_trade_bot.swing_strategy_service_registration import (
    build_strategy_service_registration,
    load_plugin_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = ROOT / "configs" / "frozen_strategy_assignments.json"
DAILY_CYCLE = ROOT / "configs" / "swing_daily_cycle.json"
MANIFEST = ROOT / "configs" / "swing_cio_plugin_manifest.json"

OLD_ARTIFACT_IDS = {
    "daily_cycle_status",
    "executive_dashboard",
    "manual_entry_strategy_form_contract",
    "market_data_status",
    "monthly_command_center",
    "opportunity_quality",
    "portfolio_allocations",
    "position_lifecycle",
    "stock_performance",
    "strategy_kpis",
    "swing_decision_journal_report",
    "swing_strategy_alerts_report",
    "swing_trade_analytics_report",
    "watchlist",
    "weekly_stock_report",
}


def _source_payload() -> dict:
    return json.loads(ASSIGNMENTS.read_text(encoding="utf-8"))


def test_daily_cycle_maps_enterprise_assignments_to_authoritative_registry() -> None:
    cycle = json.loads(DAILY_CYCLE.read_text(encoding="utf-8"))
    assert cycle["static_artifacts"]["enterprise_strategy_assignments.json"] == (
        "configs/frozen_strategy_assignments.json"
    )
    assert cycle["paper_trade_mode"] is True
    assert cycle["broker_execution_allowed"] is False
    assert cycle["capital_movement_allowed"] is False
    assert cycle["automatic_activation_allowed"] is False


def test_static_publication_preserves_assignment_payload_exactly_and_has_no_side_effects(tmp_path) -> None:
    source = _source_payload()
    root = tmp_path / "repo"
    output = root / "results"
    config_dir = root / "configs"
    config_dir.mkdir(parents=True)
    source_path = config_dir / "frozen_strategy_assignments.json"
    source_path.write_text(json.dumps(source, indent=2), encoding="utf-8")

    allocation = output / "portfolio_allocations.json"
    positions = output / "paper_portfolio_positions.json"
    confidence = output / "confidence_report.json"
    output.mkdir(parents=True)
    allocation.write_text('{"sentinel":"allocation"}\n', encoding="utf-8")
    positions.write_text('{"sentinel":"positions"}\n', encoding="utf-8")
    confidence.write_text('{"sentinel":"confidence"}\n', encoding="utf-8")
    before = {
        allocation: allocation.read_text(encoding="utf-8"),
        positions: positions.read_text(encoding="utf-8"),
        confidence: confidence.read_text(encoding="utf-8"),
    }

    errors: list[str] = []
    published = _publish_static_artifacts(
        root,
        output,
        {"enterprise_strategy_assignments.json": "configs/frozen_strategy_assignments.json"},
        errors,
    )

    target = output / "enterprise_strategy_assignments.json"
    assert errors == []
    assert str(target) in published
    assert json.loads(target.read_text(encoding="utf-8")) == source
    for path, original in before.items():
        assert path.read_text(encoding="utf-8") == original


def test_service_registration_exposes_exactly_one_strategy_assignments_artifact() -> None:
    manifest = load_plugin_manifest(MANIFEST)
    registration = build_strategy_service_registration(manifest)
    artifacts = registration["dashboard_artifacts"]
    matches = [
        item
        for item in artifacts
        if item["artifact_id"] == "strategy_assignments"
        or item["artifact_type"] == "strategy_assignments"
    ]
    assert registration["capabilities"].count("strategy_assignments") == 1
    assert len(matches) == 1
    assert matches[0] == {
        "artifact_id": "strategy_assignments",
        "artifact_type": "strategy_assignments",
        "path": "results/enterprise_strategy_assignments.json",
        "format": "json",
        "scope": "STRATEGY",
        "authoritative": True,
        "required": False,
    }
    assert OLD_ARTIFACT_IDS == {
        item["artifact_id"] for item in artifacts if item["artifact_id"] != "strategy_assignments"
    }
    assert len(artifacts) == 16


def test_authoritative_registry_preserves_nine_primary_shadow_stacks_and_max_four_shadows() -> None:
    payload = _source_payload()
    symbols = payload["symbols"]
    assert payload["paper_trade_mode"] is True
    assert len(symbols) == 9
    assert {row["symbol"] for row in symbols} == {
        "SOXL",
        "TQQQ",
        "NFLU",
        "NVDX",
        "PLTU",
        "AMZU",
        "GGLL",
        "AMDL",
        "AVL",
    }
    strategy_ids = {row["strategy_id"] for row in payload["strategies"]}
    for row in symbols:
        assert row["primary_strategy_id"] in strategy_ids
        assert len(row["shadow_strategy_ids"]) <= 4
        assert all(strategy_id in strategy_ids for strategy_id in row["shadow_strategy_ids"])


def test_published_shape_preserves_primary_and_shadow_information(tmp_path) -> None:
    source = _source_payload()
    root = tmp_path / "repo"
    (root / "configs").mkdir(parents=True)
    (root / "configs" / "frozen_strategy_assignments.json").write_text(
        json.dumps(source), encoding="utf-8"
    )
    errors: list[str] = []
    _publish_static_artifacts(
        root,
        root / "results",
        {"enterprise_strategy_assignments.json": "configs/frozen_strategy_assignments.json"},
        errors,
    )
    published = json.loads(
        (root / "results" / "enterprise_strategy_assignments.json").read_text(encoding="utf-8")
    )
    assert errors == []
    assert published["symbols"] == source["symbols"]
    assert published["strategies"] == source["strategies"]
