from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from swing_trade_bot.enterprise_financial_health import (
    build_runtime_financial_health,
    parse_enterprise_financial_health,
    refresh_enterprise_financial_health_inputs,
)


FIELDS = (
    "revenue_growth",
    "eps_growth",
    "operating_cash_flow",
    "gross_margin_trend",
    "debt_health",
    "analyst_revisions",
    "sector_strength",
)


def _local(path: Path) -> Path:
    path.write_text(
        "underlying_symbol,revenue_growth,eps_growth,operating_cash_flow,gross_margin_trend,debt_health,analyst_revisions,sector_strength\n"
        "NBIS,82,78,74,80,72,76,79\n",
        encoding="utf-8",
    )
    return path


def _financial(*, timestamp: str = "2026-08-18T12:00:00Z", provenance: str = "AI_CIO_FINANCIAL_EVIDENCE") -> dict:
    return {
        "components": {field: 80 for field in FIELDS},
        "evidence_timestamp": timestamp,
        "provenance": provenance,
    }


def test_complete_current_provenanced_enterprise_health_is_accepted() -> None:
    row = parse_enterprise_financial_health(
        "NVDA",
        _financial(),
        as_of=date(2026, 8, 18),
    )
    assert row.underlying_symbol == "NVDA"
    assert row.health.score == 80.0
    assert row.provenance == "AI_CIO_FINANCIAL_EVIDENCE"
    assert row.freshness_status == "CURRENT"


def test_missing_component_fails_closed() -> None:
    payload = _financial()
    del payload["components"]["debt_health"]
    try:
        parse_enterprise_financial_health("NVDA", payload, as_of=date(2026, 8, 18))
    except ValueError as exc:
        assert "missing required financial-health component debt_health" in str(exc)
    else:
        raise AssertionError("incomplete evidence must fail")


def test_missing_provenance_fails_closed() -> None:
    payload = _financial(provenance="")
    try:
        parse_enterprise_financial_health("NVDA", payload, as_of=date(2026, 8, 18))
    except ValueError as exc:
        assert "provenance is required" in str(exc)
    else:
        raise AssertionError("unprovenanced evidence must fail")


def test_stale_evidence_fails_closed() -> None:
    try:
        parse_enterprise_financial_health(
            "NVDA",
            _financial(timestamp="2026-07-01T12:00:00Z"),
            as_of=date(2026, 8, 18),
        )
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale evidence must fail")


def test_local_swing_health_remains_authority_for_existing_symbol(tmp_path: Path) -> None:
    bucket = {
        "candidates": [
            {"underlying_symbol": "NBIS", "financial_health": _financial()}
        ]
    }
    rows, audit, warnings = build_runtime_financial_health(
        local_path=_local(tmp_path / "health.csv"),
        bucket=bucket,
        as_of=date(2026, 8, 18),
    )
    assert round(rows["NBIS"].score, 2) != 80.0
    assert audit == [
        {"underlying_symbol": "NBIS", "status": "LOCAL_SWING_AUTHORITY_RETAINED", "accepted": False}
    ]
    assert warnings == []


def test_dynamic_enterprise_candidate_receives_health_without_editing_example_csv(tmp_path: Path) -> None:
    bucket = {
        "candidates": [
            {"underlying_symbol": "NVDA", "financial_health": _financial()}
        ]
    }
    rows, audit, warnings = build_runtime_financial_health(
        local_path=_local(tmp_path / "health.csv"),
        bucket=bucket,
        as_of=date(2026, 8, 18),
    )
    assert set(rows) == {"NBIS", "NVDA"}
    assert rows["NVDA"].score == 80.0
    assert audit[0]["accepted"] is True
    assert warnings == []


def test_missing_dynamic_health_stays_missing_and_visible(tmp_path: Path) -> None:
    bucket = {"candidates": [{"underlying_symbol": "NVDA"}]}
    rows, audit, warnings = build_runtime_financial_health(
        local_path=_local(tmp_path / "health.csv"),
        bucket=bucket,
        as_of=date(2026, 8, 18),
    )
    assert "NVDA" not in rows
    assert audit[0]["status"] == "MISSING_ENTERPRISE_FINANCIAL_HEALTH"
    assert "MISSING_REQUIRED_FINANCIAL_HEALTH:NVDA" in warnings


def test_refresh_materializes_runtime_csv_and_audit_atomically(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    (tmp_path / "results").mkdir()
    _local(tmp_path / "examples" / "financial_health.csv")
    bucket = tmp_path / "bucket.json"
    bucket.write_text(
        json.dumps({"candidates": [{"underlying_symbol": "NVDA", "financial_health": _financial()}]}),
        encoding="utf-8",
    )
    report = refresh_enterprise_financial_health_inputs(
        swing_root=tmp_path,
        bucket_path=bucket,
        as_of=date(2026, 8, 18),
    )
    assert report["enterprise_financial_health_accepted_count"] == 1
    runtime = tmp_path / "results" / "discovery_financial_health_runtime.csv"
    with runtime.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["underlying_symbol"] for row in rows} == {"NBIS", "NVDA"}
    audit = json.loads((tmp_path / "results" / "enterprise_financial_health_intake.json").read_text())
    assert audit["broker_execution_allowed"] is False
    assert audit["order_placement_allowed"] is False


def test_no_fabricated_passing_values_when_enterprise_health_missing(tmp_path: Path) -> None:
    rows, _, _ = build_runtime_financial_health(
        local_path=_local(tmp_path / "health.csv"),
        bucket={"candidates": [{"underlying_symbol": "PLTR"}]},
        as_of=date(2026, 8, 18),
    )
    assert "PLTR" not in rows
