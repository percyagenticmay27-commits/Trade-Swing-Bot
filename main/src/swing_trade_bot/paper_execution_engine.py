"""Persistent paper-only execution and position ledger.

Consumes existing portfolio allocation recommendations and completed daily CSV
bars. It never connects to a broker and never places real orders.

Frozen DIRECT strategy symbols are owned by the frozen Primary execution path.
This legacy allocation engine may mark an already-open frozen position to market,
but it must never create/recreate that position or replace its strategy authority.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
SCHEMA_VERSION = "1.0"
RESERVE_SYMBOLS = {"CASH", "RESERVE", "SGOV"}
DEFAULT_FROZEN_STRATEGY_CONFIG_PATH = Path("configs/frozen_strategy_assignments.json")


@dataclass(frozen=True, slots=True)
class PaperPosition:
    symbol: str
    opened_at: str
    entry_date: str
    entry_price: float
    shares: float
    cost_basis: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    allocation_percent: float
    active_strategy: str
    status: str = "OPEN"


@dataclass(frozen=True, slots=True)
class PaperTrade:
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
class PaperExecutionReport:
    generated_at: str
    account_capital: float
    invested_capital: float
    cash_balance: float
    portfolio_value: float
    positions: tuple[PaperPosition, ...]
    trades: tuple[PaperTrade, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    capital_movement_enabled: bool = False
    schema_version: str = SCHEMA_VERSION


def execute_allocations(
    *,
    allocations_path: Path,
    data_dir: Path,
    state_dir: Path,
    account_capital: float,
    as_of: date | None = None,
    frozen_strategy_config_path: Path = DEFAULT_FROZEN_STRATEGY_CONFIG_PATH,
) -> PaperExecutionReport:
    """Create missing legacy paper positions and mark open positions to market.

    Existing positions are preserved. New positive allocations are filled using
    the latest completed Close from each symbol CSV, except for symbols governed
    by the frozen DIRECT Primary registry. Frozen symbols can only be opened by
    the frozen Primary paper-execution boundary; if already open here they are
    mark-to-market only and their active strategy authority is preserved.

    This function does not implement sells.
    """
    if not math.isfinite(account_capital) or account_capital <= 0:
        raise ValueError("account_capital must be finite and positive")
    rows = _load_allocations(allocations_path)
    frozen_symbols = _load_frozen_direct_symbols(frozen_strategy_config_path)
    state_dir.mkdir(parents=True, exist_ok=True)
    existing = _load_position_state(state_dir / "open_positions.json")
    positions_by_symbol = {position.symbol: position for position in existing}
    trades: list[PaperTrade] = []
    warnings: list[str] = []
    errors: list[str] = []
    today = as_of or date.today()

    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        allocation = _number(row.get("allocation_percent"), default=0.0)
        if not symbol or symbol in RESERVE_SYMBOLS or allocation <= 0:
            continue
        price_date, close = _latest_completed_close(data_dir / f"{symbol}.csv", today)
        current = positions_by_symbol.get(symbol)
        frozen_governed = symbol in frozen_symbols
        if current is None:
            if frozen_governed:
                warnings.append(
                    f"{symbol} is governed by frozen DIRECT Primary; legacy allocation BUY suppressed"
                )
                continue
            notional = round(account_capital * allocation / 100.0, 2)
            shares = round(notional / close, 8)
            cost_basis = round(shares * close, 2)
            opened_at = datetime.now(timezone.utc).isoformat()
            current = PaperPosition(
                symbol=symbol,
                opened_at=opened_at,
                entry_date=price_date.isoformat(),
                entry_price=close,
                shares=shares,
                cost_basis=cost_basis,
                current_price=close,
                market_value=cost_basis,
                unrealized_pnl=0.0,
                unrealized_pnl_percent=0.0,
                allocation_percent=allocation,
                active_strategy=str(row.get("active_strategy", "Strategy A")),
            )
            positions_by_symbol[symbol] = current
            trades.append(
                PaperTrade(
                    trade_id=f"PAPER-{symbol}-{price_date.isoformat()}-BUY",
                    symbol=symbol,
                    side="BUY",
                    trade_date=price_date.isoformat(),
                    price=close,
                    shares=shares,
                    notional=cost_basis,
                    active_strategy=current.active_strategy,
                    reason="NEW_POSITIVE_PORTFOLIO_ALLOCATION",
                )
            )
        else:
            market_value = round(current.shares * close, 2)
            pnl = round(market_value - current.cost_basis, 2)
            pnl_percent = round((pnl / current.cost_basis) * 100.0, 6) if current.cost_basis else 0.0
            positions_by_symbol[symbol] = PaperPosition(
                **{
                    **asdict(current),
                    "current_price": close,
                    "market_value": market_value,
                    "unrealized_pnl": pnl,
                    "unrealized_pnl_percent": pnl_percent,
                    "allocation_percent": current.allocation_percent if frozen_governed else allocation,
                    "active_strategy": current.active_strategy if frozen_governed else str(row.get("active_strategy", current.active_strategy)),
                }
            )
            if frozen_governed:
                warnings.append(
                    f"{symbol} is governed by frozen DIRECT Primary; legacy allocator performed mark-to-market only"
                )

    positions = tuple(sorted(positions_by_symbol.values(), key=lambda item: item.symbol))
    invested = round(sum(position.cost_basis for position in positions), 2)
    market_value = round(sum(position.market_value for position in positions), 2)
    cash = round(account_capital - invested, 2)
    report = PaperExecutionReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        account_capital=round(account_capital, 2),
        invested_capital=invested,
        cash_balance=cash,
        portfolio_value=round(cash + market_value, 2),
        positions=positions,
        trades=tuple(trades),
        warnings=tuple(warnings),
        errors=tuple(errors),
    )
    write_execution_outputs(state_dir, report)
    return report


def write_execution_outputs(state_dir: Path, report: PaperExecutionReport) -> None:
    """Atomically publish the current paper ledger and append-only trade history."""
    state_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(state_dir / "open_positions.json", {
        "schema_version": SCHEMA_VERSION,
        "paper_trade_mode": True,
        "generated_at": report.generated_at,
        "positions": [asdict(position) for position in report.positions],
    })
    history_path = state_dir / "trade_history.json"
    prior = _load_json(history_path, {"schema_version": SCHEMA_VERSION, "trades": []})
    prior_trades = list(prior.get("trades", [])) if isinstance(prior, Mapping) else []
    known_ids = {str(row.get("trade_id")) for row in prior_trades if isinstance(row, Mapping)}
    prior_trades.extend(asdict(trade) for trade in report.trades if trade.trade_id not in known_ids)
    _atomic_json(history_path, {
        "schema_version": SCHEMA_VERSION,
        "paper_trade_mode": True,
        "generated_at": report.generated_at,
        "trades": prior_trades,
    })
    _atomic_json(state_dir / "paper_portfolio_summary.json", {
        **{key: value for key, value in asdict(report).items() if key not in {"positions", "trades"}},
        "position_count": len(report.positions),
        "new_trade_count": len(report.trades),
    })


def _load_allocations(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path, None)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("allocations"), list):
        raise ValueError("portfolio allocation JSON must contain an allocations list")
    return [dict(row) for row in payload["allocations"] if isinstance(row, Mapping)]


def _load_frozen_direct_symbols(path: Path) -> set[str]:
    """Return frozen symbols with enabled DIRECT Primary authority.

    A missing registry means this legacy module retains its original behavior.
    A malformed present registry fails closed rather than silently bypassing the
    frozen ownership boundary.
    """
    path = Path(path)
    if not path.is_file():
        return set()
    payload = _load_json(path, None)
    if not isinstance(payload, Mapping):
        raise ValueError("frozen strategy registry root must be an object")
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("frozen strategy registry must be paper_trade_mode=true")
    strategies = payload.get("strategies")
    if not isinstance(strategies, list):
        raise ValueError("frozen strategy registry must contain a strategies list")
    output: set[str] = set()
    for row in strategies:
        if not isinstance(row, Mapping):
            raise ValueError("frozen strategy registry strategy rows must be objects")
        if str(row.get("assignment_mode", "")).strip().upper() != "DIRECT":
            continue
        if row.get("enabled") is not True:
            continue
        symbol = str(row.get("vehicle_symbol") or row.get("signal_symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("enabled frozen DIRECT strategy requires vehicle_symbol or signal_symbol")
        output.add(symbol)
    return output


def _load_position_state(path: Path) -> tuple[PaperPosition, ...]:
    if not path.exists():
        return ()
    payload = _load_json(path, {})
    rows = payload.get("positions", []) if isinstance(payload, Mapping) else []
    return tuple(PaperPosition(**dict(row)) for row in rows if isinstance(row, Mapping))


def _latest_completed_close(path: Path, as_of: date) -> tuple[date, float]:
    if not path.exists():
        raise FileNotFoundError(f"market data missing: {path}")
    latest: tuple[date, float] | None = None
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f"market data has no headers: {path}")
        normalized = {name.strip().lower().replace("_", " "): name for name in reader.fieldnames}
        if "date" not in normalized or "close" not in normalized:
            raise ValueError(f"market data must contain Date and Close: {path}")
        for row in reader:
            bar_date = date.fromisoformat(str(row[normalized["date"]]).strip())
            close = float(row[normalized["close"]])
            if bar_date > as_of:
                continue
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"invalid Close for {path.name} on {bar_date}")
            if latest is None or bar_date > latest[0]:
                latest = (bar_date, close)
    if latest is None:
        raise ValueError(f"no completed bars available: {path}")
    return latest


def _number(value: Any, *, default: float) -> float:
    if value in (None, ""):
        return default
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("numeric value must be finite")
    return result


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
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
