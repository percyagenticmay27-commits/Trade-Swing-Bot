"""Generate the paper-only Swing executive summary CSV.

The report combines account-level KPI evidence with current paper holdings so the
emailed CSV clearly shows what the Swing Bot bought and the current valuation.
No strategy calculations or order behavior are implemented here.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False

DEFAULT_KPI_PATH = Path("results/enterprise_strategy_kpis.json")
DEFAULT_PORTFOLIO_SUMMARY_PATH = Path("results/paper_ledger/paper_portfolio_summary.json")
DEFAULT_OUTPUT_PATH = Path("results/swing_executive_summary.csv")

EXECUTIVE_COLUMNS = (
    "report_date",
    "record_type",
    "strategy_id",
    "symbol",
    "action",
    "active_strategy",
    "shares",
    "entry_date",
    "entry_price",
    "current_price",
    "cost_basis",
    "market_value",
    "unrealized_pnl",
    "unrealized_pnl_percent",
    "allocated_capital",
    "cash_balance",
    "invested_capital",
    "portfolio_value",
    "position_count",
    "trade_count",
    "closed_trade_count",
    "portfolio_return_percent",
    "win_rate_percent",
    "opportunity_quality",
    "confidence",
    "status",
    "evidence_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positions_from_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [
        payload.get("open_positions"),
        payload.get("positions"),
        payload.get("holdings"),
    ]
    portfolio = payload.get("portfolio")
    if isinstance(portfolio, Mapping):
        candidates.extend((portfolio.get("open_positions"), portfolio.get("positions")))
    holdings = payload.get("holdings")
    if isinstance(holdings, Mapping):
        candidates.extend((holdings.get("open_positions"), holdings.get("positions"), holdings.get("items")))
    for candidate in candidates:
        if isinstance(candidate, list):
            return [dict(item) for item in candidate if isinstance(item, Mapping)]
    return []


def _position_row(position: Mapping[str, Any], kpi: Mapping[str, Any], report_date: str) -> dict[str, Any]:
    shares = _as_float(_first(position, "shares", "quantity", "remaining_shares", "units"))
    entry_price = _as_float(_first(position, "entry_price", "average_cost", "avg_cost", "cost_per_share"))
    current_price = _as_float(_first(position, "current_price", "market_price", "last_price", "price"))
    cost_basis = _as_float(_first(position, "cost_basis", "remaining_cost_basis", "invested_amount"))
    market_value = _as_float(_first(position, "market_value", "position_value", "current_value"))
    if cost_basis is None and shares is not None and entry_price is not None:
        cost_basis = shares * entry_price
    if market_value is None and shares is not None and current_price is not None:
        market_value = shares * current_price
    unrealized = _as_float(_first(position, "unrealized_pnl", "unrealized_gain_loss"))
    if unrealized is None and cost_basis is not None and market_value is not None:
        unrealized = market_value - cost_basis
    unrealized_percent = _as_float(_first(position, "unrealized_pnl_percent", "unrealized_return_percent"))
    if unrealized_percent is None and unrealized is not None and cost_basis not in (None, 0):
        unrealized_percent = unrealized / cost_basis * 100.0

    return {
        "report_date": report_date,
        "record_type": "POSITION",
        "strategy_id": kpi.get("strategy_id", "SWING-001"),
        "symbol": str(_first(position, "symbol", "ticker", default="")).upper(),
        "action": _first(position, "action", "side", default="BUY"),
        "active_strategy": _first(position, "active_strategy", "strategy", "strategy_name"),
        "shares": shares,
        "entry_date": _first(position, "entry_date", "opened_at", "trade_date"),
        "entry_price": entry_price,
        "current_price": current_price,
        "cost_basis": cost_basis,
        "market_value": market_value,
        "unrealized_pnl": unrealized,
        "unrealized_pnl_percent": unrealized_percent,
        "allocated_capital": kpi.get("allocated_capital"),
        "cash_balance": kpi.get("cash_balance"),
        "invested_capital": kpi.get("invested_capital"),
        "portfolio_value": kpi.get("portfolio_value"),
        "position_count": kpi.get("position_count"),
        "trade_count": kpi.get("trade_count"),
        "closed_trade_count": kpi.get("closed_trade_count"),
        "portfolio_return_percent": kpi.get("portfolio_return_percent"),
        "win_rate_percent": kpi.get("win_rate_percent"),
        "opportunity_quality": kpi.get("opportunity_quality"),
        "confidence": _first(position, "confidence", "confidence_level"),
        "status": _first(position, "status", default="OPEN"),
        "evidence_status": kpi.get("evidence_status"),
    }


def build_swing_executive_rows(
    kpi: Mapping[str, Any],
    portfolio_summary: Mapping[str, Any] | None = None,
    report_date: str | None = None,
) -> list[dict[str, Any]]:
    """Build one account summary row followed by one row per open position."""
    if not kpi:
        raise ValueError("Enterprise KPI evidence is required")
    current_date = report_date or date.today().isoformat()
    positions = _positions_from_payload(kpi)
    if not positions and portfolio_summary:
        positions = _positions_from_payload(portfolio_summary)

    summary = {
        "report_date": current_date,
        "record_type": "ACCOUNT_SUMMARY",
        "strategy_id": kpi.get("strategy_id", "SWING-001"),
        "symbol": "",
        "action": "",
        "active_strategy": "",
        "shares": "",
        "entry_date": "",
        "entry_price": "",
        "current_price": "",
        "cost_basis": "",
        "market_value": kpi.get("positions_market_value"),
        "unrealized_pnl": kpi.get("unrealized_pnl"),
        "unrealized_pnl_percent": "",
        "allocated_capital": kpi.get("allocated_capital"),
        "cash_balance": kpi.get("cash_balance"),
        "invested_capital": kpi.get("invested_capital"),
        "portfolio_value": kpi.get("portfolio_value"),
        "position_count": kpi.get("position_count"),
        "trade_count": kpi.get("trade_count"),
        "closed_trade_count": kpi.get("closed_trade_count"),
        "portfolio_return_percent": kpi.get("portfolio_return_percent"),
        "win_rate_percent": kpi.get("win_rate_percent"),
        "opportunity_quality": kpi.get("opportunity_quality"),
        "confidence": "",
        "status": "PAPER_ONLY",
        "evidence_status": kpi.get("evidence_status"),
    }
    rows = [summary]
    rows.extend(_position_row(position, kpi, current_date) for position in positions)
    return rows


def write_swing_executive_summary(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    kpi_path: Path = DEFAULT_KPI_PATH,
    portfolio_summary_path: Path = DEFAULT_PORTFOLIO_SUMMARY_PATH,
) -> Path:
    kpi = _read_json(kpi_path)
    if not kpi:
        raise FileNotFoundError(f"Enterprise Swing KPI evidence not found: {kpi_path}")
    portfolio_summary = _read_json(portfolio_summary_path)
    rows = build_swing_executive_rows(kpi, portfolio_summary)
    _atomic_csv_write(output_path, rows, EXECUTIVE_COLUMNS)
    return output_path


def _atomic_csv_write(path: Path, rows: Iterable[dict[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
