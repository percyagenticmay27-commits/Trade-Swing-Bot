"""Paper-only per-symbol stock performance reporting.

This module reads existing strategy and portfolio outputs.  It does not connect
to a broker, place orders, or change portfolio state.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MODULE_NAME = "stock_performance_report"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
REQUIRED_INPUTS = (
    "strategy_comparison.json",
    "strategy_recommendations.csv",
    "portfolio_allocations.json",
    "portfolio_manager_report.csv",
)


@dataclass(frozen=True, slots=True)
class StockPerformanceRow:
    symbol: str
    confidence_level: str
    target_allocation: float
    current_allocation: float
    portfolio_action: str
    active_strategy: str
    recommended_strategy: str
    switch_eligible: bool
    months_outperforming: int
    strategy_a_return: float
    strategy_b_return: float
    strategy_a_win_rate: float
    strategy_b_win_rate: float
    strategy_a_trades: int
    strategy_b_trades: int
    strategy_a_net_profit: float
    strategy_b_net_profit: float
    strategy_a_max_drawdown: float
    strategy_b_max_drawdown: float
    better_win_rate_strategy: str
    better_profit_strategy: str
    better_drawdown_strategy: str
    suggested_action: str


@dataclass(frozen=True, slots=True)
class StockPerformanceReport:
    module_name: str
    module_version: str
    schema_version: str
    paper_trade_mode: bool
    symbols_reviewed: int
    strategy_switch_eligible: int
    rows: tuple[StockPerformanceRow, ...]
    warnings: tuple[str, ...]
    source_files: Mapping[str, bool]


def build_stock_performance_report(
    strategy_comparison_path: Path,
    strategy_recommendations_path: Path,
    portfolio_allocations_path: Path,
    portfolio_manager_report_path: Path,
    *,
    paper_trade_mode: bool = True,
) -> StockPerformanceReport:
    """Build a deterministic report from existing paper-trading outputs."""
    if not paper_trade_mode:
        raise ValueError("Stock performance reporting requires paper_trade_mode=True")

    paths = {
        "strategy_comparison.json": Path(strategy_comparison_path),
        "strategy_recommendations.csv": Path(strategy_recommendations_path),
        "portfolio_allocations.json": Path(portfolio_allocations_path),
        "portfolio_manager_report.csv": Path(portfolio_manager_report_path),
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required input(s): " + ", ".join(missing))

    comparison = _index_rows(_json_rows(_read_json(paths["strategy_comparison.json"])))
    recommendations = _index_rows(_read_csv(paths["strategy_recommendations.csv"]))
    allocations_payload = _read_json(paths["portfolio_allocations.json"])
    allocations = _index_rows(_json_rows(allocations_payload, preferred=("allocations", "rows")))
    portfolio = _index_rows(_read_csv(paths["portfolio_manager_report.csv"]))

    symbols = sorted(set(comparison) | set(recommendations) | set(allocations) | set(portfolio))
    warnings: list[str] = []
    rows: list[StockPerformanceRow] = []
    for symbol in symbols:
        comp = comparison.get(symbol, {})
        recommendation = recommendations.get(symbol, {})
        allocation = allocations.get(symbol, {})
        manager = portfolio.get(symbol, {})

        active = _text(recommendation, "active_strategy", "current_strategy", default=_text(comp, "active_strategy"))
        recommended = _text(
            recommendation,
            "recommended_strategy",
            "strategy_recommendation",
            default=_text(comp, "recommended_strategy", default=active),
        )
        months = _integer(recommendation, "months_outperforming", "outperformance_months")
        explicit_switch = _optional_bool(recommendation, "switch_eligible", "strategy_switch_eligible")
        switch_eligible = explicit_switch if explicit_switch is not None else bool(
            active and recommended and _strategy(active) != _strategy(recommended) and months >= 3
        )

        a_return = _metric(comp, "strategy_a_return", "a_return", "strategy_a_total_return")
        b_return = _metric(comp, "strategy_b_return", "b_return", "strategy_b_total_return")
        a_win = _metric(comp, "strategy_a_win_rate", "a_win_rate")
        b_win = _metric(comp, "strategy_b_win_rate", "b_win_rate")
        a_trades = _integer(comp, "strategy_a_trades", "a_trades", "strategy_a_trade_count")
        b_trades = _integer(comp, "strategy_b_trades", "b_trades", "strategy_b_trade_count")
        a_profit = _metric(comp, "strategy_a_net_profit", "a_net_profit", "strategy_a_profit")
        b_profit = _metric(comp, "strategy_b_net_profit", "b_net_profit", "strategy_b_profit")
        a_drawdown = abs(_metric(comp, "strategy_a_max_drawdown", "a_max_drawdown"))
        b_drawdown = abs(_metric(comp, "strategy_b_max_drawdown", "b_max_drawdown"))
        better_win = _better(a_win, b_win, higher=True)
        better_profit = _better(a_profit, b_profit, higher=True)
        better_drawdown = _better(a_drawdown, b_drawdown, higher=False)
        action = (
            f"{better_profit} has better net profit; {better_drawdown} has better drawdown."
            if better_profit != "TIE" or better_drawdown != "TIE"
            else "Continue collecting paper results; strategy evidence is tied."
        )
        if switch_eligible:
            action = f"Review paper-only switch from {active or 'UNASSIGNED'} to {recommended}. " + action

        rows.append(
            StockPerformanceRow(
                symbol=symbol,
                confidence_level=_text(manager, "confidence_level", "confidence", default=_text(recommendation, "confidence_level", "confidence")),
                target_allocation=_metric(allocation, "target_allocation", "target_allocation_percent", "allocation_percent"),
                current_allocation=_metric(manager, "current_allocation", "current_allocation_percent", "allocation_percent"),
                portfolio_action=_text(manager, "suggested_action", "portfolio_action", "action"),
                active_strategy=active,
                recommended_strategy=recommended,
                switch_eligible=switch_eligible,
                months_outperforming=months,
                strategy_a_return=a_return,
                strategy_b_return=b_return,
                strategy_a_win_rate=a_win,
                strategy_b_win_rate=b_win,
                strategy_a_trades=a_trades,
                strategy_b_trades=b_trades,
                strategy_a_net_profit=a_profit,
                strategy_b_net_profit=b_profit,
                strategy_a_max_drawdown=a_drawdown,
                strategy_b_max_drawdown=b_drawdown,
                better_win_rate_strategy=better_win,
                better_profit_strategy=better_profit,
                better_drawdown_strategy=better_drawdown,
                suggested_action=action,
            )
        )

    if not rows:
        warnings.append("Required inputs contained no symbol rows.")
    return StockPerformanceReport(
        module_name=MODULE_NAME,
        module_version=MODULE_VERSION,
        schema_version=SCHEMA_VERSION,
        paper_trade_mode=True,
        symbols_reviewed=len(rows),
        strategy_switch_eligible=sum(row.switch_eligible for row in rows),
        rows=tuple(rows),
        warnings=tuple(warnings),
        source_files={name: True for name in REQUIRED_INPUTS},
    )


def write_stock_performance_report(output_dir: Path, report: StockPerformanceReport) -> tuple[Path, Path, Path]:
    """Write CSV, JSON, and Markdown report artifacts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stock_performance_report.csv"
    json_path = output_dir / "stock_performance_report.json"
    md_path = output_dir / "stock_performance_report.md"
    row_payloads = [asdict(row) for row in report.rows]
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        fieldnames = list(StockPerformanceRow.__dataclass_fields__)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(row_payloads)
    json_path.write_text(json.dumps(asdict(report), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    md_path.write_text(format_stock_performance_markdown(report) + "\n", encoding="utf-8")
    return csv_path, json_path, md_path


def build_and_write_stock_performance_report(
    strategy_comparison_path: Path,
    strategy_recommendations_path: Path,
    portfolio_allocations_path: Path,
    portfolio_manager_report_path: Path,
    output_dir: Path,
    *,
    paper_trade_mode: bool = True,
) -> StockPerformanceReport:
    report = build_stock_performance_report(
        strategy_comparison_path,
        strategy_recommendations_path,
        portfolio_allocations_path,
        portfolio_manager_report_path,
        paper_trade_mode=paper_trade_mode,
    )
    write_stock_performance_report(output_dir, report)
    return report


def format_stock_performance_markdown(report: StockPerformanceReport) -> str:
    lines = [
        "# Stock Performance Report",
        "",
        "Paper-only: true",
        "",
        "## Summary",
        "",
        f"- Symbols Reviewed: {report.symbols_reviewed}",
        f"- Strategy Switch Eligible: {report.strategy_switch_eligible}",
        "",
        "## Per-Symbol Performance",
        "",
        "| Symbol | Confidence | Target % | Current % | Action | Active | Recommended | Switch | A Return | B Return | A Win Rate | B Win Rate | A Trades | B Trades |",
        "|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.rows:
        lines.append(
            f"| {row.symbol} | {row.confidence_level or '-'} | {row.target_allocation:.2f} | "
            f"{row.current_allocation:.2f} | {row.portfolio_action or '-'} | {row.active_strategy or '-'} | "
            f"{row.recommended_strategy or '-'} | {'YES' if row.switch_eligible else 'NO'} | "
            f"{row.strategy_a_return:.2f} | {row.strategy_b_return:.2f} | "
            f"{row.strategy_a_win_rate:.2f} | {row.strategy_b_win_rate:.2f} | "
            f"{row.strategy_a_trades} | {row.strategy_b_trades} |"
        )
    if not report.rows:
        lines.append("| None | - | - | - | - | - | - | - | - | - | - | - | - | - |")
    lines.extend(["", "## Suggested Actions", ""])
    lines.extend(f"- **{row.symbol}:** {row.suggested_action}" for row in report.rows)
    if not report.rows:
        lines.append("- No symbol actions available.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings) if report.warnings else lines.append("- None")
    return "\n".join(lines)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON input {path}: {exc}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as input_file:
            return list(csv.DictReader(input_file))
    except (OSError, csv.Error) as exc:
        raise ValueError(f"Invalid CSV input {path}: {exc}") from exc


def _json_rows(payload: Any, preferred: Sequence[str] = ("rows", "results", "comparisons")) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in preferred:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, Mapping)]
    return []


def _index_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol", row.get("ticker", row.get("underlying_symbol", "")))).strip().upper()
        if symbol:
            indexed[symbol] = row
    return indexed


def _value(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    value = _value(row, *names)
    return default if value is None else str(value).strip()


def _metric(row: Mapping[str, Any], *names: str) -> float:
    value = _value(row, *names)
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        number = float(str(value).strip().replace("%", "").replace(",", ""))
    except ValueError:
        return 0.0
    return number if math.isfinite(number) else 0.0


def _integer(row: Mapping[str, Any], *names: str) -> int:
    return int(_metric(row, *names))


def _optional_bool(row: Mapping[str, Any], *names: str) -> bool | None:
    value = _value(row, *names)
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "eligible"}:
        return True
    if text in {"false", "no", "0", "not_eligible"}:
        return False
    return None


def _strategy(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().upper()


def _better(a_value: float, b_value: float, *, higher: bool) -> str:
    if math.isclose(a_value, b_value):
        return "TIE"
    a_wins = a_value > b_value if higher else a_value < b_value
    return "STRATEGY A" if a_wins else "STRATEGY B"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper-only stock performance report")
    parser.add_argument("--strategy-comparison", type=Path, default=Path("results/strategy_comparison.json"))
    parser.add_argument("--strategy-recommendations", type=Path, default=Path("results/strategy_recommendations.csv"))
    parser.add_argument("--portfolio-allocations", type=Path, default=Path("results/portfolio_allocations.json"))
    parser.add_argument("--portfolio-manager-report", type=Path, default=Path("results/portfolio_manager_report.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    report = build_and_write_stock_performance_report(
        args.strategy_comparison,
        args.strategy_recommendations,
        args.portfolio_allocations,
        args.portfolio_manager_report,
        args.output_dir,
    )
    print(format_stock_performance_markdown(report))


if __name__ == "__main__":
    main()
