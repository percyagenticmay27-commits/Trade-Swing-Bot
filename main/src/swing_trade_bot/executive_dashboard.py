"""Executive dashboard for paper-only swing research outputs."""

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
    "strategy_assignments.json",
    "trade_lifecycle_report.json",
    "profit_protection_report.json",
    "reentry_report.json",
    "exit_review_report.json",
    "thesis_monitor_report.json",
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
    position_intelligence_count: int
    thesis_strong_count: int
    thesis_intact_count: int
    thesis_attention_count: int
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
    strategy_assignments = _rows_from_json(_read_json(results_dir / "strategy_assignments.json"), key="assignments") if files["strategy_assignments.json"] else []
    lifecycle_reviews = _rows_from_json(_read_json(results_dir / "trade_lifecycle_report.json"), key="reviews") if files["trade_lifecycle_report.json"] else []
    profit_reviews = _rows_from_json(_read_json(results_dir / "profit_protection_report.json"), key="reviews") if files["profit_protection_report.json"] else []
    reentry_reviews = _rows_from_json(_read_json(results_dir / "reentry_report.json"), key="reviews") if files["reentry_report.json"] else []
    exit_reviews = _rows_from_json(_read_json(results_dir / "exit_review_report.json"), key="reviews") if files["exit_review_report.json"] else []
    thesis_reviews = _rows_from_json(_read_json(results_dir / "thesis_monitor_report.json"), key="reviews") if files["thesis_monitor_report.json"] else []

    allocation_rows = allocations.get("allocations", []) if isinstance(allocations, dict) else []
    sgov_reserve = _float(allocations.get("sgov_allocation")) if isinstance(allocations, dict) else 0.0
    allocated = max(0.0, 100.0 - sgov_reserve)
    confidence_counts = Counter(str(row.get("confidence", "")).upper() for row in confidence)
    thesis_counts = Counter(str(row.get("thesis_state", "")).lower() for row in thesis_reviews)
    strategy_b_count = _strategy_b_count(strategies, strategy_assignments)
    active_positions = _active_position_count(portfolio_rows)
    watchlist_count = sum(1 for row in watchlist if str(row.get("watchlist_status", "")).upper() in {"WATCHLIST", "LOW", "MEDIUM", "HIGH"})
    position_intelligence_count = _position_intelligence_count(lifecycle_reviews, profit_reviews, reentry_reviews, exit_reviews, thesis_reviews)

    risk_flags = _risk_flags(allocation_rows, sgov_reserve, warnings)
    risk_flags.extend(_position_intelligence_flags(lifecycle_reviews, profit_reviews, reentry_reviews, exit_reviews, thesis_reviews))
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
            position_intelligence_count=position_intelligence_count,
            thesis_strong_count=thesis_counts["strong"],
            thesis_intact_count=thesis_counts["intact"],
            thesis_attention_count=thesis_counts["weakening"] + thesis_counts["broken"],
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
        "Research outputs only.",
        "",
        "## Summary Metrics",
        "",
        f"- Allocated Percent: {summary.allocated_percent:.2f}%",
        f"- SGOV Reserve Percent: {summary.sgov_reserve_percent:.2f}%",
        f"- Active Positions: {summary.active_positions}",
        f"- Watchlist Count: {summary.watchlist_count}",
        f"- High Confidence Count: {summary.high_confidence_count}",
        f"- Strategy B Count: {summary.strategy_b_count}",
        f"- Position Intelligence Count: {summary.position_intelligence_count}",
        f"- Thesis Strong Count: {summary.thesis_strong_count}",
        f"- Thesis Intact Count: {summary.thesis_intact_count}",
        f"- Thesis Attention Count: {summary.thesis_attention_count}",
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


def _rows_from_json(payload: Any, *, key: str | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get(key, []) if key else payload.get("rows", payload.get("allocations", payload.get("assignments", payload.get("reviews", []))))
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
        if "OPEN" in text or "HOLD" in text:
            active += 1
    return active


def _strategy_b_count(strategies: Sequence[Mapping[str, object]], assignments: Sequence[Mapping[str, object]]) -> int:
    assignment_count = sum(1 for row in assignments if str(row.get("recommended_strategy", row.get("active_strategy", ""))).strip().upper() == "STRATEGY B")
    if assignment_count:
        return assignment_count
    return sum(1 for row in strategies if str(row.get("active_strategy", "")).strip().upper() == "STRATEGY B")


def _position_intelligence_count(
    lifecycle_reviews: Sequence[Mapping[str, object]],
    profit_reviews: Sequence[Mapping[str, object]],
    reentry_reviews: Sequence[Mapping[str, object]],
    exit_reviews: Sequence[Mapping[str, object]],
    thesis_reviews: Sequence[Mapping[str, object]],
) -> int:
    return len(lifecycle_reviews) + len(profit_reviews) + len(reentry_reviews) + len(exit_reviews) + len(thesis_reviews)


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


def _position_intelligence_flags(
    lifecycle_reviews: Sequence[Mapping[str, object]],
    profit_reviews: Sequence[Mapping[str, object]],
    reentry_reviews: Sequence[Mapping[str, object]],
    exit_reviews: Sequence[Mapping[str, object]],
    thesis_reviews: Sequence[Mapping[str, object]],
) -> list[str]:
    flags: list[str] = []
    if any(str(row.get("recommended_state", "")) == "review_required" for row in lifecycle_reviews):
        flags.append("Position lifecycle review required")
    if any(str(row.get("protection_zone", "")) == "giveback_review_zone" for row in profit_reviews):
        flags.append("Profit protection giveback review detected")
    if any(str(row.get("reentry_state", "")) == "reentry_ready" for row in reentry_reviews):
        flags.append("Reentry-ready paper setup detected")
    if any(str(row.get("outcome", "")) not in {"", "continue_holding"} for row in exit_reviews):
        flags.append("Exit review attention required")
    if any(str(row.get("thesis_state", "")).lower() in {"weakening", "broken"} for row in thesis_reviews):
        flags.append("Thesis monitor attention required")
    return flags


def _suggested_actions(risk_flags: Sequence[str], warnings: Sequence[str], watchlist_count: int) -> list[str]:
    actions: list[str] = []
    if warnings:
        actions.append("Regenerate missing reports before dashboard review.")
    if any("SGOV" in flag for flag in risk_flags):
        actions.append("Review allocations and preserve enough SGOV reserve for risk control.")
    if any("thesis" in flag.lower() for flag in risk_flags):
        actions.append("Review Thesis Monitor outputs before the next paper cycle.")
    if any("review" in flag.lower() for flag in risk_flags):
        actions.append("Review Position Intelligence Layer outputs before the next paper cycle.")
    if watchlist_count == 0:
        actions.append("Run discovery/watchlist reports to refresh candidate coverage.")
    if not actions:
        actions.append("Review risk flags and suggested paper-only actions before the next cycle.")
    return actions


if __name__ == "__main__":
    main()
