import csv
import json
from datetime import date
from pathlib import Path

import pytest

from swing_trade_bot.weekly_stock_report import build_and_write_weekly_stock_report, build_weekly_stock_report


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _required(tmp_path: Path) -> tuple[Path, Path]:
    performance = tmp_path / "stock_performance_report.json"
    allocations = tmp_path / "portfolio_allocations.json"
    performance.write_text(json.dumps({"rows": [
        {"symbol": "SOXL", "weekly_return": 3, "total_return": 19, "active_strategy": "Strategy A", "recommended_strategy": "Strategy B"},
        {"symbol": "TQQQ", "weekly_return": -4, "total_return": -16},
    ]}), encoding="utf-8")
    allocations.write_text(json.dumps({"sgov_allocation": 30, "allocations": [{"symbol": "SOXL", "allocation_percent": 15}]}), encoding="utf-8")
    return performance, allocations


def test_builds_winner_target_loss_and_strategy_signals(tmp_path: Path) -> None:
    report = build_weekly_stock_report(*_required(tmp_path), as_of=date(2026, 7, 30))
    names = {signal.signal for signal in report.signals}
    assert report.paper_trade_mode is True
    assert report.summary["weekly_winners"] == 1
    assert report.summary["weekly_losers"] == 1
    assert "APPROACHING_20_TARGET" in names
    assert "LOSS_PROTECTION_WARNING" in names
    assert report.summary["strategy_changes"] == 1
    assert report.sgov_allocation == 30
    assert len(report.warnings) == 5


def test_optional_reports_add_changes_and_earnings(tmp_path: Path) -> None:
    required = _required(tmp_path)
    confidence = tmp_path / "confidence.json"
    watchlist = tmp_path / "watchlist.json"
    earnings = tmp_path / "earnings.json"
    strategies = tmp_path / "strategies.csv"
    manager = tmp_path / "manager.csv"
    confidence.write_text(json.dumps({"rows": [{"symbol": "SOXL", "change": "UPGRADE"}]}), encoding="utf-8")
    watchlist.write_text(json.dumps({"rows": [{"symbol": "SOXL", "change": "PROMOTED"}]}), encoding="utf-8")
    earnings.write_text(json.dumps({"rows": [{"symbol": "SOXL", "earnings_date": "2026-08-03"}]}), encoding="utf-8")
    _csv(strategies, [{"symbol": "SOXL", "active_strategy": "Strategy A", "recommended_strategy": "Strategy B"}])
    _csv(manager, [{"symbol": "SOXL", "action": "REVIEW", "current_allocation": 15}])
    report = build_weekly_stock_report(
        *required,
        portfolio_manager_report_path=manager,
        confidence_report_path=confidence,
        strategy_recommendations_path=strategies,
        watchlist_report_path=watchlist,
        earnings_report_path=earnings,
        as_of=date(2026, 7, 30),
    )
    assert report.confidence_upgrades == ("SOXL",)
    assert report.watchlist_promotions == ("SOXL",)
    assert report.earnings_risks == ("SOXL",)
    assert "EARNINGS_EXIT_REVIEW" in {signal.signal for signal in report.signals}
    assert report.warnings == ()


def test_writes_all_three_outputs(tmp_path: Path) -> None:
    report = build_and_write_weekly_stock_report(*_required(tmp_path), tmp_path / "out", as_of=date(2026, 7, 30))
    assert report.rows
    assert (tmp_path / "out/weekly_stock_report.csv").is_file()
    assert (tmp_path / "out/weekly_stock_report.json").is_file()
    assert "Earnings Risk Next Week" in (tmp_path / "out/weekly_stock_report.md").read_text()


def test_missing_required_input_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_weekly_stock_report(tmp_path / "missing.json", tmp_path / "also_missing.json")


def test_live_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_weekly_stock_report(*_required(tmp_path), paper_trade_mode=False)
