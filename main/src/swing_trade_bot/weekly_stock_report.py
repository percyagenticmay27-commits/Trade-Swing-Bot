"""Paper-only weekly stock review built from existing project outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

MODULE_NAME = "weekly_stock_report"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class WeeklyStockSignal:
    symbol: str
    signal: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class WeeklyStockRow:
    symbol: str
    active_strategy: str
    recommended_strategy: str
    weekly_status: str
    weekly_return: float
    total_return: float
    strategy_a_return: float
    strategy_b_return: float
    win_rate: float
    profit_factor: float
    current_allocation: float
    confidence_level: str
    suggested_action: str
    risk_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeeklyStockReport:
    module_name: str
    module_version: str
    schema_version: str
    paper_trade_mode: bool
    as_of_date: str
    summary: Mapping[str, int | float]
    rows: tuple[WeeklyStockRow, ...]
    signals: tuple[WeeklyStockSignal, ...]
    watchlist_promotions: tuple[str, ...]
    watchlist_demotions: tuple[str, ...]
    confidence_upgrades: tuple[str, ...]
    confidence_downgrades: tuple[str, ...]
    strategy_changes: tuple[str, ...]
    earnings_risks: tuple[str, ...]
    sgov_allocation: float
    warnings: tuple[str, ...]
    source_files: Mapping[str, bool]


def build_weekly_stock_report(
    stock_performance_path: Path,
    portfolio_allocations_path: Path,
    *,
    portfolio_manager_report_path: Path | None = None,
    confidence_report_path: Path | None = None,
    strategy_recommendations_path: Path | None = None,
    watchlist_report_path: Path | None = None,
    earnings_report_path: Path | None = None,
    as_of: date | None = None,
    paper_trade_mode: bool = True,
) -> WeeklyStockReport:
    if not paper_trade_mode:
        raise ValueError("Weekly stock reporting requires paper_trade_mode=True")
    required = {
        "stock_performance_report.json": Path(stock_performance_path),
        "portfolio_allocations.json": Path(portfolio_allocations_path),
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required input(s): " + ", ".join(missing))

    optional = {
        "portfolio_manager_report": portfolio_manager_report_path,
        "confidence_report": confidence_report_path,
        "strategy_recommendations": strategy_recommendations_path,
        "watchlist_report": watchlist_report_path,
        "earnings_report": earnings_report_path,
    }
    source_files: dict[str, bool] = {name: True for name in required}
    warnings: list[str] = []
    for name, raw_path in optional.items():
        present = raw_path is not None and Path(raw_path).is_file()
        source_files[name] = present
        if not present:
            warnings.append(f"Missing optional input: {name}")

    performance_payload = _read_json(required["stock_performance_report.json"])
    performance_rows = _index(_rows(performance_payload))
    allocation_payload = _read_json(required["portfolio_allocations.json"])
    allocation_rows = _index(_rows(allocation_payload, ("allocations", "rows")))
    manager = _optional_index(portfolio_manager_report_path)
    confidence = _optional_index(confidence_report_path)
    strategies = _optional_index(strategy_recommendations_path)
    watchlist_rows = _optional_rows(watchlist_report_path)
    earnings_rows = _optional_rows(earnings_report_path)
    review_date = as_of or date.today()

    symbols = sorted(set(performance_rows) | set(allocation_rows) | set(manager) | set(confidence) | set(strategies))
    report_rows: list[WeeklyStockRow] = []
    signals: list[WeeklyStockSignal] = []
    confidence_upgrades: list[str] = []
    confidence_downgrades: list[str] = []
    strategy_changes: list[str] = []

    for symbol in symbols:
        perf = performance_rows.get(symbol, {})
        allocation = allocation_rows.get(symbol, {})
        manager_row = manager.get(symbol, {})
        confidence_row = confidence.get(symbol, {})
        strategy_row = strategies.get(symbol, {})
        weekly_return = _number(perf, "weekly_return", "week_return", "weekly_return_percent")
        total_return = _number(perf, "total_return", "return_percent", "total_return_percent")
        status = "WINNER" if weekly_return > 0 else "LOSER" if weekly_return < 0 else "FLAT"
        active = _text(strategy_row, "active_strategy", default=_text(perf, "active_strategy"))
        recommended = _text(strategy_row, "recommended_strategy", default=_text(perf, "recommended_strategy", default=active))
        risk_flags: list[str] = []

        def add_signal(signal: str, severity: str, message: str) -> None:
            signals.append(WeeklyStockSignal(symbol, signal, severity, message))
            risk_flags.append(signal)

        if weekly_return > 0:
            add_signal("WEEKLY_WINNER", "INFO", f"{symbol} gained {weekly_return:.2f}% this week.")
        elif weekly_return < 0:
            add_signal("WEEKLY_LOSER", "WATCH", f"{symbol} lost {abs(weekly_return):.2f}% this week.")
        if 18.0 <= total_return < 20.0:
            add_signal("APPROACHING_20_TARGET", "WATCH", f"{symbol} is approaching the +20% target.")
        if 28.0 <= total_return < 30.0:
            add_signal("APPROACHING_30_TARGET", "WATCH", f"{symbol} is approaching the +30% target.")
        if total_return >= 20.0:
            add_signal("TRAILING_STOP_5_REVIEW", "REVIEW", f"Review a 5% paper trailing stop for {symbol}.")
        if total_return >= 30.0:
            add_signal("TRAILING_STOP_10_REVIEW", "REVIEW", f"Review a 10% paper trailing stop for {symbol}.")
        if total_return <= -20.0:
            add_signal("LOSS_PROTECTION_REVIEW", "HIGH", f"{symbol} reached the -20% loss-protection review level.")
        elif total_return <= -15.0:
            add_signal("LOSS_PROTECTION_WARNING", "HIGH", f"{symbol} is approaching the -20% loss-protection level.")

        confidence_change = _text(confidence_row, "change", "confidence_change", "direction").upper()
        if confidence_change in {"UP", "UPGRADE", "UPGRADED", "PROMOTED"}:
            confidence_upgrades.append(symbol)
        elif confidence_change in {"DOWN", "DOWNGRADE", "DOWNGRADED", "DEMOTED"}:
            confidence_downgrades.append(symbol)
        if active and recommended and _normalize(active) != _normalize(recommended):
            strategy_changes.append(f"{symbol}: {active} → {recommended}")

        suggested = _text(manager_row, "suggested_action", "action")
        if not suggested:
            suggested = "Review risk flags before the next paper cycle." if risk_flags else "Continue paper monitoring."
        report_rows.append(
            WeeklyStockRow(
                symbol=symbol,
                active_strategy=active,
                recommended_strategy=recommended,
                weekly_status=status,
                weekly_return=weekly_return,
                total_return=total_return,
                strategy_a_return=_number(perf, "strategy_a_return"),
                strategy_b_return=_number(perf, "strategy_b_return"),
                win_rate=_number(perf, "win_rate", "active_win_rate"),
                profit_factor=_number(perf, "profit_factor", "active_profit_factor"),
                current_allocation=_number(manager_row, "current_allocation", "allocation_percent", default=_number(allocation, "allocation_percent")),
                confidence_level=_text(confidence_row, "confidence_level", "confidence", default=_text(perf, "confidence_level")),
                suggested_action=suggested,
                risk_flags=tuple(risk_flags),
            )
        )

    promotions, demotions = _watchlist_changes(watchlist_rows)
    earnings_risks = _earnings_within(earnings_rows, review_date, days=7)
    for symbol in earnings_risks:
        signals.append(WeeklyStockSignal(symbol, "EARNINGS_EXIT_REVIEW", "HIGH", "Earnings event falls within the next seven days."))
    sgov = _sgov_allocation(allocation_payload, allocation_rows)
    summary = {
        "symbols_reviewed": len(report_rows),
        "weekly_winners": sum(row.weekly_status == "WINNER" for row in report_rows),
        "weekly_losers": sum(row.weekly_status == "LOSER" for row in report_rows),
        "approaching_20_target": sum(signal.signal == "APPROACHING_20_TARGET" for signal in signals),
        "approaching_30_target": sum(signal.signal == "APPROACHING_30_TARGET" for signal in signals),
        "trailing_stop_reviews": sum(signal.signal.startswith("TRAILING_STOP") for signal in signals),
        "loss_protection_warnings": sum(signal.signal.startswith("LOSS_PROTECTION") for signal in signals),
        "earnings_risks": len(earnings_risks),
        "confidence_upgrades": len(confidence_upgrades),
        "confidence_downgrades": len(confidence_downgrades),
        "strategy_changes": len(strategy_changes),
        "watchlist_promotions": len(promotions),
        "watchlist_demotions": len(demotions),
    }
    return WeeklyStockReport(
        module_name=MODULE_NAME,
        module_version=MODULE_VERSION,
        schema_version=SCHEMA_VERSION,
        paper_trade_mode=True,
        as_of_date=review_date.isoformat(),
        summary=summary,
        rows=tuple(report_rows),
        signals=tuple(signals),
        watchlist_promotions=tuple(promotions),
        watchlist_demotions=tuple(demotions),
        confidence_upgrades=tuple(confidence_upgrades),
        confidence_downgrades=tuple(confidence_downgrades),
        strategy_changes=tuple(strategy_changes),
        earnings_risks=tuple(earnings_risks),
        sgov_allocation=sgov,
        warnings=tuple(warnings),
        source_files=source_files,
    )


def write_weekly_stock_report(output_dir: Path, report: WeeklyStockReport) -> tuple[Path, Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "weekly_stock_report.csv"
    json_path = output_dir / "weekly_stock_report.json"
    md_path = output_dir / "weekly_stock_report.md"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        fieldnames = list(WeeklyStockRow.__dataclass_fields__)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.rows:
            payload = asdict(row)
            payload["risk_flags"] = "|".join(row.risk_flags)
            writer.writerow(payload)
    json_path.write_text(json.dumps(asdict(report), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    md_path.write_text(format_weekly_stock_markdown(report) + "\n", encoding="utf-8")
    return csv_path, json_path, md_path


def build_and_write_weekly_stock_report(
    stock_performance_path: Path,
    portfolio_allocations_path: Path,
    output_dir: Path,
    **kwargs: Any,
) -> WeeklyStockReport:
    report = build_weekly_stock_report(stock_performance_path, portfolio_allocations_path, **kwargs)
    write_weekly_stock_report(output_dir, report)
    return report


def format_weekly_stock_markdown(report: WeeklyStockReport) -> str:
    summary = report.summary
    lines = [
        "# Weekly Stock Report",
        "",
        f"As of: {report.as_of_date}",
        "Paper-only: true",
        "",
        "## Executive Summary",
        "",
        f"- Weekly Winners: {summary['weekly_winners']}",
        f"- Weekly Losers: {summary['weekly_losers']}",
        f"- Approaching +20% Targets: {summary['approaching_20_target']}",
        f"- Approaching +30% Targets: {summary['approaching_30_target']}",
        f"- Loss Protection Warnings: {summary['loss_protection_warnings']}",
        f"- Earnings Risks: {summary['earnings_risks']}",
        f"- SGOV Allocation: {report.sgov_allocation:.2f}%",
    ]
    sections = [
        ("Weekly Winners and Losers", [f"{row.symbol}: {row.weekly_status} ({row.weekly_return:.2f}%)" for row in report.rows]),
        ("Profit Target Watch", _signal_lines(report, {"APPROACHING_20_TARGET", "APPROACHING_30_TARGET"})),
        ("Trailing Stop Review", _signal_lines(report, {"TRAILING_STOP_5_REVIEW", "TRAILING_STOP_10_REVIEW"})),
        ("Loss Protection Warnings", _signal_lines(report, {"LOSS_PROTECTION_WARNING", "LOSS_PROTECTION_REVIEW"})),
        ("Confidence Changes", [*(f"Upgrade: {symbol}" for symbol in report.confidence_upgrades), *(f"Downgrade: {symbol}" for symbol in report.confidence_downgrades)]),
        ("Strategy A vs B Changes", list(report.strategy_changes)),
        ("Watchlist Changes", [*(f"Promotion: {symbol}" for symbol in report.watchlist_promotions), *(f"Demotion: {symbol}" for symbol in report.watchlist_demotions)]),
        ("Earnings Risk Next Week", [f"{symbol}: EARNINGS_EXIT_REVIEW" for symbol in report.earnings_risks]),
        ("Suggested Actions for Next Week", [f"{row.symbol}: {row.suggested_action}" for row in report.rows]),
        ("Warnings", list(report.warnings)),
    ]
    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {item}" for item in items) if items else lines.append("- None")
    return "\n".join(lines)


def _signal_lines(report: WeeklyStockReport, names: set[str]) -> list[str]:
    return [f"{signal.symbol}: {signal.message}" for signal in report.signals if signal.signal in names]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON input {path}: {exc}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as input_file:
            return list(csv.DictReader(input_file))
    except (OSError, csv.Error) as exc:
        raise ValueError(f"Invalid CSV input {path}: {exc}") from exc


def _rows(payload: Any, keys: Sequence[str] = ("rows", "results")) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
    return []


def _load_rows(path: Path) -> list[Mapping[str, Any]]:
    return _read_csv(path) if path.suffix.lower() == ".csv" else _rows(_read_json(path), ("rows", "results", "events", "earnings", "watchlist"))


def _optional_rows(path: Path | None) -> list[Mapping[str, Any]]:
    return _load_rows(Path(path)) if path is not None and Path(path).is_file() else []


def _optional_index(path: Path | None) -> dict[str, Mapping[str, Any]]:
    return _index(_optional_rows(path))


def _index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol", row.get("ticker", row.get("underlying_symbol", "")))).strip().upper()
        if symbol:
            result[symbol] = row
    return result


def _get(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    value = _get(row, *names)
    return default if value is None else str(value).strip()


def _number(row: Mapping[str, Any], *names: str, default: float = 0.0) -> float:
    value = _get(row, *names)
    if value is None or str(value).strip() == "":
        return default
    try:
        number = float(str(value).replace("%", "").replace(",", "").strip())
    except ValueError:
        return default
    return number if math.isfinite(number) else default


def _normalize(text: str) -> str:
    return text.replace("_", " ").replace("-", " ").strip().upper()


def _watchlist_changes(rows: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    promotions: list[str] = []
    demotions: list[str] = []
    for row in rows:
        symbol = _text(row, "symbol", "ticker", "underlying_symbol").upper()
        change = _text(row, "change", "watchlist_change", "action", "status_change").upper()
        if symbol and change in {"PROMOTE", "PROMOTED", "PROMOTION", "ADD", "ADDED"}:
            promotions.append(symbol)
        elif symbol and change in {"DEMOTE", "DEMOTED", "DEMOTION", "REMOVE", "REMOVED"}:
            demotions.append(symbol)
    return promotions, demotions


def _earnings_within(rows: Sequence[Mapping[str, Any]], as_of: date, *, days: int) -> list[str]:
    result: list[str] = []
    end = as_of + timedelta(days=days)
    for row in rows:
        symbol = _text(row, "symbol", "ticker", "underlying_symbol").upper()
        raw = _text(row, "earnings_date", "event_date", "date")
        try:
            event_date = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if symbol and as_of <= event_date <= end:
            result.append(symbol)
    return result


def _sgov_allocation(payload: Any, indexed: Mapping[str, Mapping[str, Any]]) -> float:
    if isinstance(payload, Mapping):
        direct = _number(payload, "sgov_allocation", "sgov_allocation_percent")
        if direct:
            return direct
    return _number(indexed.get("SGOV", {}), "allocation_percent", "target_allocation", "current_allocation")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper-only weekly stock report")
    parser.add_argument("--stock-performance", type=Path, default=Path("results/stock_performance_report.json"))
    parser.add_argument("--portfolio-allocations", type=Path, default=Path("results/portfolio_allocations.json"))
    parser.add_argument("--portfolio-manager-report", type=Path)
    parser.add_argument("--confidence-report", type=Path)
    parser.add_argument("--strategy-recommendations", type=Path)
    parser.add_argument("--watchlist-report", type=Path)
    parser.add_argument("--earnings-report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    report = build_and_write_weekly_stock_report(
        args.stock_performance,
        args.portfolio_allocations,
        args.output_dir,
        portfolio_manager_report_path=args.portfolio_manager_report,
        confidence_report_path=args.confidence_report,
        strategy_recommendations_path=args.strategy_recommendations,
        watchlist_report_path=args.watchlist_report,
        earnings_report_path=args.earnings_report,
        as_of=args.as_of,
    )
    print(format_weekly_stock_markdown(report))


if __name__ == "__main__":
    main()
