"""Monthly management summary for existing paper-only Swing reports.

This module is an aggregation boundary. It reads reports produced by their
owning Swing modules and never recalculates strategy, scoring, allocation,
lifecycle, or performance results.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "monthly_command_center"
MODULE_VERSION = "1.0.0"
REPORT_VERSION = "1.0"

REQUIRED_FILES = (
    "executive_dashboard.json",
    "weekly_stock_report.json",
    "stock_performance_report.json",
    "portfolio_allocations.json",
)
OPTIONAL_FILES = (
    "portfolio_manager_report.csv",
    "strategy_comparison.json",
    "strategy_recommendations.csv",
    "confidence_report.json",
    "confidence_report.csv",
    "watchlist_report.json",
    "watchlist_report.csv",
    "earnings_report.json",
    "earnings_report.csv",
    "theme_momentum.json",
    "source_confluence.json",
)


@dataclass(frozen=True, slots=True)
class MonthlyCommandCenter:
    """Complete Version 1.0 monthly management payload."""

    paper_trade_mode: bool
    report_version: str
    executive_summary: Mapping[str, Any]
    weekly_summary: Mapping[str, Any]
    performance_summary: Mapping[str, Any]
    allocation_summary: Mapping[str, Any]
    risk_flags: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    warnings: tuple[str, ...]
    source_files: Mapping[str, bool]


def build_monthly_command_center(
    results_dir: Path,
    *,
    output_dir: Path | None = None,
    paper_trade_mode: bool = True,
) -> MonthlyCommandCenter:
    """Build and write the command center from authentic existing reports."""
    if not paper_trade_mode:
        raise ValueError("Monthly Command Center requires paper_trade_mode=True")

    results_dir = Path(results_dir)
    output_dir = Path(output_dir) if output_dir is not None else results_dir
    source_files = {
        name: (results_dir / name).is_file()
        for name in (*REQUIRED_FILES, *OPTIONAL_FILES)
    }
    missing_required = [name for name in REQUIRED_FILES if not source_files[name]]
    if missing_required:
        joined = ", ".join(missing_required)
        raise FileNotFoundError(f"Missing required Monthly Command Center inputs: {joined}")

    executive = _read_json_object(results_dir / "executive_dashboard.json")
    weekly = _read_json_object(results_dir / "weekly_stock_report.json")
    performance = _read_json_object(results_dir / "stock_performance_report.json")
    allocations = _read_json_object(results_dir / "portfolio_allocations.json")

    _require_paper_only("executive_dashboard.json", executive)
    _require_paper_only("weekly_stock_report.json", weekly)
    _require_paper_only("stock_performance_report.json", performance)
    _require_paper_only("portfolio_allocations.json", allocations)

    warnings = tuple(
        f"Missing optional output: {name}"
        for name in OPTIONAL_FILES
        if not source_files[name]
    )
    command_center = MonthlyCommandCenter(
        paper_trade_mode=True,
        report_version=REPORT_VERSION,
        executive_summary=_mapping(executive.get("summary")),
        weekly_summary=_first_mapping(weekly, "summary", "executive_summary"),
        performance_summary=_first_mapping(performance, "executive_summary", "summary"),
        allocation_summary=_allocation_summary(allocations),
        risk_flags=_string_tuple(executive.get("risk_flags")),
        suggested_actions=_string_tuple(executive.get("suggested_actions")),
        warnings=warnings,
        source_files=source_files,
    )
    write_monthly_command_center(output_dir, command_center)
    return command_center


def write_monthly_command_center(
    output_dir: Path,
    command_center: MonthlyCommandCenter,
) -> tuple[Path, Path]:
    """Write monthly_command_center.json and monthly_command_center.md."""
    if command_center.paper_trade_mode is not True:
        raise ValueError("Monthly Command Center requires paper_trade_mode=True")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "monthly_command_center.json"
    markdown_path = output_dir / "monthly_command_center.md"
    json_path.write_text(
        json.dumps(
            {
                "module_name": MODULE_NAME,
                "module_version": MODULE_VERSION,
                **asdict(command_center),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        format_monthly_command_center_markdown(command_center) + "\n",
        encoding="utf-8",
    )
    return json_path, markdown_path


def format_monthly_command_center_markdown(
    command_center: MonthlyCommandCenter,
) -> str:
    """Render a deterministic human-readable monthly review."""
    lines = [
        "# Monthly Command Center",
        "",
        f"- Report version: {command_center.report_version}",
        "- Paper-only: true",
        "- Advisory-only: true",
        "",
        "## Executive Summary",
        "",
    ]
    lines.extend(_mapping_lines(command_center.executive_summary))
    lines.extend(["", "## Weekly Summary", ""])
    lines.extend(_mapping_lines(command_center.weekly_summary))
    lines.extend(["", "## Performance Summary", ""])
    lines.extend(_mapping_lines(command_center.performance_summary))
    lines.extend(["", "## Allocation Summary", ""])
    lines.extend(_mapping_lines(command_center.allocation_summary))
    lines.extend(["", "## Risk Flags", ""])
    lines.extend(
        f"- {item}" for item in command_center.risk_flags
    ) if command_center.risk_flags else lines.append("- None")
    lines.extend(["", "## Suggested Paper-Only Actions", ""])
    lines.extend(
        f"- {item}" for item in command_center.suggested_actions
    ) if command_center.suggested_actions else lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    lines.extend(
        f"- {item}" for item in command_center.warnings
    ) if command_center.warnings else lines.append("- None")
    return "\n".join(lines)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} root must be a JSON object")
    return payload


def _require_paper_only(name: str, payload: Mapping[str, Any]) -> None:
    if payload.get("paper_trade_mode") is not True:
        raise ValueError(f"{name} must contain paper_trade_mode=True")


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_mapping(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _allocation_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    allocations = payload.get("allocations")
    rows = allocations if isinstance(allocations, list) else []
    return {
        "allocation_count": len(rows),
        "sgov_allocation": payload.get("sgov_allocation", 0.0),
        "cash_allocation": payload.get("cash_allocation", 0.0),
    }


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _mapping_lines(payload: Mapping[str, Any]) -> list[str]:
    if not payload:
        return ["- No summary fields were published by the owning report."]
    return [f"- {key}: {payload[key]}" for key in sorted(payload)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create the paper-only Swing Monthly Command Center"
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    report = build_monthly_command_center(
        args.results_dir,
        output_dir=args.output_dir,
        paper_trade_mode=True,
    )
    print(format_monthly_command_center_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
