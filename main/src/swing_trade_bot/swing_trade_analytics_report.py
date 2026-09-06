"""Dedicated paper-only Swing trade lifecycle reporting.

This presentation report consumes the authoritative trade_analytics section from
SWING-001 Enterprise KPI evidence. It does not calculate trading performance,
infer drawdown, create trades, connect to a broker, or move capital.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_trade_analytics_report"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
REPORT_ID = "SWING-TRADE-ANALYTICS"
STRATEGY_ID = "SWING-001"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False

MAX_DRAWDOWN_POLICY = "AUTHORITATIVE_POSITION_HISTORY_ONLY"

COLUMNS = (
    "symbol",
    "entry_date",
    "entry_price",
    "current_price",
    "exit_date",
    "exit_price",
    "shares",
    "cost_basis",
    "current_or_exit_value",
    "gain_loss_amount",
    "gain_loss_percent",
    "max_drawdown_amount",
    "max_drawdown_percent",
    "days_held",
    "active_strategy",
    "position_status",
    "exit_reason",
)


def build_swing_trade_analytics_report(
    enterprise_kpis: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a consumer-ready Swing position-performance report."""
    if enterprise_kpis.get("strategy_id") != STRATEGY_ID:
        raise ValueError("Swing trade analytics requires strategy_id=SWING-001")
    if enterprise_kpis.get("paper_trade_mode") is not True:
        raise ValueError("Swing trade analytics requires paper_trade_mode=true")
    for field in (
        "live_trading_enabled",
        "broker_execution_enabled",
        "order_placement_enabled",
        "capital_movement_enabled",
        "direct_database_writes",
    ):
        if enterprise_kpis.get(field, False) is not False:
            raise ValueError(f"unsafe Enterprise KPI evidence: {field}")

    analytics = enterprise_kpis.get("trade_analytics")
    if not isinstance(analytics, Mapping):
        raise ValueError("Enterprise KPI evidence must contain trade_analytics")
    if analytics.get("max_drawdown_policy") != MAX_DRAWDOWN_POLICY:
        raise ValueError("trade_analytics max_drawdown_policy is not authoritative")
    if analytics.get("max_drawdown_inference_allowed") is not False:
        raise ValueError("trade_analytics must prohibit max drawdown inference")

    generated_at = str(enterprise_kpis.get("generated_at", ""))
    as_of = _date_prefix(generated_at)
    open_rows = _rows(analytics.get("open_positions"), status="OPEN", as_of=as_of)
    closed_rows = _rows(analytics.get("closed_positions"), status="CLOSED", as_of=as_of)
    positions = sorted(
        [*open_rows, *closed_rows],
        key=lambda row: (
            row["position_status"],
            row["symbol"],
            row.get("entry_date") or "",
            row.get("exit_date") or "",
        ),
    )

    declared_open = analytics.get("open_position_count")
    declared_closed = analytics.get("closed_position_count")
    if declared_open is not None and int(declared_open) != len(open_rows):
        raise ValueError("open_position_count does not match authoritative rows")
    if declared_closed is not None and int(declared_closed) != len(closed_rows):
        raise ValueError("closed_position_count does not match authoritative rows")

    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": REPORT_ID,
        "report_type": "TRADE_ANALYTICS_POSITION_PERFORMANCE",
        "title": "Swing Trade Analytics / Position Performance",
        "strategy_id": STRATEGY_ID,
        "generated_at": generated_at,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
        "max_drawdown_policy": MAX_DRAWDOWN_POLICY,
        "max_drawdown_inference_allowed": False,
        "open_position_count": len(open_rows),
        "closed_position_count": len(closed_rows),
        "position_count": len(positions),
        "columns": list(COLUMNS),
        "open_positions": open_rows,
        "closed_positions": closed_rows,
        "positions": positions,
        "source_artifact": "results/enterprise_strategy_kpis.json",
        "source_section": "trade_analytics",
    }


def _rows(value: Any, *, status: str, as_of: date | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{status.lower()}_positions must be a list")
    output: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("trade analytics position rows must be objects")
        output.append(_position(raw, status=status, as_of=as_of))
    return output


def _position(raw: Mapping[str, Any], *, status: str, as_of: date | None) -> dict[str, Any]:
    symbol = str(raw.get("symbol", "")).strip().upper()
    if not symbol:
        raise ValueError("trade analytics position symbol is required")
    actual = str(raw.get("position_status", status)).strip().upper()
    if actual != status:
        raise ValueError(f"{symbol} position_status must be {status}")

    row: dict[str, Any] = {
        "symbol": symbol,
        "entry_date": _text_or_none(raw.get("entry_date")),
        "entry_price": _number_or_none(raw.get("entry_price")),
        "shares": _number_or_none(raw.get("shares")),
        "cost_basis": _number_or_none(raw.get("cost_basis")),
        "max_drawdown_amount": _number_or_none(raw.get("max_drawdown_amount")),
        "max_drawdown_percent": _number_or_none(raw.get("max_drawdown_percent")),
        "active_strategy": str(raw.get("active_strategy", "")).strip(),
        "position_status": status,
    }
    if status == "OPEN":
        forbidden = ("exit_date", "exit_price", "realized_pnl", "realized_pnl_percent", "exit_reason")
        if any(raw.get(field) not in (None, "") for field in forbidden):
            raise ValueError(f"{symbol} open position contains fabricated exit evidence")
        row.update(
            {
                "current_price": _number_or_none(raw.get("current_price")),
                "current_or_exit_value": _number_or_none(raw.get("market_value")),
                "gain_loss_amount": _number_or_none(raw.get("unrealized_pnl")),
                "gain_loss_percent": _number_or_none(raw.get("unrealized_pnl_percent")),
                "days_held": _days_between(row["entry_date"], as_of),
            }
        )
    else:
        exit_date = _text_or_none(raw.get("exit_date"))
        row.update(
            {
                "exit_date": exit_date,
                "exit_price": _number_or_none(raw.get("exit_price")),
                "current_or_exit_value": _number_or_none(
                    raw.get("proceeds", raw.get("exit_value"))
                ),
                "gain_loss_amount": _number_or_none(raw.get("realized_pnl")),
                "gain_loss_percent": _number_or_none(raw.get("realized_pnl_percent")),
                "days_held": _integer_or_none(raw.get("holding_days")),
                "exit_reason": str(raw.get("exit_reason", "")).strip(),
            }
        )
        if not exit_date or row["exit_price"] is None:
            raise ValueError(f"{symbol} closed position lacks authoritative exit evidence")
    return row


def write_swing_trade_analytics_report(
    report: Mapping[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    """Atomically publish JSON, CSV, and Markdown report views."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "swing_trade_analytics_report.json"
    csv_path = root / "swing_trade_analytics_report.csv"
    md_path = root / "swing_trade_analytics_report.md"
    _atomic_text(json_path, json.dumps(dict(report), indent=2, sort_keys=True) + "\n")

    rows = report.get("positions")
    if not isinstance(rows, list):
        raise ValueError("report positions must be a list")
    fd, temp_name = tempfile.mkstemp(prefix=f".{csv_path.name}.", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(COLUMNS), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in COLUMNS})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, csv_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

    _atomic_text(md_path, format_swing_trade_analytics_markdown(report) + "\n")
    return json_path, csv_path, md_path


def format_swing_trade_analytics_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Swing Trade Analytics / Position Performance",
        "",
        f"- Strategy: {report.get('strategy_id')}",
        f"- Open Positions: {report.get('open_position_count')}",
        f"- Closed Positions: {report.get('closed_position_count')}",
        f"- Drawdown Policy: {report.get('max_drawdown_policy')}",
        "",
        "| Symbol | Entry Date | Entry Price | Current/Exit Price | Shares | Cost Basis | Current/Exit Value | Gain/Loss $ | Gain/Loss % | Max Drawdown $ | Max Drawdown % | Days Held | Strategy | Status | Exit Reason |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    rows = report.get("positions")
    if isinstance(rows, list):
        for row in rows:
            price = row.get("current_price", row.get("exit_price"))
            lines.append(
                f"| {row.get('symbol', '')} | {row.get('entry_date') or '-'} | {_display(row.get('entry_price'))} | "
                f"{_display(price)} | {_display(row.get('shares'))} | {_display(row.get('cost_basis'))} | "
                f"{_display(row.get('current_or_exit_value'))} | {_display(row.get('gain_loss_amount'))} | "
                f"{_display(row.get('gain_loss_percent'))} | {_display(row.get('max_drawdown_amount'))} | "
                f"{_display(row.get('max_drawdown_percent'))} | {row.get('days_held') if row.get('days_held') is not None else '-'} | "
                f"{row.get('active_strategy') or '-'} | {row.get('position_status')} | {row.get('exit_reason') or '-'} |"
            )
    if not rows:
        lines.append("| None | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
    return "\n".join(lines)


def _atomic_text(path: Path, content: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("trade analytics numeric evidence must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError("trade analytics numeric evidence must be finite")
    return number


def _integer_or_none(value: Any) -> int | None:
    number = _number_or_none(value)
    return None if number is None else int(number)


def _text_or_none(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _date_prefix(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _days_between(entry: Any, as_of: date | None) -> int | None:
    if not entry or as_of is None:
        return None
    try:
        start = date.fromisoformat(str(entry)[:10])
    except ValueError:
        return None
    days = (as_of - start).days
    return days if days >= 0 else None


def _display(value: Any) -> str:
    return "-" if value is None else str(value)
