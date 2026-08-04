"""Paper-only portfolio valuation built from the persistent execution ledger.

This module owns no market-data fetching and performs no broker operations. It
reads open paper positions plus completed local daily CSV bars, validates that
those bars are fresh, applies split normalization when adjusted-close evidence
requires it, and atomically publishes authoritative portfolio evidence.
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
from typing import Any, Mapping

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False
SCHEMA_VERSION = "1.1"
DEFAULT_MAX_PRICE_AGE_DAYS = 5


@dataclass(frozen=True, slots=True)
class ValuedPaperPosition:
    symbol: str
    entry_date: str
    entry_price: float
    shares: float
    cost_basis: float
    current_price: float
    price_date: str
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    allocation_percent: float
    active_strategy: str
    split_adjustment_factor: float = 1.0
    price_source: str = "ADJ_CLOSE"
    status: str = "OPEN"


@dataclass(frozen=True, slots=True)
class PaperPortfolioReport:
    generated_at: str
    account_capital: float
    invested_capital: float
    cash_balance: float
    positions_market_value: float
    portfolio_value: float
    unrealized_pnl: float
    portfolio_return_percent: float
    position_count: int
    positions: tuple[ValuedPaperPosition, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    valuation_source: str = "PAPER_LEDGER_SPLIT_ADJUSTED_MARK_TO_MARKET"
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    capital_movement_enabled: bool = False
    direct_database_writes: bool = False
    schema_version: str = SCHEMA_VERSION


def build_paper_portfolio_report(
    *,
    ledger_dir: Path,
    data_dir: Path,
    account_capital: float,
    as_of: date | None = None,
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
) -> PaperPortfolioReport:
    """Mark open paper positions to fresh, split-adjusted completed closes."""
    if not math.isfinite(account_capital) or account_capital <= 0:
        raise ValueError("account_capital must be finite and positive")
    if max_price_age_days < 0:
        raise ValueError("max_price_age_days must be nonnegative")

    source = _load_json(ledger_dir / "open_positions.json")
    rows = source.get("positions")
    if not isinstance(rows, list):
        raise ValueError("open_positions.json must contain a positions list")

    valued: list[ValuedPaperPosition] = []
    warnings: list[str] = []
    valuation_date = as_of or date.today()

    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each open position must be a JSON object")
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("open position symbol is required")
        original_shares = _positive(row.get("shares"), f"{symbol}.shares")
        original_entry_price = _positive(row.get("entry_price"), f"{symbol}.entry_price")
        cost_basis = _nonnegative(row.get("cost_basis"), f"{symbol}.cost_basis")
        entry_date = _parse_date(row.get("entry_date"), f"{symbol}.entry_date")

        price_date, current_price, split_factor, price_source = _latest_completed_adjusted_close(
            data_dir / f"{symbol}.csv",
            valuation_date,
            entry_date=entry_date,
            max_price_age_days=max_price_age_days,
        )

        shares = round(original_shares * split_factor, 12)
        entry_price = round(original_entry_price / split_factor, 12)
        normalized_cost_basis = round(shares * entry_price, 2)
        if abs(normalized_cost_basis - cost_basis) > 0.02:
            raise ValueError(
                f"{symbol} split normalization does not preserve cost basis: "
                f"stored={cost_basis}, normalized={normalized_cost_basis}"
            )
        if split_factor != 1.0:
            warnings.append(
                f"{symbol} position normalized for corporate action factor {split_factor:g}"
            )

        market_value = round(shares * current_price, 2)
        unrealized = round(market_value - cost_basis, 2)
        unrealized_percent = round((unrealized / cost_basis) * 100.0, 6) if cost_basis else 0.0
        valued.append(
            ValuedPaperPosition(
                symbol=symbol,
                entry_date=entry_date.isoformat(),
                entry_price=entry_price,
                shares=shares,
                cost_basis=cost_basis,
                current_price=current_price,
                price_date=price_date.isoformat(),
                market_value=market_value,
                unrealized_pnl=unrealized,
                unrealized_pnl_percent=unrealized_percent,
                allocation_percent=_nonnegative(row.get("allocation_percent", 0.0), f"{symbol}.allocation_percent"),
                active_strategy=str(row.get("active_strategy", "Strategy A")),
                split_adjustment_factor=split_factor,
                price_source=price_source,
                status="OPEN",
            )
        )

    positions = tuple(sorted(valued, key=lambda item: item.symbol))
    invested = round(sum(position.cost_basis for position in positions), 2)
    if invested > round(account_capital, 2) + 0.01:
        raise ValueError("paper position cost basis exceeds account_capital")
    cash = round(account_capital - invested, 2)
    market_value = round(sum(position.market_value for position in positions), 2)
    portfolio_value = round(cash + market_value, 2)
    unrealized = round(market_value - invested, 2)
    return_percent = round((unrealized / account_capital) * 100.0, 6)

    return PaperPortfolioReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        account_capital=round(account_capital, 2),
        invested_capital=invested,
        cash_balance=cash,
        positions_market_value=market_value,
        portfolio_value=portfolio_value,
        unrealized_pnl=unrealized,
        portfolio_return_percent=return_percent,
        position_count=len(positions),
        positions=positions,
        warnings=tuple(warnings),
        errors=(),
    )


def write_paper_portfolio_outputs(output_dir: Path, report: PaperPortfolioReport) -> tuple[Path, Path]:
    """Atomically publish summary and valued-position evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "paper_portfolio_summary.json"
    positions_path = output_dir / "paper_portfolio_positions.json"
    summary = {key: value for key, value in asdict(report).items() if key != "positions"}
    _atomic_json(summary_path, summary)
    _atomic_json(
        positions_path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": report.generated_at,
            "paper_trade_mode": True,
            "position_count": report.position_count,
            "positions": [asdict(position) for position in report.positions],
        },
    )
    return summary_path, positions_path


def build_and_write_paper_portfolio_report(
    *,
    ledger_dir: Path = Path("results/paper_ledger"),
    data_dir: Path = Path("data"),
    output_dir: Path | None = None,
    account_capital: float,
    as_of: date | None = None,
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
) -> PaperPortfolioReport:
    report = build_paper_portfolio_report(
        ledger_dir=ledger_dir,
        data_dir=data_dir,
        account_capital=account_capital,
        as_of=as_of,
        max_price_age_days=max_price_age_days,
    )
    write_paper_portfolio_outputs(output_dir or ledger_dir, report)
    return report


def _latest_completed_adjusted_close(
    path: Path,
    as_of: date,
    *,
    entry_date: date,
    max_price_age_days: int,
) -> tuple[date, float, float, str]:
    if not path.exists():
        raise FileNotFoundError(f"market data missing: {path}")
    rows: list[tuple[date, float, float | None]] = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f"market data has no headers: {path}")
        names = {name.strip().lower().replace("_", " "): name for name in reader.fieldnames}
        if "date" not in names or "close" not in names:
            raise ValueError(f"market data must contain Date and Close: {path}")
        adj_name = names.get("adj close")
        seen: dict[date, tuple[float, float | None]] = {}
        for row in reader:
            bar_date = date.fromisoformat(str(row[names["date"]]).strip()[:10])
            close = _positive(row[names["close"]], f"{path.name}.{bar_date}.Close")
            adjusted = None
            if adj_name and str(row.get(adj_name, "")).strip() != "":
                adjusted = _positive(row[adj_name], f"{path.name}.{bar_date}.Adj Close")
            current = (close, adjusted)
            if bar_date in seen and seen[bar_date] != current:
                raise ValueError(f"conflicting duplicate market-data date: {path}:{bar_date}")
            seen[bar_date] = current
        rows = [(day, values[0], values[1]) for day, values in sorted(seen.items()) if day <= as_of]

    if not rows:
        raise ValueError(f"no completed bars available: {path}")
    latest_date, latest_close, latest_adjusted = rows[-1]
    age_days = (as_of - latest_date).days
    if age_days > max_price_age_days:
        raise ValueError(
            f"stale market data for {path.stem}: latest={latest_date}, as_of={as_of}, age_days={age_days}"
        )

    current_price = latest_adjusted if latest_adjusted is not None else latest_close
    price_source = "ADJ_CLOSE" if latest_adjusted is not None else "CLOSE"

    # Split inference requires a bar at or before the ledger entry date. Some
    # valid datasets begin after the paper entry date (for example a shortened
    # fixture or a newly downloaded history window). In that case valuation is
    # still safe, but there is no evidence for a corporate-action adjustment,
    # so preserve the ledger shares and entry price with factor 1.0.
    entry_candidates = [row for row in rows if row[0] <= entry_date]
    if not entry_candidates:
        return latest_date, round(current_price, 12), 1.0, price_source

    _, entry_close, entry_adjusted = entry_candidates[-1]
    split_factor = 1.0
    if entry_adjusted is not None:
        ratio = entry_close / entry_adjusted
        nearest = round(ratio)
        if nearest >= 1 and math.isclose(ratio, nearest, rel_tol=0.0, abs_tol=0.02):
            split_factor = float(nearest)
        elif math.isclose(ratio, 1.0, rel_tol=0.0, abs_tol=0.02):
            split_factor = 1.0
        else:
            raise ValueError(
                f"unsupported corporate-action adjustment ratio for {path.stem}: {ratio:.8f}"
            )
    return latest_date, round(current_price, 12), split_factor, price_source


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO date") from exc


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
