"""Paper-only Position Intelligence Engine.

Version 1.3 scope:
- Consolidate existing paper-only reports into one daily decision summary.
- Use existing outputs only.
- Do not create new scores.
- Do not modify allocations.
- Do not connect to external market or brokerage systems.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REPORT_VERSION = "1.3"
GENERATED_BY = "position_intelligence_engine"
PAPER_TRADE_MODE = True

OUTPUT_JSON = "position_intelligence.json"
OUTPUT_MD = "position_intelligence.md"

REQUIRED_FILES = {
    "opportunity_quality": "opportunity_quality.json",
    "strategy_assignments": "strategy_assignments.json",
    "trade_lifecycle_report": "trade_lifecycle_report.json",
    "profit_protection_report": "profit_protection_report.json",
    "reentry_report": "reentry_report.json",
    "exit_review_report": "exit_review_report.json",
    "portfolio_allocations": "portfolio_allocations.json",
}

OPTIONAL_RESULT_FILES = {
    "executive_dashboard": ("executive_dashboard.json",),
    "confidence_report": ("confidence_report.json", "confidence_report.csv"),
    "earnings_report": ("earnings_report.json", "earnings_report.csv"),
    "position_lifecycle": ("position_lifecycle.json",),
    "portfolio_risk": ("portfolio_risk.json",),
    "entry_scores": ("entry_scores.json",),
    "conviction_scores": ("conviction_scores.json",),
    "momentum_scores": ("momentum_scores.json",),
}

OPTIONAL_DATA_FILES = {
    "position_intelligence_context": (
        "position_intelligence_context.json",
        "position_intelligence_context.csv",
    ),
}

DECISION_STATES = {
    "MONITOR_WATCHLIST",
    "REVIEW_ENTRY",
    "REVIEW_REENTRY",
    "HOLD_ACTIVE_POSITION",
    "REVIEW_PROFIT_PROTECTION",
    "REVIEW_EXIT",
    "WAIT_FOR_ENTRY",
    "WAIT_FOR_REENTRY",
    "REMOVE_FROM_ACTIVE_REVIEW",
    "NEEDS_MANUAL_REVIEW",
    "NO_ACTION_REQUIRED",
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
RESERVE_SYMBOLS = {"SGOV", "CASH", "RESERVE"}


@dataclass(frozen=True, slots=True)
class PositionIntelligenceWarning:
    source: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class SymbolPositionIntelligence:
    symbol: str
    decision_state: str
    strategy_assignment: str
    opportunity_quality_score: float
    opportunity_classification: str
    entry_gate_status: str
    lifecycle_state: str
    allocation_pct: float
    profit_protection_state: str
    reentry_state: str
    exit_review_state: str
    final_recommendation: str
    summary: str
    source: str = GENERATED_BY


@dataclass(frozen=True, slots=True)
class PositionIntelligenceRiskFlag:
    flag_type: str
    symbol: str | None
    severity: str
    message: str
    source: str


@dataclass(frozen=True, slots=True)
class PositionIntelligenceReviewAction:
    action_type: str
    symbol: str | None
    priority: str
    message: str
    source: str


@dataclass(frozen=True, slots=True)
class PositionIntelligenceSummaryMetrics:
    paper_trade_mode: bool
    symbols_analyzed: int
    monitor_watchlist_count: int
    review_entry_count: int
    review_reentry_count: int
    hold_active_position_count: int
    review_profit_protection_count: int
    review_exit_count: int
    wait_for_entry_count: int
    wait_for_reentry_count: int
    remove_from_active_review_count: int
    manual_review_count: int
    no_action_required_count: int
    strategy_a_count: int
    strategy_b_count: int
    risk_flag_count: int
    review_action_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class PositionIntelligenceReport:
    report_version: str
    generated_by: str
    generated_at_utc: str
    paper_trade_mode: bool
    data_sources: dict[str, dict[str, str]]
    summary_metrics: PositionIntelligenceSummaryMetrics
    symbol_position_intelligence: list[SymbolPositionIntelligence]
    risk_flags: list[PositionIntelligenceRiskFlag]
    suggested_review_actions: list[PositionIntelligenceReviewAction]
    warnings: list[PositionIntelligenceWarning]
    sections: dict[str, Any] = field(default_factory=dict)


def build_position_intelligence_report(
    results_dir: str = "results",
    data_dir: str = "data",
) -> PositionIntelligenceReport:
    """Build and return the paper-only Position Intelligence report."""
    results_path = Path(results_dir)
    data_path = Path(data_dir)

    required = _load_required_inputs(results_path)
    optional, warnings, optional_status = _load_optional_inputs(results_path, data_path)
    data_sources = _build_data_source_status(optional_status)

    symbols = _extract_symbols(required, optional)
    rows = [
        _build_symbol_position_intelligence(symbol, required, optional)
        for symbol in sorted(symbols)
        if symbol.upper() not in RESERVE_SYMBOLS
    ]
    risk_flags = _generate_position_intelligence_risk_flags(rows, warnings)
    actions = _generate_position_intelligence_review_actions(rows, risk_flags)
    summary = _calculate_summary_metrics(rows, risk_flags, actions, warnings)

    return PositionIntelligenceReport(
        report_version=REPORT_VERSION,
        generated_by=GENERATED_BY,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        paper_trade_mode=PAPER_TRADE_MODE,
        data_sources=data_sources,
        summary_metrics=summary,
        symbol_position_intelligence=rows,
        risk_flags=risk_flags,
        suggested_review_actions=actions,
        warnings=warnings,
        sections={
            "position_intelligence_overview": {},
            "daily_decision_summary": {},
            "entry_reviews": {},
            "reentry_reviews": {},
            "active_positions": {},
            "profit_protection_reviews": {},
            "exit_reviews": {},
            "manual_reviews": {},
            "risk_summary": {},
            "review_plan": {},
        },
    )


def write_position_intelligence_reports(output_dir: str, report: PositionIntelligenceReport) -> None:
    """Write position_intelligence.json and position_intelligence.md."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / OUTPUT_JSON).write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_path / OUTPUT_MD).write_text(
        format_position_intelligence_markdown(report),
        encoding="utf-8",
    )


def build_and_write_position_intelligence_report(
    results_dir: str = "results",
    data_dir: str = "data",
) -> PositionIntelligenceReport:
    """Build and write the paper-only Position Intelligence report."""
    report = build_position_intelligence_report(results_dir=results_dir, data_dir=data_dir)
    write_position_intelligence_reports(results_dir, report)
    return report


def format_position_intelligence_markdown(report: PositionIntelligenceReport) -> str:
    """Render Position Intelligence as Markdown."""
    metrics = report.summary_metrics
    lines = [
        "# Position Intelligence Report",
        "",
        "## Paper-Only Status",
        "",
        f"- paper_trade_mode={report.paper_trade_mode}",
        "- No Robinhood connection",
        "- No broker integration",
        "- No real placement activity",
        "- No live market/news/price fetching",
        "- Review actions only",
        "",
        "## Position Intelligence Overview",
        "",
        "This report consolidates existing paper-only outputs into one daily review state per symbol.",
        "",
        "## Data Sources",
        "",
        "### Required",
    ]
    for key, status in report.data_sources.get("required", {}).items():
        lines.append(f"- {key}: {status}")
    lines.extend(["", "### Optional"])
    for key, status in report.data_sources.get("optional", {}).items():
        lines.append(f"- {key}: {status}")

    lines.extend(
        [
            "",
            "## Summary Metrics",
            "",
            f"- Symbols analyzed: {metrics.symbols_analyzed}",
            f"- Review entry: {metrics.review_entry_count}",
            f"- Review re-entry: {metrics.review_reentry_count}",
            f"- Hold active position: {metrics.hold_active_position_count}",
            f"- Review profit protection: {metrics.review_profit_protection_count}",
            f"- Review exit: {metrics.review_exit_count}",
            f"- Wait for entry: {metrics.wait_for_entry_count}",
            f"- Wait for re-entry: {metrics.wait_for_reentry_count}",
            f"- Monitor watchlist: {metrics.monitor_watchlist_count}",
            f"- Manual review: {metrics.manual_review_count}",
            f"- Strategy A: {metrics.strategy_a_count}",
            f"- Strategy B: {metrics.strategy_b_count}",
            f"- Risk flags: {metrics.risk_flag_count}",
            f"- Review actions: {metrics.review_action_count}",
            f"- Warnings: {metrics.warning_count}",
            "",
            "## Daily Decision Summary",
            "",
            "| Symbol | Decision State | Strategy | Opportunity | Entry Gate | Lifecycle | Allocation % |",
            "|---|---|---|---:|---|---|---:|",
        ]
    )
    for row in report.symbol_position_intelligence:
        lines.append(
            f"| {row.symbol} | {row.decision_state} | {row.strategy_assignment} | "
            f"{row.opportunity_quality_score:.2f} | {row.entry_gate_status} | "
            f"{row.lifecycle_state} | {row.allocation_pct:.2f} |"
        )

    _append_decision_section(lines, "## Entry Reviews", report, "REVIEW_ENTRY")
    _append_decision_section(lines, "## Re-entry Reviews", report, "REVIEW_REENTRY")
    _append_decision_section(lines, "## Active Positions", report, "HOLD_ACTIVE_POSITION")
    _append_decision_section(lines, "## Profit Protection Reviews", report, "REVIEW_PROFIT_PROTECTION")
    _append_decision_section(lines, "## Exit Reviews", report, "REVIEW_EXIT")
    _append_decision_section(lines, "## Manual Reviews", report, "NEEDS_MANUAL_REVIEW")

    lines.extend(["", "## Risk Flags", ""])
    if report.risk_flags:
        for flag in report.risk_flags:
            lines.append(f"- {flag.severity.upper()} - {flag.symbol or 'PORTFOLIO'} - {flag.flag_type}: {flag.message}")
    else:
        lines.append("None.")

    lines.extend(["", "## Suggested Review Actions", ""])
    if report.suggested_review_actions:
        for action in report.suggested_review_actions:
            lines.append(f"- {action.priority.upper()} - {action.symbol or 'PORTFOLIO'} - {action.action_type}: {action.message}")
    else:
        lines.append("None.")

    lines.extend(["", "## Warnings", ""])
    if report.warnings:
        for warning in report.warnings:
            lines.append(f"- {warning.severity.upper()} - {warning.source}: {warning.message}")
    else:
        lines.append("None.")

    lines.extend(
        [
            "",
            "## Version 1.3 Scope",
            "",
            "This module summarizes existing paper-only review states. It does not create new scores or modify allocations.",
        ]
    )
    return "\n".join(lines) + "\n"


def format_console_summary(report: PositionIntelligenceReport) -> str:
    """Return a concise console summary."""
    metrics = report.summary_metrics
    return (
        f"Position Intelligence v{report.report_version}: "
        f"symbols={metrics.symbols_analyzed}, "
        f"entries={metrics.review_entry_count}, "
        f"reentries={metrics.review_reentry_count}, "
        f"exits={metrics.review_exit_count}, "
        f"profit_reviews={metrics.review_profit_protection_count}, "
        f"flags={metrics.risk_flag_count}, "
        f"warnings={metrics.warning_count}"
    )


def _load_required_inputs(results_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, filename in REQUIRED_FILES.items():
        path = results_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input: {path}")
        try:
            data[key] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed required JSON input: {path}: {exc}") from exc
    return data


def _load_optional_inputs(
    results_path: Path,
    data_path: Path,
) -> tuple[dict[str, Any], list[PositionIntelligenceWarning], dict[str, str]]:
    optional: dict[str, Any] = {}
    warnings: list[PositionIntelligenceWarning] = []
    status: dict[str, str] = {}

    for key, filenames in OPTIONAL_RESULT_FILES.items():
        value, source, warning = _load_first_optional(results_path, filenames)
        if warning is not None:
            warnings.append(warning)
        if value is None:
            status[key] = "missing"
            warnings.append(PositionIntelligenceWarning(key, "low", f"Optional input missing: {key}"))
        else:
            optional[key] = value
            status[key] = f"loaded:{source}"

    for key, filenames in OPTIONAL_DATA_FILES.items():
        value, source, warning = _load_first_optional(data_path, filenames)
        if warning is not None:
            warnings.append(warning)
        if value is None:
            status[key] = "missing"
            warnings.append(PositionIntelligenceWarning(key, "low", f"Optional input missing: {key}"))
        else:
            optional[key] = value
            status[key] = f"loaded:{source}"

    return optional, warnings, status


def _load_first_optional(base: Path, filenames: Iterable[str]) -> tuple[Any | None, str | None, PositionIntelligenceWarning | None]:
    for filename in filenames:
        path = base / filename
        if not path.exists():
            continue
        try:
            if path.suffix.lower() == ".json":
                return json.loads(path.read_text(encoding="utf-8")), filename, None
            if path.suffix.lower() == ".csv":
                text = path.read_text(encoding="utf-8")
                if "\x00" in text:
                    raise csv.Error("CSV contains null bytes.")
                return list(csv.DictReader(text.splitlines())), filename, None
        except (json.JSONDecodeError, csv.Error, UnicodeDecodeError, OSError) as exc:
            return None, filename, PositionIntelligenceWarning(filename, "medium", f"Optional input could not be parsed: {exc}")
    return None, None, None


def _build_data_source_status(optional_status: Mapping[str, str]) -> dict[str, dict[str, str]]:
    return {
        "required": {key: "loaded" for key in REQUIRED_FILES},
        "optional": {key: optional_status.get(key, "missing") for key in (*OPTIONAL_RESULT_FILES, *OPTIONAL_DATA_FILES)},
    }


def _extract_symbols(required: Mapping[str, Any], optional: Mapping[str, Any]) -> set[str]:
    symbols: set[str] = set()
    for payload in list(required.values()) + list(optional.values()):
        symbols.update(_walk_symbols(payload))
    return {symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()}


def _walk_symbols(payload: Any) -> set[str]:
    symbols: set[str] = set()
    if isinstance(payload, Mapping):
        symbol = payload.get("symbol")
        if isinstance(symbol, str) and symbol.strip():
            symbols.add(symbol.upper())
        for key, value in payload.items():
            if _looks_like_symbol_key(key) and isinstance(value, Mapping):
                symbols.add(str(key).upper())
            if isinstance(value, (Mapping, list, tuple)):
                symbols.update(_walk_symbols(value))
    elif isinstance(payload, (list, tuple)):
        for row in payload:
            symbols.update(_walk_symbols(row))
    return symbols


def _looks_like_symbol_key(key: Any) -> bool:
    text = str(key).strip().upper()
    return 1 <= len(text) <= 8 and text.replace(".", "").replace("-", "").isalnum()


def _build_symbol_position_intelligence(
    symbol: str,
    required: Mapping[str, Any],
    optional: Mapping[str, Any],
) -> SymbolPositionIntelligence:
    opportunity = _find_symbol_record(required.get("opportunity_quality"), symbol)
    strategy = _extract_strategy(symbol, required.get("strategy_assignments"))
    allocation_pct = _extract_allocation_pct(symbol, required.get("portfolio_allocations"))
    lifecycle = _find_symbol_record(required.get("trade_lifecycle_report"), symbol)
    profit = _find_symbol_record(required.get("profit_protection_report"), symbol)
    reentry = _find_symbol_record(required.get("reentry_report"), symbol)
    exit_review = _find_symbol_record(required.get("exit_review_report"), symbol)

    opportunity_score = _extract_float(opportunity, ("opportunity_quality_score", "quality_score", "score"), 0.0)
    opportunity_classification = _extract_text(opportunity, ("opportunity_classification", "classification"), "UNKNOWN")
    entry_gate = _extract_text(opportunity, ("entry_gate_status", "entry_classification"), "UNKNOWN")
    lifecycle_state = _extract_text(opportunity, ("lifecycle_state",), "UNKNOWN")
    if lifecycle_state == "UNKNOWN":
        lifecycle_state = _extract_text(lifecycle, ("recommended_state", "lifecycle_state", "current_state"), "UNKNOWN")

    profit_state = _extract_text(profit, ("suggested_review_action", "protection_zone", "outcome"), "NONE")
    reentry_state = _extract_text(reentry, ("suggested_review_action", "reentry_state", "outcome"), "NONE")
    exit_state = _extract_text(exit_review, ("suggested_review_action", "exit_review_state", "outcome"), "NONE")

    decision_state = _determine_decision_state(
        opportunity_classification=opportunity_classification,
        entry_gate_status=entry_gate,
        lifecycle_state=lifecycle_state,
        allocation_pct=allocation_pct,
        strategy_assignment=strategy,
        lifecycle_record=lifecycle,
        profit_record=profit,
        reentry_record=reentry,
        exit_record=exit_review,
        opportunity_record=opportunity,
    )

    return SymbolPositionIntelligence(
        symbol=symbol.upper(),
        decision_state=decision_state,
        strategy_assignment=strategy,
        opportunity_quality_score=round(opportunity_score, 4),
        opportunity_classification=opportunity_classification,
        entry_gate_status=entry_gate,
        lifecycle_state=lifecycle_state,
        allocation_pct=round(allocation_pct, 4),
        profit_protection_state=profit_state,
        reentry_state=reentry_state,
        exit_review_state=exit_state,
        final_recommendation=decision_state,
        summary=_decision_summary(decision_state),
    )


def _determine_decision_state(
    *,
    opportunity_classification: str,
    entry_gate_status: str,
    lifecycle_state: str,
    allocation_pct: float,
    strategy_assignment: str,
    lifecycle_record: Any,
    profit_record: Any,
    reentry_record: Any,
    exit_record: Any,
    opportunity_record: Any,
) -> str:
    lifecycle_upper = lifecycle_state.upper()
    entry_upper = entry_gate_status.upper()
    classification_upper = opportunity_classification.upper()

    if _exit_review_required(exit_record) or lifecycle_upper in {"EXIT_REVIEW", "REVIEW_REQUIRED"}:
        return "REVIEW_EXIT"

    if _profit_review_required(profit_record) or lifecycle_upper in {"PROFIT_PROTECTION", "PROFIT_PROTECTION_REVIEW"}:
        return "REVIEW_PROFIT_PROTECTION"

    final_status = _extract_text(opportunity_record, ("final_opportunity_status",), "")
    if _reentry_ready(reentry_record) or final_status in {"HIGH_QUALITY_REENTRY_READY", "REENTRY_READY"}:
        return "REVIEW_REENTRY"

    if final_status in {"ELITE_ENTRY_READY", "HIGH_QUALITY_ENTRY_READY"}:
        return "REVIEW_ENTRY"

    if allocation_pct > 0 or lifecycle_upper in {"ACTIVE_POSITION", "PAPER_POSITION"}:
        return "HOLD_ACTIVE_POSITION"

    if final_status in {"HIGH_QUALITY_REENTRY_WAIT", "REENTRY_WAIT"} or lifecycle_upper == "REENTRY_WATCH":
        return "WAIT_FOR_REENTRY"

    if classification_upper in {"ELITE_OPPORTUNITY", "HIGH_OPPORTUNITY"} and entry_upper != "ENTRY_FAVORABLE":
        return "WAIT_FOR_ENTRY"

    if classification_upper == "AVOID_FOR_NOW":
        return "REMOVE_FROM_ACTIVE_REVIEW"

    if strategy_assignment == "UNKNOWN" and classification_upper == "UNKNOWN":
        return "NEEDS_MANUAL_REVIEW"

    if classification_upper in {"MODERATE_OPPORTUNITY", "LOW_OPPORTUNITY", "UNKNOWN"}:
        return "MONITOR_WATCHLIST"

    return "NO_ACTION_REQUIRED"


def _exit_review_required(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    values = {str(record.get(key, "")).lower() for key in ("outcome", "suggested_review_action", "exit_review_state", "recommended_state")}
    return any(value and value not in {"continue_holding", "monitor", "none", ""} for value in values)


def _profit_review_required(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    values = {str(record.get(key, "")).lower() for key in ("suggested_review_action", "protection_zone", "outcome")}
    return any(value in {"standard_profit_review", "strong_trend_review", "giveback_review", "standard_protection_zone", "strong_trend_zone", "giveback_review_zone"} for value in values)


def _reentry_ready(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    values = {str(record.get(key, "")).lower() for key in ("suggested_review_action", "reentry_state", "outcome", "recommended_state")}
    return any(value in {"review_reentry", "prepare_reentry_review", "reentry_ready", "ready", "entry_ready"} for value in values)


def _generate_position_intelligence_risk_flags(
    rows: list[SymbolPositionIntelligence],
    warnings: list[PositionIntelligenceWarning],
) -> list[PositionIntelligenceRiskFlag]:
    flags: list[PositionIntelligenceRiskFlag] = []
    for row in rows:
        if row.decision_state == "REVIEW_EXIT":
            flags.append(PositionIntelligenceRiskFlag("exit_review_required", row.symbol, "critical", "Exit review is the highest-priority paper review state.", GENERATED_BY))
        elif row.decision_state == "REVIEW_PROFIT_PROTECTION":
            flags.append(PositionIntelligenceRiskFlag("profit_protection_review_required", row.symbol, "high", "Profit protection review is active for this paper position.", GENERATED_BY))
        elif row.decision_state == "REVIEW_REENTRY":
            flags.append(PositionIntelligenceRiskFlag("reentry_ready", row.symbol, "high", "Re-entry review is ready from existing outputs.", GENERATED_BY))
        elif row.decision_state == "REVIEW_ENTRY":
            flags.append(PositionIntelligenceRiskFlag("entry_ready", row.symbol, "medium", "Entry review is ready from existing outputs.", GENERATED_BY))
        elif row.decision_state == "WAIT_FOR_ENTRY":
            flags.append(PositionIntelligenceRiskFlag("high_quality_waiting_for_entry", row.symbol, "medium", "High-quality opportunity is waiting on entry timing.", GENERATED_BY))
        elif row.decision_state == "NEEDS_MANUAL_REVIEW":
            flags.append(PositionIntelligenceRiskFlag("manual_review_required", row.symbol, "medium", "Existing context is insufficient for a clean daily state.", GENERATED_BY))
        if row.strategy_assignment == "Strategy B" and row.decision_state == "REVIEW_EXIT":
            flags.append(PositionIntelligenceRiskFlag("strategy_b_capital_preservation", row.symbol, "critical", "Strategy B capital-preservation review is active.", GENERATED_BY))
    if warnings:
        flags.append(PositionIntelligenceRiskFlag("missing_optional_context", None, "low", "One or more optional inputs are missing or unavailable.", GENERATED_BY))
    return flags


def _generate_position_intelligence_review_actions(
    rows: list[SymbolPositionIntelligence],
    flags: list[PositionIntelligenceRiskFlag],
) -> list[PositionIntelligenceReviewAction]:
    action_map = {
        "REVIEW_EXIT": ("REVIEW_EXIT", "critical", "Review exit state from existing paper reports."),
        "REVIEW_PROFIT_PROTECTION": ("REVIEW_PROFIT_PROTECTION", "high", "Review profit protection state from existing paper reports."),
        "REVIEW_REENTRY": ("REVIEW_REENTRY", "high", "Review re-entry state from existing paper reports."),
        "REVIEW_ENTRY": ("REVIEW_ENTRY", "high", "Review entry state from existing paper reports."),
        "HOLD_ACTIVE_POSITION": ("REVIEW_ACTIVE_POSITION", "medium", "Review active paper position context."),
        "WAIT_FOR_ENTRY": ("MONITOR_WAIT_FOR_ENTRY", "medium", "Monitor until entry timing improves."),
        "WAIT_FOR_REENTRY": ("MONITOR_WAIT_FOR_REENTRY", "medium", "Monitor re-entry watch until timing improves."),
        "MONITOR_WATCHLIST": ("MONITOR_WATCHLIST", "low", "Monitor watchlist context."),
        "NEEDS_MANUAL_REVIEW": ("REVIEW_MANUAL_CONTEXT", "medium", "Review missing or conflicting context."),
        "REMOVE_FROM_ACTIVE_REVIEW": ("REMOVE_FROM_ACTIVE_REVIEW", "medium", "Review whether this symbol should remain in active review."),
        "NO_ACTION_REQUIRED": ("NO_ACTION_REQUIRED", "low", "No position-intelligence review action is required."),
    }
    actions = []
    for row in rows:
        action_type, priority, message = action_map.get(row.decision_state, action_map["NEEDS_MANUAL_REVIEW"])
        actions.append(PositionIntelligenceReviewAction(action_type, row.symbol, priority, message, GENERATED_BY))
    if not actions and not flags:
        actions.append(PositionIntelligenceReviewAction("NO_ACTION_REQUIRED", None, "low", "No position-intelligence review action is required.", GENERATED_BY))
    return sorted(actions, key=lambda action: (_priority_rank(action.priority), action.symbol or "", action.action_type))


def _calculate_summary_metrics(
    rows: list[SymbolPositionIntelligence],
    risk_flags: list[PositionIntelligenceRiskFlag],
    actions: list[PositionIntelligenceReviewAction],
    warnings: list[PositionIntelligenceWarning],
) -> PositionIntelligenceSummaryMetrics:
    counts = Counter(row.decision_state for row in rows)
    strategy_counts = Counter(row.strategy_assignment for row in rows)
    return PositionIntelligenceSummaryMetrics(
        paper_trade_mode=PAPER_TRADE_MODE,
        symbols_analyzed=len(rows),
        monitor_watchlist_count=counts["MONITOR_WATCHLIST"],
        review_entry_count=counts["REVIEW_ENTRY"],
        review_reentry_count=counts["REVIEW_REENTRY"],
        hold_active_position_count=counts["HOLD_ACTIVE_POSITION"],
        review_profit_protection_count=counts["REVIEW_PROFIT_PROTECTION"],
        review_exit_count=counts["REVIEW_EXIT"],
        wait_for_entry_count=counts["WAIT_FOR_ENTRY"],
        wait_for_reentry_count=counts["WAIT_FOR_REENTRY"],
        remove_from_active_review_count=counts["REMOVE_FROM_ACTIVE_REVIEW"],
        manual_review_count=counts["NEEDS_MANUAL_REVIEW"],
        no_action_required_count=counts["NO_ACTION_REQUIRED"],
        strategy_a_count=strategy_counts["Strategy A"],
        strategy_b_count=strategy_counts["Strategy B"],
        risk_flag_count=len(risk_flags),
        review_action_count=len(actions),
        warning_count=len(warnings),
    )


def _extract_strategy(symbol: str, payload: Any) -> str:
    record = _find_symbol_record(payload, symbol)
    value = _extract_text(record, ("assigned_strategy", "strategy", "active_strategy", "recommended_strategy"), "UNKNOWN")
    if value.upper() in {"A", "STRATEGY_A"}:
        return "Strategy A"
    if value.upper() in {"B", "STRATEGY_B"}:
        return "Strategy B"
    if value in {"Strategy A", "Strategy B"}:
        return value
    return value if value != "UNKNOWN" else "UNKNOWN"


def _extract_allocation_pct(symbol: str, payload: Any) -> float:
    record = _find_symbol_record(payload, symbol)
    return _extract_float(record, ("allocation_pct", "allocation_percent", "target_allocation_pct", "current_allocation_pct", "weight_pct"), 0.0)


def _find_symbol_record(payload: Any, symbol: str) -> Any:
    symbol_upper = symbol.upper()
    if isinstance(payload, Mapping):
        if str(payload.get("symbol", "")).upper() == symbol_upper:
            return payload
        for key, value in payload.items():
            if str(key).upper() == symbol_upper and isinstance(value, Mapping):
                return value
        for key in ("symbol_position_intelligence", "symbol_opportunity_quality", "reviews", "rows", "allocations", "positions", "holdings", "data", "items", "results"):
            found = _find_symbol_record(payload.get(key), symbol)
            if found is not None:
                return found
        for value in payload.values():
            if isinstance(value, (Mapping, list, tuple)):
                found = _find_symbol_record(value, symbol)
                if found is not None:
                    return found
    elif isinstance(payload, (list, tuple)):
        for row in payload:
            found = _find_symbol_record(row, symbol)
            if found is not None:
                return found
    return None


def _extract_text(record: Any, keys: Iterable[str], default: str) -> str:
    if not isinstance(record, Mapping):
        return default
    lower = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        value = lower.get(key.lower())
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _extract_float(record: Any, keys: Iterable[str], default: float) -> float:
    if not isinstance(record, Mapping):
        return default
    lower = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        parsed = _to_float(lower.get(key.lower()))
        if parsed is not None:
            return parsed
    return default


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "").replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _decision_summary(decision_state: str) -> str:
    return {
        "MONITOR_WATCHLIST": "Symbol remains in daily watchlist monitoring.",
        "REVIEW_ENTRY": "Existing outputs indicate entry review is ready.",
        "REVIEW_REENTRY": "Existing outputs indicate re-entry review is ready.",
        "HOLD_ACTIVE_POSITION": "Active paper position remains under daily review.",
        "REVIEW_PROFIT_PROTECTION": "Profit protection review is active.",
        "REVIEW_EXIT": "Exit review is active.",
        "WAIT_FOR_ENTRY": "High-quality opportunity is waiting for entry timing.",
        "WAIT_FOR_REENTRY": "Re-entry watch is waiting for timing confirmation.",
        "REMOVE_FROM_ACTIVE_REVIEW": "Symbol may no longer belong in active review.",
        "NEEDS_MANUAL_REVIEW": "Symbol has missing or conflicting context that needs review.",
        "NO_ACTION_REQUIRED": "No action is required from available context.",
    }.get(decision_state, "Position intelligence state is unknown.")


def _append_decision_section(
    lines: list[str],
    heading: str,
    report: PositionIntelligenceReport,
    decision_state: str,
) -> None:
    lines.extend(["", heading, ""])
    matches = [row for row in report.symbol_position_intelligence if row.decision_state == decision_state]
    if not matches:
        lines.append("None.")
        return
    for row in matches:
        lines.append(f"- {row.symbol}: {row.summary}")


def _priority_rank(priority: str) -> int:
    return PRIORITY_ORDER.get(str(priority).lower(), 99)


def main() -> None:
    report = build_and_write_position_intelligence_report()
    print(format_console_summary(report))


if __name__ == "__main__":
    main()
