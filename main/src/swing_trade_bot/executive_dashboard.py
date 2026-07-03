"""Executive dashboard for paper-only swing trading system outputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "portfolio_allocations.json",
    "portfolio_manager_report.csv",
    "strategy_comparison.json",
    "strategy_recommendations.csv",
    "confidence_report.json",
    "watchlist_report.json",
)
OPTIONAL_FILES = (
    "stock_performance_report.json",
    "weekly_stock_report.json",
    "earnings_report.json",
    "theme_momentum.json",
    "source_confluence.json",
    "opportunity_quality_report.json",
)


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    """High-level summary metrics for the paper-only system."""

    allocated_percent: float
    sgov_reserve_percent: float
    active_positions: int
    watchlist_count: int
    high_confidence_count: int
    strategy_b_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class ExecutiveDashboard:
    """Complete executive dashboard payload."""

    paper_trade_mode: bool
    summary: DashboardSummary
    risk_flags: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    warnings: tuple[str, ...]
    source_files: Mapping[str, bool]


def build_executive_dashboard(results_dir: Path, *, output_dir: Path | None = None, paper_trade_mode: bool = True) -> ExecutiveDashboard:
    """Read existing outputs only and write executive_dashboard.json and .md."""
    if not paper_trade_mode:
        raise ValueError("Executive dashboard requires paper_trade_mode=True")
    output_dir = output_dir or results_dir
    files = {name: (results_dir / name).exists() for name in (*REQUIRED_FILES, *OPTIONAL_FILES)}
    warnings = [f"Missing required output: {name}" for name in REQUIRED_FILES if not files[name]]
    warnings.extend(f"Missing optional output: {name}" for name in OPTIONAL_FILES if not files[name])

    allocations = _read_json(results_dir / "portfolio_allocations.json") if files["portfolio_allocations.json"] else {}
    confidence = _rows_from_json(_read_json(results_dir / "confidence_report.json")) if files["confidence_report.json"] else []
    watchlist = _rows_from_json(_read_json(results_dir / "watchlist_report.json")) if files["watchlist_report.json"] else []
    strategies = _read_csv(results_dir / "strategy_recommendations.csv") if files["strategy_recommendations.csv"] else []
    portfolio_rows = _read_csv(results_dir / "portfolio_manager_report.csv") if files["portfolio_manager_report.csv"] else []

    allocation_rows = allocations.get("allocations", []) if isinstance(allocations, dict) else []
    sgov_reserve = _float(allocations.get("sgov_allocation")) if isinstance(allocations, dict) else 0.0
    allocated = max(0.0, 100.0 - sgov_reserve)
    confidence_counts = Counter(str(row.get("confidence", "")).upper() for row in confidence)
    strategy_b_count = sum(1 for row in strategies if str(row.get("active_strategy", "")).strip().upper() == "STRATEGY B")
    active_positions = _active_position_count(portfolio_rows)
    watchlist_count = sum(1 for row in watchlist if str(row.get("watchlist_status", "")).upper() in {"WATCHLIST", "LOW", "MEDIUM", "HIGH"})

    risk_flags = _risk_flags(allocation_rows, sgov_reserve, warnings)
    suggested_actions = _suggested_actions(risk_flags, warnings, watchlist_count)
    dashboard = ExecutiveDashboard(
        paper_trade_mode=True,
        summary=DashboardSummary(
            allocated_percent=round(allocated, 6),
            sgov_reserve_percent=round(sgov_reserve, 6),
            active_positions=active_positions,
            watchlist_count=watchlist_count,
            high_confidence_count=confidence_counts["HIGH"],
            strategy_b_count=strategy_b_count,
            warning_count=len(warnings),
        ),
        risk_flags=tuple(risk_flags),
        suggested_actions=tuple(suggested_actions),
        warnings=tuple(warnings),
        source_files=files,
    )
    write_executive_dashboard(output_dir, dashboard)
    return dashboard


def write_executive_dashboard(output_dir: Path, dashboard: ExecutiveDashboard) -> tuple[Path, Path]:
    """Write results/executive_dashboard.json and results/executive_dashboard.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "executive_dashboard.json"
    md_path = output_dir / "executive_dashboard.md"
    payload = asdict(dashboard)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_executive_dashboard_markdown(dashboard) + "\n", encoding="utf-8")
    return json_path, md_path


def format_executive_dashboard_markdown(dashboard: ExecutiveDashboard) -> str:
    """Render executive dashboard Markdown."""
    summary = dashboard.summary
    lines = [
        "# Executive Dashboard",
        "",
        "Paper-only: true",
        "No Robinhood execution. No real order placement.",
        "",
        "## Summary Metrics",
        "",
        f"- Allocated Percent: {summary.allocated_percent:.2f}%",
        f"- SGOV Reserve Percent: {summary.sgov_reserve_percent:.2f}%",
        f"- Active Positions: {summary.active_positions}",
        f"- Watchlist Count: {summary.watchlist_count}",
        f"- High Confidence Count: {summary.high_confidence_count}",
        f"- Strategy B Count: {summary.strategy_b_count}",
        "",
        "## Risk Flags",
        "",
    ]
    lines.extend(f"- {flag}" for flag in dashboard.risk_flags) if dashboard.risk_flags else lines.append("- None")
    lines.extend(["", "## Suggested Actions", ""])
    lines.extend(f"- {action}" for action in dashboard.suggested_actions) if dashboard.suggested_actions else lines.append("- Continue monitoring existing paper outputs.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in dashboard.warnings) if dashboard.warnings else lines.append("- None")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create paper-only executive dashboard from existing outputs")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    dashboard = build_executive_dashboard(args.results_dir, output_dir=args.output_dir, paper_trade_mode=True)
    print(format_executive_dashboard_markdown(dashboard))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return list(csv.DictReader(input_file))


def _rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get("rows", payload.get("allocations", []))
        return rows if isinstance(rows, list) else []
    return []


def _float(value: object) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    return float(value)


def _active_position_count(rows: Sequence[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    active = 0
    for row in rows:
        text = " ".join(str(value).upper() for value in row.values())
        if "OPEN" in text or "HOLD" in text or "BUY" in text:
            active += 1
    return active


def _risk_flags(allocation_rows: Sequence[Mapping[str, object]], sgov_reserve: float, warnings: Sequence[str]) -> list[str]:
    flags: list[str] = []
    if sgov_reserve < 10.0:
        flags.append("Low SGOV reserve below 10%")
    for row in allocation_rows:
        symbol = str(row.get("symbol", "")).upper()
        if symbol == "SGOV":
            continue
        allocation = _float(row.get("allocation_percent"))
        if allocation > 25.0:
            flags.append(f"Position allocation exceeds 25% cap: {symbol}")
        theme_allocation = _float(row.get("theme_allocation"))
        if theme_allocation > 40.0:
            flags.append(f"Theme allocation exceeds 40% cap: {row.get('theme', 'Unclassified')}")
    if any(warning.startswith("Missing required") for warning in warnings):
        flags.append("Dashboard is incomplete because required outputs are missing")
    return flags


def _suggested_actions(risk_flags: Sequence[str], warnings: Sequence[str], watchlist_count: int) -> list[str]:
    actions: list[str] = []
    if warnings:
        actions.append("Regenerate missing reports before using the dashboard for allocation review.")
    if any("SGOV" in flag for flag in risk_flags):
        actions.append("Review allocations and preserve enough SGOV reserve for risk control.")
    if watchlist_count == 0:
        actions.append("Run discovery/watchlist reports to refresh candidate coverage.")
    if not actions:
        actions.append("Review risk flags and suggested paper-only rebalance actions before the next cycle.")
    return actions


if __name__ == "__main__":
    main()
