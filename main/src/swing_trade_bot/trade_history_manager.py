"""Persistent paper-only trade history and lifecycle summaries.

The manager reads the append-only paper trade ledger produced by the execution
engine, validates deterministic trade records, pairs BUY and SELL activity using
FIFO accounting, and atomically publishes open-lot, closed-trade, and summary
evidence. It never connects to a broker and never places or modifies orders.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .paper_position_excursion import calculate_closed_long_trade_excursion

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ManagedTrade:
    trade_id: str
    symbol: str
    side: str
    trade_date: str
    price: float
    shares: float
    notional: float
    active_strategy: str
    reason: str
    paper_trade_mode: bool = True


@dataclass(frozen=True, slots=True)
class OpenTradeLot:
    symbol: str
    source_trade_id: str
    entry_date: str
    entry_price: float
    remaining_shares: float
    remaining_cost_basis: float
    active_strategy: str
    status: str = "OPEN"


@dataclass(frozen=True, slots=True)
class ClosedPaperTrade:
    closed_trade_id: str
    symbol: str
    buy_trade_id: str
    sell_trade_id: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    cost_basis: float
    proceeds: float
    realized_pnl: float
    realized_pnl_percent: float
    holding_days: int
    active_strategy: str
    exit_reason: str
    max_drawdown_amount: float | None = None
    max_drawdown_percent: float | None = None
    max_drawdown_peak_price: float | None = None
    max_drawdown_peak_date: str | None = None
    max_drawdown_trough_price: float | None = None
    max_drawdown_trough_date: str | None = None
    drawdown_observation_count: int | None = None
    drawdown_source: str | None = None
    status: str = "CLOSED"


@dataclass(frozen=True, slots=True)
class TradeHistoryReport:
    generated_at: str
    total_trade_events: int
    buy_event_count: int
    sell_event_count: int
    open_lot_count: int
    closed_trade_count: int
    realized_pnl: float
    winning_trade_count: int
    losing_trade_count: int
    breakeven_trade_count: int
    win_rate_percent: float | None
    trades: tuple[ManagedTrade, ...]
    open_lots: tuple[OpenTradeLot, ...]
    closed_trades: tuple[ClosedPaperTrade, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    capital_movement_enabled: bool = False
    direct_database_writes: bool = False
    schema_version: str = SCHEMA_VERSION


def build_trade_history_report(
    *,
    trade_history_path: Path,
    data_dir: Path | None = None,
) -> TradeHistoryReport:
    """Validate paper trade events and derive FIFO lifecycle evidence.

    When authoritative completed daily market history is available, each closed
    long paper trade also receives lifetime peak-to-trough drawdown evidence.
    Missing or truncated history leaves drawdown explicitly unavailable rather
    than inferring it from entry/exit snapshots.
    """
    payload = _load_json(trade_history_path)
    rows = payload.get("trades")
    if not isinstance(rows, list):
        raise ValueError("trade_history.json must contain a trades list")

    trades = tuple(_normalize_trade(row) for row in rows)
    _validate_unique_trade_ids(trades)
    ordered = tuple(sorted(trades, key=lambda item: (item.trade_date, item.trade_id)))
    resolved_data_dir = _resolve_data_dir(trade_history_path, data_dir)

    lots_by_symbol: dict[str, list[dict[str, Any]]] = {}
    closed: list[ClosedPaperTrade] = []
    warnings: list[str] = []

    for trade in ordered:
        if trade.side == "BUY":
            lots_by_symbol.setdefault(trade.symbol, []).append(
                {
                    "trade_id": trade.trade_id,
                    "entry_date": trade.trade_date,
                    "entry_price": trade.price,
                    "remaining_shares": trade.shares,
                    "active_strategy": trade.active_strategy,
                }
            )
            continue

        remaining_to_sell = trade.shares
        lots = lots_by_symbol.setdefault(trade.symbol, [])
        while remaining_to_sell > 1e-10:
            if not lots:
                raise ValueError(
                    f"SELL {trade.trade_id} exceeds available paper shares for {trade.symbol}"
                )
            lot = lots[0]
            matched = min(remaining_to_sell, float(lot["remaining_shares"]))
            cost_basis = round(matched * float(lot["entry_price"]), 2)
            proceeds = round(matched * trade.price, 2)
            realized = round(proceeds - cost_basis, 2)
            realized_percent = round((realized / cost_basis) * 100.0, 6) if cost_basis else 0.0
            entry_day = date.fromisoformat(str(lot["entry_date"]))
            exit_day = date.fromisoformat(trade.trade_date)
            holding_days = (exit_day - entry_day).days
            if holding_days < 0:
                raise ValueError(f"SELL {trade.trade_id} occurs before its matched BUY")

            closed_trade_id = f"CLOSED-{lot['trade_id']}-{trade.trade_id}-{len(closed) + 1}"
            excursion = None
            if resolved_data_dir is not None:
                try:
                    excursion = calculate_closed_long_trade_excursion(
                        market_data_path=resolved_data_dir / f"{trade.symbol}.csv",
                        entry_date=entry_day,
                        exit_date=exit_day,
                        entry_price=float(lot["entry_price"]),
                        shares=matched,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    warnings.append(
                        f"{closed_trade_id} max drawdown unavailable from authoritative market history: {exc}"
                    )
                if excursion is None:
                    warnings.append(
                        f"{closed_trade_id} max drawdown is not reportable because authoritative market history does not cover the full holding period."
                    )

            closed.append(
                ClosedPaperTrade(
                    closed_trade_id=closed_trade_id,
                    symbol=trade.symbol,
                    buy_trade_id=str(lot["trade_id"]),
                    sell_trade_id=trade.trade_id,
                    entry_date=str(lot["entry_date"]),
                    exit_date=trade.trade_date,
                    entry_price=float(lot["entry_price"]),
                    exit_price=trade.price,
                    shares=round(matched, 8),
                    cost_basis=cost_basis,
                    proceeds=proceeds,
                    realized_pnl=realized,
                    realized_pnl_percent=realized_percent,
                    holding_days=holding_days,
                    active_strategy=str(lot["active_strategy"]),
                    exit_reason=trade.reason,
                    max_drawdown_amount=(excursion.max_drawdown_amount if excursion else None),
                    max_drawdown_percent=(excursion.max_drawdown_percent if excursion else None),
                    max_drawdown_peak_price=(excursion.max_drawdown_peak_price if excursion else None),
                    max_drawdown_peak_date=(excursion.max_drawdown_peak_date if excursion else None),
                    max_drawdown_trough_price=(excursion.max_drawdown_trough_price if excursion else None),
                    max_drawdown_trough_date=(excursion.max_drawdown_trough_date if excursion else None),
                    drawdown_observation_count=(excursion.observation_count if excursion else None),
                    drawdown_source=(excursion.source if excursion else None),
                )
            )
            lot["remaining_shares"] = round(float(lot["remaining_shares"]) - matched, 8)
            remaining_to_sell = round(remaining_to_sell - matched, 8)
            if float(lot["remaining_shares"]) <= 1e-10:
                lots.pop(0)

    open_lots: list[OpenTradeLot] = []
    for symbol, lots in lots_by_symbol.items():
        for lot in lots:
            shares = round(float(lot["remaining_shares"]), 8)
            if shares <= 0:
                continue
            entry_price = float(lot["entry_price"])
            open_lots.append(
                OpenTradeLot(
                    symbol=symbol,
                    source_trade_id=str(lot["trade_id"]),
                    entry_date=str(lot["entry_date"]),
                    entry_price=entry_price,
                    remaining_shares=shares,
                    remaining_cost_basis=round(shares * entry_price, 2),
                    active_strategy=str(lot["active_strategy"]),
                )
            )

    closed_tuple = tuple(sorted(closed, key=lambda item: (item.exit_date, item.closed_trade_id)))
    wins = sum(1 for item in closed_tuple if item.realized_pnl > 0)
    losses = sum(1 for item in closed_tuple if item.realized_pnl < 0)
    breakeven = len(closed_tuple) - wins - losses
    decided = wins + losses
    win_rate = round((wins / decided) * 100.0, 6) if decided else None
    if not closed_tuple:
        warnings.append("No closed paper trades are available; win rate is not yet reportable.")

    return TradeHistoryReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_trade_events=len(ordered),
        buy_event_count=sum(1 for item in ordered if item.side == "BUY"),
        sell_event_count=sum(1 for item in ordered if item.side == "SELL"),
        open_lot_count=len(open_lots),
        closed_trade_count=len(closed_tuple),
        realized_pnl=round(sum(item.realized_pnl for item in closed_tuple), 2),
        winning_trade_count=wins,
        losing_trade_count=losses,
        breakeven_trade_count=breakeven,
        win_rate_percent=win_rate,
        trades=ordered,
        open_lots=tuple(sorted(open_lots, key=lambda item: (item.symbol, item.entry_date, item.source_trade_id))),
        closed_trades=closed_tuple,
        warnings=tuple(dict.fromkeys(warnings)),
        errors=(),
    )


def write_trade_history_outputs(output_dir: Path, report: TradeHistoryReport) -> tuple[Path, Path, Path]:
    """Atomically publish normalized history, closed trades, and summary evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = output_dir / "managed_trade_history.json"
    closed_path = output_dir / "closed_positions.json"
    summary_path = output_dir / "trade_history_summary.json"

    _atomic_json(
        normalized_path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": report.generated_at,
            "paper_trade_mode": True,
            "trade_count": report.total_trade_events,
            "trades": [asdict(item) for item in report.trades],
            "open_lots": [asdict(item) for item in report.open_lots],
        },
    )
    _atomic_json(
        closed_path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": report.generated_at,
            "paper_trade_mode": True,
            "closed_trade_count": report.closed_trade_count,
            "closed_trades": [asdict(item) for item in report.closed_trades],
        },
    )
    summary = {
        key: value
        for key, value in asdict(report).items()
        if key not in {"trades", "open_lots", "closed_trades"}
    }
    _atomic_json(summary_path, summary)
    return normalized_path, closed_path, summary_path


def build_and_write_trade_history_report(
    *,
    trade_history_path: Path = Path("results/paper_ledger/trade_history.json"),
    output_dir: Path = Path("results/paper_ledger"),
    data_dir: Path | None = None,
) -> TradeHistoryReport:
    report = build_trade_history_report(
        trade_history_path=trade_history_path,
        data_dir=data_dir,
    )
    write_trade_history_outputs(output_dir, report)
    return report


def _resolve_data_dir(trade_history_path: Path, data_dir: Path | None) -> Path | None:
    if data_dir is not None:
        return Path(data_dir)
    try:
        candidate = trade_history_path.resolve().parents[2] / "data"
    except IndexError:
        return None
    return candidate if candidate.is_dir() else None


def _normalize_trade(row: Any) -> ManagedTrade:
    if not isinstance(row, Mapping):
        raise ValueError("each trade history row must be a JSON object")
    trade_id = str(row.get("trade_id", "")).strip()
    symbol = str(row.get("symbol", "")).strip().upper()
    side = str(row.get("side", "")).strip().upper()
    trade_date = str(row.get("trade_date", "")).strip()
    if not trade_id or not symbol:
        raise ValueError("trade_id and symbol are required")
    if side not in {"BUY", "SELL"}:
        raise ValueError(f"unsupported paper trade side: {side}")
    try:
        date.fromisoformat(trade_date)
    except ValueError as exc:
        raise ValueError(f"invalid trade_date for {trade_id}") from exc
    price = _positive(row.get("price"), f"{trade_id}.price")
    shares = _positive(row.get("shares"), f"{trade_id}.shares")
    notional = _nonnegative(row.get("notional"), f"{trade_id}.notional")
    expected_notional = round(price * shares, 2)
    if abs(notional - expected_notional) > 0.02:
        raise ValueError(f"{trade_id}.notional does not match price times shares")
    if row.get("paper_trade_mode") is not True:
        raise ValueError(f"{trade_id} is not marked paper_trade_mode=true")
    return ManagedTrade(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        trade_date=trade_date,
        price=price,
        shares=shares,
        notional=notional,
        active_strategy=str(row.get("active_strategy", "Strategy A")),
        reason=str(row.get("reason", "UNSPECIFIED")),
    )


def _validate_unique_trade_ids(trades: Sequence[ManagedTrade]) -> None:
    ids = [item.trade_id for item in trades]
    if len(ids) != len(set(ids)):
        raise ValueError("trade history contains duplicate trade_id values")


def _positive(value: Any, field: str) -> float:
    number = _nonnegative(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def _nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return number


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(dict(payload), output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
