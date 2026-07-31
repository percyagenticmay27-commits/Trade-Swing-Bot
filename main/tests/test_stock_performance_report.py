import csv
import json
from pathlib import Path

import pytest

from swing_trade_bot.stock_performance_report import (
    build_and_write_stock_performance_report,
    build_stock_performance_report,
)


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    comparison = tmp_path / "strategy_comparison.json"
    recommendations = tmp_path / "strategy_recommendations.csv"
    allocations = tmp_path / "portfolio_allocations.json"
    manager = tmp_path / "portfolio_manager_report.csv"
    comparison.write_text(json.dumps({"rows": [{
        "symbol": "SOXL", "strategy_a_return": 8, "strategy_b_return": 12,
        "strategy_a_win_rate": 55, "strategy_b_win_rate": 60,
        "strategy_a_trades": 20, "strategy_b_trades": 22,
        "strategy_a_net_profit": 800, "strategy_b_net_profit": 1200,
        "strategy_a_max_drawdown": 9, "strategy_b_max_drawdown": 7,
    }]}), encoding="utf-8")
    _csv(recommendations, [{"symbol": "SOXL", "active_strategy": "Strategy A", "recommended_strategy": "Strategy B", "months_outperforming": 3}])
    allocations.write_text(json.dumps({"allocations": [{"symbol": "SOXL", "allocation_percent": 15}]}), encoding="utf-8")
    _csv(manager, [{"symbol": "SOXL", "current_allocation": 10, "confidence": "HIGH", "action": "HOLD"}])
    return comparison, recommendations, allocations, manager


def test_builds_strategy_comparison_and_switch_signal(tmp_path: Path) -> None:
    report = build_stock_performance_report(*_inputs(tmp_path))
    row = report.rows[0]
    assert report.paper_trade_mode is True
    assert report.symbols_reviewed == 1
    assert report.strategy_switch_eligible == 1
    assert row.better_profit_strategy == "STRATEGY B"
    assert row.better_drawdown_strategy == "STRATEGY B"


def test_writes_csv_json_and_markdown(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    report = build_and_write_stock_performance_report(*inputs, tmp_path / "out")
    assert report.rows
    assert (tmp_path / "out/stock_performance_report.csv").is_file()
    assert json.loads((tmp_path / "out/stock_performance_report.json").read_text())["paper_trade_mode"] is True
    assert "Suggested Actions" in (tmp_path / "out/stock_performance_report.md").read_text()


def test_missing_required_input_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_stock_performance_report(*(tmp_path / name for name in ("a", "b", "c", "d")))


def test_live_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_stock_performance_report(*_inputs(tmp_path), paper_trade_mode=False)


def test_nonfinite_metrics_become_zero(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    paths[0].write_text(json.dumps({"rows": [{"symbol": "SOXL", "strategy_a_return": "Infinity"}]}), encoding="utf-8")
    assert build_stock_performance_report(*paths).rows[0].strategy_a_return == 0
