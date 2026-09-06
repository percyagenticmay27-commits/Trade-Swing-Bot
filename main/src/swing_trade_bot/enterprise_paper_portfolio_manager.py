"""Phase 2 portfolio valuation using normalized AI CIO market data.

Existing valuation formulas are preserved. Provider selection stays in the
Dividend AI CIO; Swing reads fresh normalized evidence only.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .enterprise_market_data_client import EnterpriseMarketDataClient, MarketDataUnavailable
from .paper_portfolio_manager import PaperPortfolioReport, ValuedPaperPosition, write_paper_portfolio_outputs

STRATEGY_ID = "SWING-001"
SWING_ALLOCATION = 4500.0


def build_enterprise_paper_portfolio_report(
    *,
    ledger_dir: Path,
    account_capital: float,
    client: EnterpriseMarketDataClient,
) -> PaperPortfolioReport:
    """Mark open positions with fresh normalized Enterprise quotes."""
    if not math.isfinite(account_capital) or account_capital <= 0:
        raise ValueError("account_capital must be finite and positive")
    if round(account_capital, 2) != SWING_ALLOCATION:
        raise ValueError("SWING-001 account_capital must remain 4500.00")

    source = _load_json(Path(ledger_dir) / "open_positions.json")
    rows = source.get("positions")
    if not isinstance(rows, list):
        raise ValueError("open_positions.json must contain a positions list")

    valued: list[ValuedPaperPosition] = []
    warnings: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each open position must be a JSON object")
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("open position symbol is required")
        shares = _positive(row.get("shares"), f"{symbol}.shares")
        entry_price = _positive(row.get("entry_price"), f"{symbol}.entry_price")
        cost_basis = _nonnegative(row.get("cost_basis"), f"{symbol}.cost_basis")
        quote = client.get_quote(symbol, required=True)
        assert quote is not None
        market_value = round(shares * quote.price, 2)
        unrealized = round(market_value - cost_basis, 2)
        unrealized_percent = round((unrealized / cost_basis) * 100.0, 6) if cost_basis else 0.0
        warnings.extend(quote.warnings)
        valued.append(
            ValuedPaperPosition(
                symbol=symbol,
                entry_date=str(row.get("entry_date", "")),
                entry_price=entry_price,
                shares=shares,
                cost_basis=cost_basis,
                current_price=quote.price,
                price_date=quote.trading_date,
                market_value=market_value,
                unrealized_pnl=unrealized,
                unrealized_pnl_percent=unrealized_percent,
                allocation_percent=_nonnegative(row.get("allocation_percent", 0.0), f"{symbol}.allocation_percent"),
                active_strategy=str(row.get("active_strategy", "Strategy A")),
                split_adjustment_factor=1.0,
                price_source="ENTERPRISE_NORMALIZED_QUOTE",
                status="OPEN",
            )
        )

    positions = tuple(sorted(valued, key=lambda item: item.symbol))
    invested = round(sum(position.cost_basis for position in positions), 2)
    if invested > round(account_capital, 2) + 0.01:
        raise ValueError("paper position cost basis exceeds account_capital")
    cash = round(account_capital - invested, 2)
    positions_market_value = round(sum(position.market_value for position in positions), 2)
    portfolio_value = round(cash + positions_market_value, 2)
    unrealized = round(positions_market_value - invested, 2)
    return_percent = round((unrealized / account_capital) * 100.0, 6)

    return PaperPortfolioReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        account_capital=round(account_capital, 2),
        invested_capital=invested,
        cash_balance=cash,
        positions_market_value=positions_market_value,
        portfolio_value=portfolio_value,
        unrealized_pnl=unrealized,
        portfolio_return_percent=return_percent,
        position_count=len(positions),
        positions=positions,
        warnings=tuple(dict.fromkeys(warnings)),
        errors=(),
        valuation_source="ENTERPRISE_MARKET_DATA_PROVIDER_V1",
    )


def build_and_write_enterprise_paper_portfolio_report(
    *, ledger_dir: Path, output_dir: Path, account_capital: float,
    client: EnterpriseMarketDataClient,
) -> PaperPortfolioReport:
    report = build_enterprise_paper_portfolio_report(
        ledger_dir=ledger_dir, account_capital=account_capital, client=client
    )
    write_paper_portfolio_outputs(output_dir, report)
    return report


def write_blocked_state(output_dir: Path, error: Exception) -> Path:
    """Publish an explicit SWING-001-only blocked-state artifact."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "enterprise_market_data_blocked.json"
    payload = {
        "strategy_id": STRATEGY_ID,
        "status": "BLOCKED",
        "reason": str(error),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_data_dependent_publication_allowed": False,
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "allocated_capital": SWING_ALLOCATION,
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists(): raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict): raise ValueError(f"expected JSON object: {path}")
    return payload


def _positive(value: Any, field: str) -> float:
    number = _nonnegative(value, field)
    if number <= 0: raise ValueError(f"{field} must be positive")
    return number


def _nonnegative(value: Any, field: str) -> float:
    try: number = float(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0: raise ValueError(f"{field} must be finite and nonnegative")
    return number
