"""Publish read-only Swing Enterprise KPI evidence for the existing AI CIO host.

Version 2 combines strategy-specific allocation, paper-ledger valuation, holdings,
trade-history, performance, watchlist, and opportunity-quality evidence. Missing
optional evidence is disclosed and never fabricated. This module never imports
host production code, connects to a broker, places orders, or moves capital.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "enterprise_strategy_kpi_publisher"
MODULE_VERSION = "2.0.0"
SCHEMA_VERSION = "2.0"
KPI_CONTRACT_VERSION = "2.0"
STRATEGY_ID = "SWING-001"
DEFAULT_STRATEGY_ALLOCATIONS_PATH = Path("results/enterprise_strategy_allocations.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False

CAPABILITIES = (
    "opportunity_quality",
    "paper_holdings",
    "paper_performance",
    "paper_portfolio",
    "portfolio_allocations",
    "strategy_kpis",
    "trade_history",
    "watchlist",
)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _load_first(root: Path, names: Sequence[str]) -> tuple[dict[str, Any] | None, str | None]:
    for name in names:
        payload = _load_json(root / name)
        if payload is not None:
            return payload, name
    return None, None


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonnegative(value: object) -> float | None:
    number = _finite(value)
    return number if number is not None and number >= 0 else None


def _find_numeric(payload: Mapping[str, Any] | None, keys: Sequence[str], *, signed: bool = False) -> float | None:
    if not payload:
        return None
    for key in keys:
        value = _finite(payload.get(key)) if signed else _nonnegative(payload.get(key))
        if value is not None:
            return value
    for value in payload.values():
        if isinstance(value, Mapping):
            found = _find_numeric(value, keys, signed=signed)
            if found is not None:
                return found
    return None


def _strategy_allocations_mapping(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("strategy_allocations")
    return nested if isinstance(nested, Mapping) else payload


def resolve_strategy_allocation(strategy_allocations: Mapping[str, Any], strategy_id: str = STRATEGY_ID) -> float:
    allocated = _nonnegative(_strategy_allocations_mapping(strategy_allocations).get(strategy_id))
    if allocated is None:
        raise ValueError(f"strategy_allocations[{strategy_id!r}] is required")
    return allocated


def _require_safe_source(payload: Mapping[str, Any] | None, name: str) -> None:
    if payload is None:
        return
    if payload.get("paper_trade_mode") is not True:
        raise ValueError(f"{name}.paper_trade_mode must be true")
    for field in (
        "live_trading_enabled", "broker_execution_enabled", "order_placement_enabled",
        "capital_movement_enabled", "direct_database_writes",
    ):
        if payload.get(field, False) is not False:
            raise ValueError(f"{name}.{field} has unsafe value")


def _active_positions(allocations: Mapping[str, Any] | None) -> int | None:
    rows = allocations.get("allocations") if allocations else None
    if not isinstance(rows, list):
        return None
    return sum(
        1 for row in rows
        if isinstance(row, Mapping)
        and (_nonnegative(row.get("allocation_percent")) or 0) > 0
        and str(row.get("confidence_level", "")).upper() != "RESERVE"
        and not bool(str(row.get("cash_equivalent", "")).strip())
    )


def _validated_portfolio(payload: Mapping[str, Any] | None, allocated: float) -> dict[str, Any] | None:
    if not payload:
        return None
    _require_safe_source(payload, "paper_portfolio_summary")
    if payload.get("valuation_source") != "PAPER_LEDGER_MARK_TO_MARKET":
        return None
    account_capital = _nonnegative(payload.get("account_capital"))
    if account_capital is None or abs(account_capital - allocated) > 0.01:
        raise ValueError("paper ledger account_capital must equal the preserved SWING-001 allocation")
    required = {
        "portfolio_value": _nonnegative(payload.get("portfolio_value")),
        "cash_balance": _nonnegative(payload.get("cash_balance")),
        "invested_capital": _nonnegative(payload.get("invested_capital")),
        "positions_market_value": _nonnegative(payload.get("positions_market_value")),
        "unrealized_pnl": _finite(payload.get("unrealized_pnl")),
        "portfolio_return_percent": _finite(payload.get("portfolio_return_percent")),
    }
    if any(value is None for value in required.values()):
        return None
    position_count = payload.get("position_count")
    if not isinstance(position_count, int) or position_count < 0:
        return None
    return {**required, "position_count": position_count}


def _holdings(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    _require_safe_source(payload, "paper_portfolio_positions")
    rows = payload.get("positions") or payload.get("holdings")
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        shares = _nonnegative(row.get("shares"))
        if not symbol or shares is None or shares <= 0:
            continue
        output.append({
            "symbol": symbol,
            "shares": round(shares, 8),
            "entry_price": _nonnegative(row.get("entry_price") or row.get("average_cost")),
            "current_price": _nonnegative(row.get("current_price")),
            "market_value": _nonnegative(row.get("market_value")),
            "unrealized_pnl": _finite(row.get("unrealized_pnl")),
            "unrealized_pnl_percent": _finite(row.get("unrealized_pnl_percent")),
            "active_strategy": str(row.get("active_strategy", "")),
        })
    return sorted(output, key=lambda item: item["symbol"])


def _list_count(payload: Mapping[str, Any] | None, keys: Sequence[str]) -> int | None:
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def build_enterprise_strategy_kpis(
    results_dir: str | Path = "results",
    *,
    strategy_allocations: Mapping[str, Any],
    strategy_allocations_source: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(results_dir)
    allocations = _load_json(root / "portfolio_allocations.json")
    executive = _load_json(root / "executive_dashboard.json")
    opportunity, opportunity_name = _load_first(root, ("opportunity_quality.json", "opportunity_quality_report.json"))
    watchlist, watchlist_name = _load_first(root, ("watchlist_report.json", "watchlist.json"))
    portfolio = _load_json(root / "paper_ledger" / "paper_portfolio_summary.json")
    positions = _load_json(root / "paper_ledger" / "paper_portfolio_positions.json")
    trade_summary = _load_json(root / "paper_ledger" / "trade_history_summary.json")
    performance = _load_json(root / "paper_ledger" / "paper_performance.json")

    for name, payload in (
        ("trade_history_summary", trade_summary), ("paper_performance", performance),
    ):
        _require_safe_source(payload, name)

    allocated = resolve_strategy_allocation(strategy_allocations)
    warnings: list[str] = []
    ledger = _validated_portfolio(portfolio, allocated)

    if ledger:
        portfolio_value = round(float(ledger["portfolio_value"]), 2)
        portfolio_value_source = "PAPER_LEDGER_MARK_TO_MARKET"
        position_count = int(ledger["position_count"])
        cash_balance = round(float(ledger["cash_balance"]), 2)
        invested_capital = round(float(ledger["invested_capital"]), 2)
        positions_market_value = round(float(ledger["positions_market_value"]), 2)
        unrealized_pnl = round(float(ledger["unrealized_pnl"]), 2)
        portfolio_return = round(float(ledger["portfolio_return_percent"]), 6)
    else:
        portfolio_value = _find_numeric(executive, ("portfolio_value", "current_portfolio_value", "total_portfolio_value"))
        portfolio_value_source = "EXECUTIVE_DASHBOARD"
        if portfolio_value is None:
            portfolio_value = allocated
            portfolio_value_source = "PAPER_ALLOCATION_PROXY"
            warnings.append("Marked-to-market paper ledger is unavailable; allocated paper capital is used as a disclosed proxy.")
        position_count = _active_positions(allocations)
        if position_count is None:
            position_count = int(_find_numeric(executive, ("active_positions", "position_count")) or 0)
        cash_balance = invested_capital = positions_market_value = unrealized_pnl = portfolio_return = None

    holdings = _holdings(positions)
    if ledger and len(holdings) != position_count:
        warnings.append("Detailed holdings count does not match the paper portfolio position count.")

    realized_pnl = _find_numeric(performance, ("realized_pnl",), signed=True)
    total_pnl = _find_numeric(performance, ("total_pnl",), signed=True)
    win_rate = _find_numeric(performance, ("win_rate_percent",))
    closed_count = _list_count(performance, ("closed_trade_count",))
    if closed_count is None:
        closed_count = _list_count(trade_summary, ("closed_trade_count",))
    trade_count = _list_count(performance, ("total_trade_events", "trade_count"))
    if trade_count is None:
        trade_count = _list_count(trade_summary, ("total_trade_events", "trade_count"))

    opportunity_score = _find_numeric(opportunity, ("opportunity_quality_score", "opportunity_quality", "score"))
    watchlist_count = _list_count(watchlist, ("watchlist_count", "symbols", "watchlist", "candidates", "rows"))

    artifacts = {
        "portfolio_allocations": allocations is not None,
        "executive_dashboard": executive is not None,
        "opportunity_quality": opportunity is not None,
        "watchlist": watchlist is not None,
        "paper_portfolio_summary": portfolio is not None,
        "paper_portfolio_positions": positions is not None,
        "trade_history_summary": trade_summary is not None,
        "paper_performance": performance is not None,
    }
    available_count = sum(artifacts.values())
    evidence_status = "AVAILABLE" if ledger and performance else "PARTIAL" if ledger or allocations else "REGISTRY_ONLY"
    if performance is None:
        warnings.append("Performance analytics evidence is not yet published.")
    if win_rate is None:
        warnings.append("Win rate is not reportable until decided closed paper trades exist.")

    return {
        "schema_version": SCHEMA_VERSION,
        "kpi_contract_version": KPI_CONTRACT_VERSION,
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "strategy_id": STRATEGY_ID,
        "plugin_id": STRATEGY_ID,
        "strategy_name": "Trade Swing Bot",
        "allocated_capital": round(allocated, 2),
        "allocation_source": "STRATEGY_ALLOCATIONS",
        "strategy_allocations_source": str(strategy_allocations_source) if strategy_allocations_source else None,
        "portfolio_value": round(float(portfolio_value), 2),
        "portfolio_value_source": portfolio_value_source,
        "cash_balance": cash_balance,
        "invested_capital": invested_capital,
        "positions_market_value": positions_market_value,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "total_pnl": total_pnl,
        "portfolio_return_percent": portfolio_return,
        "position_count": int(position_count),
        "open_positions": holdings,
        "trade_count": trade_count,
        "closed_trade_count": closed_count,
        "win_rate_percent": win_rate,
        "opportunity_quality": opportunity_score,
        "watchlist_count": watchlist_count,
        "performance": performance,
        "evidence_status": evidence_status,
        "capabilities": list(CAPABILITIES),
        "artifacts": available_count,
        "artifact_availability": artifacts,
        "source_artifacts": {
            "portfolio_allocations.json": allocations is not None,
            "executive_dashboard.json": executive is not None,
            opportunity_name or "opportunity_quality.json": opportunity is not None,
            watchlist_name or "watchlist_report.json": watchlist is not None,
            "paper_ledger/paper_portfolio_summary.json": portfolio is not None,
            "paper_ledger/paper_portfolio_positions.json": positions is not None,
            "paper_ledger/trade_history_summary.json": trade_summary is not None,
            "paper_ledger/paper_performance.json": performance is not None,
        },
        "warnings": sorted(set(warnings)),
        "errors": [],
        "paper_trade_mode": True,
        "paper_compatible": True,
        "advisory_only": True,
        "reporting_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "capital_movement_enabled": False,
        "order_placement_enabled": False,
        "automatic_activation_allowed": False,
        "governance_review_required": True,
        "direct_database_writes": False,
    }


def validate_enterprise_strategy_kpis(payload: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if payload.get("strategy_id") != STRATEGY_ID:
        errors.append("strategy_id must be SWING-001")
    if payload.get("kpi_contract_version") != KPI_CONTRACT_VERSION:
        errors.append("kpi_contract_version must be 2.0")
    if payload.get("allocation_source") != "STRATEGY_ALLOCATIONS":
        errors.append("allocation_source must be STRATEGY_ALLOCATIONS")
    if payload.get("evidence_status") not in {"AVAILABLE", "PARTIAL", "REGISTRY_ONLY"}:
        errors.append("unsupported evidence_status")
    for field in ("allocated_capital", "portfolio_value"):
        if _nonnegative(payload.get(field)) is None:
            errors.append(f"{field} must be finite and nonnegative")
    if payload.get("portfolio_value_source") == "PAPER_ALLOCATION_PROXY" and payload.get("portfolio_value") != payload.get("allocated_capital"):
        errors.append("PAPER_ALLOCATION_PROXY must equal allocated_capital")
    if payload.get("portfolio_value_source") == "PAPER_LEDGER_MARK_TO_MARKET":
        for field in ("cash_balance", "invested_capital", "positions_market_value"):
            if _nonnegative(payload.get(field)) is None:
                errors.append(f"{field} is required for PAPER_LEDGER_MARK_TO_MARKET")
    if not isinstance(payload.get("position_count"), int) or payload.get("position_count", -1) < 0:
        errors.append("position_count must be a nonnegative integer")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or capabilities != sorted(set(capabilities)):
        errors.append("capabilities must be deterministic, sorted, and unique")
    holdings = payload.get("open_positions")
    if not isinstance(holdings, list):
        errors.append("open_positions must be a list")
    for field in ("paper_trade_mode", "paper_compatible", "advisory_only", "reporting_only", "governance_review_required"):
        if payload.get(field) is not True:
            errors.append(f"{field} must be true")
    for field in ("live_trading_enabled", "broker_execution_enabled", "capital_movement_enabled", "order_placement_enabled", "automatic_activation_allowed", "direct_database_writes"):
        if payload.get(field) is not False:
            errors.append(f"{field} must be false")
    return tuple(errors)


def write_enterprise_strategy_kpis(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    errors = validate_enterprise_strategy_kpis(payload)
    if errors:
        raise ValueError("Invalid Swing enterprise KPI evidence: " + "; ".join(errors))
    path = Path(output_path)
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
    return path


def build_and_write_enterprise_strategy_kpis(
    results_dir: str | Path = "results",
    output_path: str | Path = "results/enterprise_strategy_kpis.json",
    *,
    strategy_allocations_path: str | Path = DEFAULT_STRATEGY_ALLOCATIONS_PATH,
) -> Path:
    allocation_path = Path(strategy_allocations_path)
    strategy_allocations = _load_json(allocation_path)
    if strategy_allocations is None:
        raise FileNotFoundError(f"Strategy allocation evidence not found: {allocation_path}")
    payload = build_enterprise_strategy_kpis(
        results_dir,
        strategy_allocations=strategy_allocations,
        strategy_allocations_source=allocation_path,
    )
    return write_enterprise_strategy_kpis(payload, output_path)
