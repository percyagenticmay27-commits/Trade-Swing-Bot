import json
from pathlib import Path

import pytest

from swing_trade_bot.opportunity_quality_publisher import (
    build_and_write_opportunity_quality_evidence,
    build_opportunity_quality_evidence,
    validate_opportunity_quality_evidence,
)


def _source(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "opportunity_quality_report.json"
    path.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "system_mode": "QA",
                "entry_score_display_only": True,
                "entry_score_not_part_of_opportunity_quality": True,
                "missing_evidence_rule": "missing evidence = 0",
                "component_weights": {"fundamental_analysis_score": 0.2},
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_publishes_ranked_canonical_evidence(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        [
            {"symbol": "bbb", "opportunity_quality_score": 70, "opportunity_quality_level": "MEDIUM", "entry_score": 80, "entry_score_gate_passed": True},
            {"symbol": "aaa", "opportunity_quality_score": 85, "opportunity_quality_level": "HIGH", "entry_score": 40, "entry_score_gate_passed": False},
        ],
    )
    payload = build_opportunity_quality_evidence(source)
    assert payload["evidence_status"] == "AVAILABLE"
    assert payload["opportunity_quality_score"] == 85.0
    assert payload["top_opportunity"]["symbol"] == "AAA"
    assert [row["symbol"] for row in payload["ranked_opportunities"]] == ["AAA", "BBB"]
    assert payload["average_opportunity_quality_score"] == 77.5
    assert payload["entry_score_not_part_of_opportunity_quality"] is True
    assert validate_opportunity_quality_evidence(payload) == ()


def test_empty_report_is_partial_not_fabricated(tmp_path: Path) -> None:
    payload = build_opportunity_quality_evidence(_source(tmp_path, []))
    assert payload["evidence_status"] == "PARTIAL"
    assert payload["opportunity_quality_score"] is None
    assert payload["top_opportunity"] is None
    assert payload["opportunity_count"] == 0
    assert payload["warnings"]


def test_duplicate_symbols_are_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        [
            {"symbol": "AAA", "opportunity_quality_score": 70, "entry_score": 0},
            {"symbol": "aaa", "opportunity_quality_score": 80, "entry_score": 0},
        ],
    )
    with pytest.raises(ValueError, match="duplicate symbol"):
        build_opportunity_quality_evidence(source)


def test_unsafe_source_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, [])
    data = json.loads(source.read_text(encoding="utf-8"))
    data["paper_trade_mode"] = False
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="paper_trade_mode"):
        build_opportunity_quality_evidence(source)


def test_out_of_range_score_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, [{"symbol": "AAA", "opportunity_quality_score": 101, "entry_score": 0}])
    with pytest.raises(ValueError, match="between 0 and 100"):
        build_opportunity_quality_evidence(source)


def test_atomic_publication_writes_expected_file(tmp_path: Path) -> None:
    source = _source(tmp_path, [{"symbol": "AAA", "opportunity_quality_score": 75, "opportunity_quality_level": "MEDIUM", "entry_score": 65}])
    output = tmp_path / "results" / "opportunity_quality.json"
    written = build_and_write_opportunity_quality_evidence(source, output)
    assert written == output
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["opportunity_quality_score"] == 75.0
    assert not list(output.parent.glob("*.tmp"))


def test_missing_source_fails_safely(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_opportunity_quality_evidence(tmp_path / "missing.json")


def test_no_dividend_production_imports_exist() -> None:
    source = Path("src/swing_trade_bot/opportunity_quality_publisher.py").read_text(encoding="utf-8").lower()
    assert "trade-dividend-bot" not in source
    assert "dividend_bot" not in source
