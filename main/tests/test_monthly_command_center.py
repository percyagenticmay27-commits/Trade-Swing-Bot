from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.monthly_command_center import (
    OPTIONAL_FILES,
    REQUIRED_FILES,
    build_monthly_command_center,
    format_monthly_command_center_markdown,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare_required(root: Path) -> None:
    _write(
        root / "executive_dashboard.json",
        {
            "paper_trade_mode": True,
            "summary": {"active_positions": 2, "sgov_reserve_percent": 25.0},
            "risk_flags": ["Review concentration"],
            "suggested_actions": ["Review paper allocations."],
        },
    )
    _write(
        root / "weekly_stock_report.json",
        {"paper_trade_mode": True, "summary": {"symbols_reviewed": 4}},
    )
    _write(
        root / "stock_performance_report.json",
        {
            "paper_trade_mode": True,
            "executive_summary": {"average_portfolio_return": 3.5},
        },
    )
    _write(
        root / "portfolio_allocations.json",
        {
            "paper_trade_mode": True,
            "sgov_allocation": 25.0,
            "cash_allocation": 0.0,
            "allocations": [{"symbol": "SOXL"}, {"symbol": "TQQQ"}],
        },
    )


def test_required_file_contract_is_frozen() -> None:
    assert REQUIRED_FILES == (
        "executive_dashboard.json",
        "weekly_stock_report.json",
        "stock_performance_report.json",
        "portfolio_allocations.json",
    )


def test_build_writes_json_and_markdown(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    report = build_monthly_command_center(tmp_path)
    assert report.paper_trade_mode is True
    assert (tmp_path / "monthly_command_center.json").is_file()
    assert (tmp_path / "monthly_command_center.md").is_file()


def test_json_contains_authentic_source_summaries(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    build_monthly_command_center(tmp_path)
    payload = json.loads(
        (tmp_path / "monthly_command_center.json").read_text(encoding="utf-8")
    )
    assert payload["executive_summary"]["active_positions"] == 2
    assert payload["weekly_summary"]["symbols_reviewed"] == 4
    assert payload["performance_summary"]["average_portfolio_return"] == 3.5
    assert payload["allocation_summary"]["sgov_allocation"] == 25.0
    assert payload["allocation_summary"]["allocation_count"] == 2


def test_risk_flags_and_actions_are_copied_not_recalculated(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    report = build_monthly_command_center(tmp_path)
    assert report.risk_flags == ("Review concentration",)
    assert report.suggested_actions == ("Review paper allocations.",)


@pytest.mark.parametrize("missing_name", REQUIRED_FILES)
def test_missing_required_input_blocks_without_outputs(
    tmp_path: Path,
    missing_name: str,
) -> None:
    _prepare_required(tmp_path)
    (tmp_path / missing_name).unlink()
    with pytest.raises(FileNotFoundError, match=missing_name):
        build_monthly_command_center(tmp_path)
    assert not (tmp_path / "monthly_command_center.json").exists()
    assert not (tmp_path / "monthly_command_center.md").exists()


@pytest.mark.parametrize("required_name", REQUIRED_FILES)
def test_required_input_must_be_paper_only(
    tmp_path: Path,
    required_name: str,
) -> None:
    _prepare_required(tmp_path)
    payload = json.loads((tmp_path / required_name).read_text(encoding="utf-8"))
    payload["paper_trade_mode"] = False
    _write(tmp_path / required_name, payload)
    with pytest.raises(ValueError, match="paper_trade_mode=True"):
        build_monthly_command_center(tmp_path)


def test_missing_optional_inputs_create_warnings(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    report = build_monthly_command_center(tmp_path)
    assert len(report.warnings) == len(OPTIONAL_FILES)
    assert report.warnings[0].startswith("Missing optional output:")


def test_present_optional_input_removes_only_its_warning(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    (tmp_path / "strategy_recommendations.csv").write_text(
        "symbol,recommended_strategy\nSOXL,Strategy A\n",
        encoding="utf-8",
    )
    report = build_monthly_command_center(tmp_path)
    assert (
        "Missing optional output: strategy_recommendations.csv"
        not in report.warnings
    )
    assert len(report.warnings) == len(OPTIONAL_FILES) - 1


def test_malformed_required_json_blocks_without_outputs(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    (tmp_path / "weekly_stock_report.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        build_monthly_command_center(tmp_path)
    assert not (tmp_path / "monthly_command_center.json").exists()
    assert not (tmp_path / "monthly_command_center.md").exists()


def test_non_object_required_json_is_rejected(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    _write(tmp_path / "stock_performance_report.json", [])
    with pytest.raises(ValueError, match="root must be a JSON object"):
        build_monthly_command_center(tmp_path)


def test_separate_output_directory_is_supported(tmp_path: Path) -> None:
    results = tmp_path / "results"
    output = tmp_path / "published"
    _prepare_required(results)
    build_monthly_command_center(results, output_dir=output)
    assert (output / "monthly_command_center.json").is_file()
    assert (output / "monthly_command_center.md").is_file()


def test_live_mode_is_rejected_before_writing(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    with pytest.raises(ValueError, match="paper_trade_mode=True"):
        build_monthly_command_center(tmp_path, paper_trade_mode=False)
    assert not (tmp_path / "monthly_command_center.json").exists()


def test_markdown_is_deterministic(tmp_path: Path) -> None:
    _prepare_required(tmp_path)
    report = build_monthly_command_center(tmp_path)
    first = format_monthly_command_center_markdown(report)
    second = format_monthly_command_center_markdown(report)
    assert first == second
    assert "# Monthly Command Center" in first
    assert "Paper-only: true" in first
    assert "Advisory-only: true" in first
