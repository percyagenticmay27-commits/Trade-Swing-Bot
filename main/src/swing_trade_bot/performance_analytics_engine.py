"""Paper-only performance analytics built from authoritative ledger evidence.

Consumes Paper Portfolio Manager and Trade History Manager outputs. It never
connects to a broker, places orders, moves capital, or fabricates unavailable
statistics.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class StrategyPerformance:
    strategy_name: str
    closed_trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    breakeven_trade_count: int
    win_rate_percent: float | None
    realized_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_trade_pnl: float | None
    average_holding_days: float | None


@dataclass(frozen=True, slots=True)
class PerformanceAnalyticsReport:
    generated_at: str
    account_capital: float
    portfolio_value: float
    cash_balance: float
    invested_capital: float
    positions_market_value: float
    open_position_count: int
    total_trade_events: int
    closed_trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    breakeven_trade_count: int
    win_rate_percent: float | None
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    portfolio_return_percent: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_gain: float | None
    average_loss: float | None
    average_trade_pnl: float | None
    largest_win: float | None
    largest_loss: float | None
    average_holding_days: float | None
    max_drawdown_percent: float | None
    strategy_performance: tuple[StrategyPerformance, ...]
    evidence_status: str
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    capital_movement_enabled: bool = False
    direct_database_writes: bool = False
    schema_version: str = SCHEMA_VERSION


def build_performance_analytics_report(
    *,
    portfolio_summary_path: Path,
    closed_positions_path: Path,
    trade_history_summary_path: Path,
) -> PerformanceAnalyticsReport:
    """Build transparent paper performance statistics from managed evidence."""
    portfolio = _load_json(portfolio_summary_path)
    closed_payload = _load_json(closed_positions_path)
    history = _load_json(trade_history_summary_path)

    _require_paper_safe(portfolio, portfolio_summary_path)
    _require_paper_safe(closed_payload, closed_positions_path)
    _require_paper_safe(history, trade_history_summary_path)

    closed_rows = closed_payload.get("closed_trades")
    if not isinstance(closed_rows, list):
        raise ValueError("closed_positions.json must contain a closed_trades list")
    closed = tuple(_normalize_closed_trade(row) for row in closed_rows)

    account_capital = _positive(portfolio.get("account_capital"), "account_capital")
    portfolio_value = _nonnegative(portfolio.get("portfolio_value"), "portfolio_value")
    cash_balance = _nonnegative(portfolio.get("cash_balance"), "cash_balance")
    invested_capital = _nonnegative(portfolio.get("invested_capital"), "invested_capital")
    positions_market_value = _nonnegative(
        portfolio.get("positions_market_value"), "positions_market_value"
    )
    unrealized_pnl = _finite(portfolio.get("unrealized_pnl"), "unrealized_pnl")
    open_position_count = _nonnegative_int(portfolio.get("position_count"), "position_count")
    total_trade_events = _nonnegative_int(
        history.get("total_trade_events"), "total_trade_events"
    )

    realized_pnl = round(sum(item["realized_pnl"] for item in closed), 2)
    if abs(realized_pnl - _finite(history.get("realized_pnl", 0.0), "history.realized_pnl")) > 0.02:
        raise ValueError("closed-position realized P/L disagrees with trade-history summary")

    wins = [item for item in closed if item["realized_pnl"] > 0]
    losses = [item for item in closed if item["realized_pnl"] < 0]
    breakeven = [item for item in closed if item["realized_pnl"] == 0]
    decided = len(wins) + len(losses)
    win_rate = round(len(wins) / decided * 100.0, 6) if decided else None
    gross_profit = round(sum(item["realized_pnl"] for item in wins), 2)
    gross_loss = round(abs(sum(item["realized_pnl"] for item in losses)), 2)
    profit_factor = round(gross_profit / gross_loss, 6) if gross_loss > 0 else None
    average_gain = round(gross_profit / len(wins), 2) if wins else None
    average_loss = round(-gross_loss / len(losses), 2) if losses else None
    average_trade = round(realized_pnl / len(closed), 2) if closed else None
    largest_win = round(max((item["realized_pnl"] for item in wins), default=0.0), 2) if wins else None
    largest_loss = round(min((item["realized_pnl"] for item in losses), default=0.0), 2) if losses else None
    average_holding = (
        round(sum(item["holding_days"] for item in closed) / len(closed), 2)
        if closed
        else None
    )
    total_pnl = round(realized_pnl + unrealized_pnl, 2)
    calculated_value = round(account_capital + total_pnl, 2)
    if abs(calculated_value - portfolio_value) > 0.02:
        raise ValueError("portfolio value does not reconcile to capital plus total P/L")
    return_percent = round(total_pnl / account_capital * 100.0, 6)

    warnings: list[str] = []
    if not closed:
        warnings.append("No closed paper trades are available; win/loss analytics are not reportable.")
    if gross_loss == 0:
        warnings.append("Profit factor is not reportable until at least one losing closed trade exists.")
    warnings.append(
        "Max drawdown is not reportable because a dated portfolio equity curve is not yet available."
    )

    strategies = _build_strategy_performance(closed)
    evidence_status = "AVAILABLE" if closed else "PARTIAL"

    return PerformanceAnalyticsReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        account_capital=round(account_capital, 2),
        portfolio_value=round(portfolio_value, 2),
        cash_balance=round(cash_balance, 2),
        invested_capital=round(invested_capital, 2),
        positions_market_value=round(positions_market_value, 2),
        open_position_count=open_position_count,
        total_trade_events=total_trade_events,
        closed_trade_count=len(closed),
        winning_trade_count=len(wins),
        losing_trade_count=len(losses),
        breakeven_trade_count=len(breakeven),
        win_rate_percent=win_rate,
        realized_pnl=realized_pnl,
        unrealized_pnl=round(unrealized_pnl, 2),
        total_pnl=total_pnl,
        portfolio_return_percent=return_percent,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        average_gain=average_gain,
        average_loss=average_loss,
        average_trade_pnl=average_trade,
        largest_win=largest_win,
        largest_loss=largest_loss,
        average_holding_days=average_holding,
        max_drawdown_percent=None,
        strategy_performance=strategies,
        evidence_status=evidence_status,
        warnings=tuple(warnings),
        errors=(),
    )


def write_performance_analytics_outputs(
    output_dir: Path, report: PerformanceAnalyticsReport
) -> tuple[Path, Path, Path]:
    """Atomically publish JSON, CSV, and Markdown performance evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "paper_performance.json"
    csv_path = output_dir / "paper_performance.csv"
    md_path = output_dir / "paper_performance.md"
    payload = asdict(report)
    payload["strategy_performance"] = [asdict(item) for item in report.strategy_performance]
    _atomic_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _atomic_text(csv_path, _render_csv(report))
    _atomic_text(md_path, _render_markdown(report))
    return json_path, csv_path, md_path


def build_and_write_performance_analytics_report(
    *,
    ledger_dir: Path = Path("results/paper_ledger"),
    output_dir: Path | None = None,
) -> PerformanceAnalyticsReport:
    report = build_performance_analytics_report(
        portfolio_summary_path=ledger_dir / "paper_portfolio_summary.json",
        closed_positions_path=ledger_dir / "closed_positions.json",
        trade_history_summary_path=ledger_dir / "trade_history_summary.json",
    )
    write_performance_analytics_outputs(output_dir or ledger_dir, report)
    return report


def _build_strategy_performance(
    closed: Sequence[dict[str, Any]],
) -> tuple[StrategyPerformance, ...]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in closed:
        grouped.setdefault(str(item["active_strategy"]), []).append(item)
    results: list[StrategyPerformance] = []
    for name in sorted(grouped):
        rows = grouped[name]
        wins = [item for item in rows if item["realized_pnl"] > 0]
        losses = [item for item in rows if item["realized_pnl"] < 0]
        breakeven = len(rows) - len(wins) - len(losses)
        decided = len(wins) + len(losses)
        gross_profit = round(sum(item["realized_pnl"] for item in wins), 2)
        gross_loss = round(abs(sum(item["realized_pnl"] for item in losses)), 2)
        realized = round(sum(item["realized_pnl"] for item in rows), 2)
        results.append(
            StrategyPerformance(
                strategy_name=name,
                closed_trade_count=len(rows),
                winning_trade_count=len(wins),
                losing_trade_count=len(losses),
                breakeven_trade_count=breakeven,
                win_rate_percent=round(len(wins) / decided * 100.0, 6) if decided else None,
                realized_pnl=realized,
                gross_profit=gross_profit,
                gross_loss=gross_loss,
                profit_factor=round(gross_profit / gross_loss, 6) if gross_loss else None,
                average_trade_pnl=round(realized / len(rows), 2) if rows else None,
                average_holding_days=round(
                    sum(item["holding_days"] for item in rows) / len(rows), 2
                ) if rows else None,
            )
        )
    return tuple(results)


def _normalize_closed_trade(row: Any) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("each closed trade must be a JSON object")
    return {
        "closed_trade_id": str(row.get("closed_trade_id", "")).strip(),
        "symbol": str(row.get("symbol", "")).strip().upper(),
        "realized_pnl": _finite(row.get("realized_pnl"), "closed_trade.realized_pnl"),
        "holding_days": _nonnegative_int(row.get("holding_days"), "closed_trade.holding_days"),
        "active_strategy": str(row.get("active_strategy", "Strategy A")),
    }


def _render_csv(report: PerformanceAnalyticsReport) -> str:
    rows = [
        ("account_capital", report.account_capital),
        ("portfolio_value", report.portfolio_value),
        ("open_position_count", report.open_position_count),
        ("closed_trade_count", report.closed_trade_count),
        ("win_rate_percent", report.win_rate_percent),
        ("realized_pnl", report.realized_pnl),
        ("unrealized_pnl", report.unrealized_pnl),
        ("total_pnl", report.total_pnl),
        ("portfolio_return_percent", report.portfolio_return_percent),
        ("profit_factor", report.profit_factor),
        ("max_drawdown_percent", report.max_drawdown_percent),
        ("evidence_status", report.evidence_status),
    ]
    output = ["metric,value"]
    for key, value in rows:
        output.append(f"{key},{'' if value is None else value}")
    return "\n".join(output) + "\n"


def _render_markdown(report: PerformanceAnalyticsReport) -> str:
    value = lambda item: "Not reportable" if item is None else str(item)
    lines = [
        "# Paper Performance Analytics",
        "",
        f"- Generated at: {report.generated_at}",
        f"- Evidence status: {report.evidence_status}",
        f"- Account capital: ${report.account_capital:,.2f}",
        f"- Portfolio value: ${report.portfolio_value:,.2f}",
        f"- Total P/L: ${report.total_pnl:,.2f}",
        f"- Portfolio return: {report.portfolio_return_percent:.4f}%",
        f"- Open positions: {report.open_position_count}",
        f"- Closed trades: {report.closed_trade_count}",
        f"- Win rate: {value(report.win_rate_percent)}",
        f"- Profit factor: {value(report.profit_factor)}",
        f"- Max drawdown: {value(report.max_drawdown_percent)}",
        "",
        "## Strategy Performance",
    ]
    if report.strategy_performance:
        for item in report.strategy_performance:
            lines.append(
                f"- {item.strategy_name}: closed={item.closed_trade_count}, "
                f"win_rate={value(item.win_rate_percent)}, realized_pnl=${item.realized_pnl:,.2f}"
            )
    else:
        lines.append("- No closed strategy trades are available.")
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def _require_paper_safe(payload: Mapping[str, Any], path: Path) -> None:
    if payload.get("paper_trade_mode") is not True:
        raise ValueError(f"{path} must declare paper_trade_mode=true")
    for field in (
        "live_trading_enabled",
        "broker_execution_enabled",
        "order_placement_enabled",
        "capital_movement_enabled",
        "direct_database_writes",
    ):
        if payload.get(field, False) is not False:
            raise ValueError(f"unsafe value in {path}: {field}")


def _positive(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def _nonnegative(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number < 0:
        raise ValueError(f"{field} must be nonnegative")
    return number


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _nonnegative_int(value: Any, field: str) -> int:
    number = _nonnegative(value, field)
    if not number.is_integer():
        raise ValueError(f"{field} must be an integer")
    return int(number)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
