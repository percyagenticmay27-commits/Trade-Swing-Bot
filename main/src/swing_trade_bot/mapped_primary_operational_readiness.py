"""Fail-closed operational-readiness audit for mapped frozen Primary stacks.

This module is advisory and paper-only. It does not run the daily cycle, generate
signals, mutate paper positions, allocate capital, or create execution authority.
It verifies that a mapped underlying-signal / leveraged-paper-vehicle stack has
sufficient market-data, ledger, committee, confidence, and allocation evidence
before the normal governed daily cycle is allowed to consume it.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .frozen_primary_confidence_adapter import build_forward_primary_confidence_metrics
from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, resolve_frozen_stack
from .intraday_chart_bars import build_chart_bars, load_intraday_csv, regular_session_rows

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    passed: bool
    status: str
    detail: str


def audit_mapped_primary_operational_readiness(
    symbol: str,
    *,
    root: Path = Path("."),
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Audit one frozen mapped Primary without mutating any runtime artifacts."""
    root = Path(root)
    config_path = config_path if config_path.is_absolute() else root / config_path
    target = symbol.strip().upper()
    stack = resolve_frozen_stack(target, config_path)
    if stack is None:
        raise ValueError(f"no frozen stack for {target}")
    primary = stack.primary
    if primary.signal_symbol == primary.vehicle_symbol:
        raise ValueError("mapped readiness audit requires distinct signal and vehicle symbols")

    checks: list[ReadinessCheck] = []
    intraday_dir = root / "data" / "intraday"
    signal_path = intraday_dir / f"{primary.signal_symbol}.csv"
    vehicle_path = intraday_dir / f"{primary.vehicle_symbol}.csv"

    market = _market_data_status(signal_path, vehicle_path, primary.timeframe)
    checks.append(ReadinessCheck(
        "market_data",
        market["ready"],
        "READY" if market["ready"] else "BLOCKED",
        market["detail"],
    ))

    ledger_dir = root / "results" / "paper_ledger"
    ledger = _ledger_status(ledger_dir, primary.vehicle_symbol, primary.strategy_id)
    checks.append(ReadinessCheck(
        "paper_ledger",
        ledger["ready"],
        "READY" if ledger["ready"] else "BLOCKED",
        ledger["detail"],
    ))

    committee = _committee_status(
        root / "results" / "committee_allocation_eligibility.json",
        primary.signal_symbol,
        primary.vehicle_symbol,
    )
    checks.append(ReadinessCheck(
        "committee_governance",
        committee["artifact_valid"],
        committee["status"],
        committee["detail"],
    ))

    forward = _forward_confidence_status(
        ledger_dir=ledger_dir,
        config_path=config_path,
        watchlist_path=root / "results" / "watchlist_report.json",
        allocation_symbol=committee.get("allocation_symbol") or primary.signal_symbol,
        vehicle_symbol=primary.vehicle_symbol,
        strategy_id=primary.strategy_id,
        confidence_path=root / "results" / "confidence_report.json",
    )
    checks.append(ReadinessCheck(
        "forward_primary_confidence",
        forward["ready"],
        "READY" if forward["ready"] else "BLOCKED",
        forward["detail"],
    ))

    allocation = _allocation_status(
        root / "results" / "portfolio_allocations.json",
        committee.get("allocation_symbol") or primary.signal_symbol,
        committee_eligible=bool(committee.get("eligible_for_allocation")),
    )
    checks.append(ReadinessCheck(
        "governed_allocation",
        allocation["ready"],
        "READY" if allocation["ready"] else "BLOCKED",
        allocation["detail"],
    ))

    blockers = [check.name for check in checks if not check.passed]
    # Committee ineligibility is a valid governed HOLD/REJECT state, not a runtime
    # defect. The artifact itself must be valid, while allocation must remain absent.
    runtime_ready = market["ready"] and ledger["ready"] and committee["artifact_valid"] and forward["ready"] and allocation["ready"]
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "symbol": target,
        "signal_symbol": primary.signal_symbol,
        "vehicle_symbol": primary.vehicle_symbol,
        "primary_strategy_id": primary.strategy_id,
        "timeframe": primary.timeframe,
        "runtime_ready": runtime_ready,
        "committee_eligible_for_allocation": committee.get("eligible_for_allocation"),
        "committee_reason_code": committee.get("reason_code"),
        "forward_primary_trade_count": forward.get("trade_count"),
        "current_confidence": forward.get("confidence"),
        "current_allocation_percent": allocation.get("allocation_percent"),
        "open_vehicle_position": ledger.get("open_position"),
        "checks": [asdict(check) for check in checks],
        "blockers": blockers,
        "daily_cycle_authorized_by_this_audit": False,
    }


def _market_data_status(signal_path: Path, vehicle_path: Path, timeframe: str) -> dict[str, Any]:
    if not signal_path.is_file() or not vehicle_path.is_file():
        missing = [str(path) for path in (signal_path, vehicle_path) if not path.is_file()]
        return {"ready": False, "detail": f"missing intraday data: {', '.join(missing)}"}
    try:
        signal_rows = regular_session_rows(load_intraday_csv(signal_path))
        vehicle_rows = regular_session_rows(load_intraday_csv(vehicle_path))
        signal_chart = build_chart_bars(signal_rows, timeframe)  # type: ignore[arg-type]
        vehicle_chart = build_chart_bars(vehicle_rows, timeframe)  # type: ignore[arg-type]
    except (OSError, ValueError, TypeError) as exc:
        return {"ready": False, "detail": f"market data error: {type(exc).__name__}: {exc}"}
    if not signal_rows or not vehicle_rows or not signal_chart or not vehicle_chart:
        return {"ready": False, "detail": "signal/vehicle RTH evidence does not produce chart bars"}
    signal_buckets = {row.timestamp for row in signal_chart}
    vehicle_buckets = {row.timestamp for row in vehicle_chart}
    overlap = len(signal_buckets & vehicle_buckets)
    if overlap == 0:
        return {"ready": False, "detail": "signal and vehicle have zero overlapping chart buckets"}
    return {
        "ready": True,
        "detail": (
            f"{signal_path.name}: {len(signal_rows)} RTH rows/{len(signal_chart)} {timeframe} bars; "
            f"{vehicle_path.name}: {len(vehicle_rows)} RTH rows/{len(vehicle_chart)} {timeframe} bars; "
            f"overlap={overlap} buckets"
        ),
    }


def _ledger_status(ledger_dir: Path, vehicle_symbol: str, strategy_id: str) -> dict[str, Any]:
    open_path = ledger_dir / "open_positions.json"
    history_path = ledger_dir / "trade_history.json"
    closed_path = ledger_dir / "closed_positions.json"
    missing = [str(path) for path in (open_path, history_path, closed_path) if not path.is_file()]
    if missing:
        return {"ready": False, "open_position": None, "detail": f"missing paper-ledger artifacts: {', '.join(missing)}"}
    try:
        open_payload = _load(open_path)
        history_payload = _load(history_path)
        closed_payload = _load(closed_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"ready": False, "open_position": None, "detail": f"ledger error: {type(exc).__name__}: {exc}"}
    for name, payload in (("open_positions", open_payload), ("trade_history", history_payload), ("closed_positions", closed_payload)):
        if payload.get("paper_trade_mode", True) is not True:
            return {"ready": False, "open_position": None, "detail": f"{name} is not paper_trade_mode=true"}
    positions = open_payload.get("positions", [])
    trades = history_payload.get("trades", [])
    closed = closed_payload.get("closed_trades", [])
    if not isinstance(positions, list) or not isinstance(trades, list) or not isinstance(closed, list):
        return {"ready": False, "open_position": None, "detail": "paper-ledger list contract is invalid"}
    matching_positions = [row for row in positions if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == vehicle_symbol]
    if len(matching_positions) > 1:
        return {"ready": False, "open_position": None, "detail": f"duplicate open {vehicle_symbol} paper positions"}
    current = matching_positions[0] if matching_positions else None
    if current is not None:
        active = str(current.get("active_strategy", "")).strip().upper()
        if active != strategy_id:
            return {"ready": False, "open_position": True, "detail": f"open {vehicle_symbol} position belongs to {active or 'UNKNOWN'}, not current Primary"}
    history_count = sum(1 for row in trades if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == vehicle_symbol)
    return {"ready": True, "open_position": current is not None, "detail": f"paper ledger valid; open_position={current is not None}; vehicle trade-history rows={history_count}"}


def _committee_status(path: Path, signal_symbol: str, vehicle_symbol: str) -> dict[str, Any]:
    if not path.is_file():
        return {"artifact_valid": False, "status": "BLOCKED", "detail": f"missing {path}", "eligible_for_allocation": False}
    payload = _load(path)
    if payload.get("paper_trade_mode") is not True or not isinstance(payload.get("rows"), list):
        return {"artifact_valid": False, "status": "BLOCKED", "detail": "committee artifact contract invalid", "eligible_for_allocation": False}
    matches = []
    for row in payload["rows"]:
        if not isinstance(row, Mapping):
            continue
        values = {
            str(row.get("symbol", "")).strip().upper(),
            str(row.get("underlying_symbol", "")).strip().upper(),
            str(row.get("leveraged_symbol", "")).strip().upper(),
        }
        if signal_symbol in values or vehicle_symbol in values:
            matches.append(row)
    if len(matches) != 1:
        return {"artifact_valid": False, "status": "BLOCKED", "detail": f"expected one committee row; found {len(matches)}", "eligible_for_allocation": False}
    row = matches[0]
    allocation_symbol = str(row.get("underlying_symbol") or row.get("symbol") or signal_symbol).strip().upper()
    eligible = row.get("eligible_for_allocation") is True
    reason = str(row.get("reason_code", ""))
    return {
        "artifact_valid": True,
        "status": "ELIGIBLE" if eligible else "GOVERNED_HOLD_OR_REJECT",
        "detail": f"OQ={row.get('opportunity_quality_score')}; Entry={row.get('entry_score')}; thesis={row.get('thesis_intact')}; reason={reason}",
        "eligible_for_allocation": eligible,
        "reason_code": reason,
        "allocation_symbol": allocation_symbol,
    }


def _forward_confidence_status(*, ledger_dir: Path, config_path: Path, watchlist_path: Path, allocation_symbol: str, vehicle_symbol: str, strategy_id: str, confidence_path: Path) -> dict[str, Any]:
    closed_path = ledger_dir / "closed_positions.json"
    if not closed_path.is_file() or not watchlist_path.is_file():
        return {"ready": False, "detail": "forward-confidence source artifacts are missing", "trade_count": None, "confidence": None}
    try:
        metrics = build_forward_primary_confidence_metrics(closed_positions_path=closed_path, config_path=config_path, watchlist_path=watchlist_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"ready": False, "detail": f"forward-confidence evidence error: {type(exc).__name__}: {exc}", "trade_count": None, "confidence": None}
    matches = [row for row in metrics if row.vehicle_symbol == vehicle_symbol and row.strategy_id == strategy_id]
    if len(matches) != 1:
        return {"ready": False, "detail": f"expected one current-Primary confidence metric; found {len(matches)}", "trade_count": None, "confidence": None}
    metric = matches[0]
    confidence = None
    if confidence_path.is_file():
        payload = _load(confidence_path)
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == allocation_symbol:
                    confidence = str(row.get("confidence", "")).strip().upper() or None
                    break
    if metric.number_of_trades == 0 and confidence not in (None, "LOW"):
        return {"ready": False, "detail": f"zero current-Primary forward trades but confidence={confidence}; expected LOW or absent", "trade_count": 0, "confidence": confidence}
    return {
        "ready": True,
        "detail": f"current Primary forward trades={metric.number_of_trades}; confidence={confidence or 'NOT_YET_PUBLISHED'}; historical/shadow evidence excluded",
        "trade_count": metric.number_of_trades,
        "confidence": confidence,
    }


def _allocation_status(path: Path, allocation_symbol: str, *, committee_eligible: bool) -> dict[str, Any]:
    if not path.is_file():
        return {"ready": not committee_eligible, "detail": "allocation artifact absent" if not committee_eligible else "eligible symbol has no allocation artifact", "allocation_percent": None}
    payload = _load(path)
    if payload.get("paper_trade_mode") is not True or not isinstance(payload.get("allocations"), list):
        return {"ready": False, "detail": "portfolio allocation artifact contract invalid", "allocation_percent": None}
    rows = [row for row in payload["allocations"] if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == allocation_symbol]
    if not committee_eligible and rows:
        return {"ready": False, "detail": f"ineligible {allocation_symbol} has an allocation row", "allocation_percent": rows[0].get("allocation_percent")}
    if committee_eligible and not rows:
        return {"ready": False, "detail": f"eligible {allocation_symbol} has no governed allocation row", "allocation_percent": None}
    allocation = rows[0].get("allocation_percent") if rows else None
    return {"ready": True, "detail": f"allocation row {'present' if rows else 'correctly absent'}; allocation_percent={allocation}", "allocation_percent": allocation}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit mapped frozen Primary operational readiness")
    parser.add_argument("symbol", help="paper vehicle symbol, e.g. NVDX")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = audit_mapped_primary_operational_readiness(args.symbol, root=args.root)
    print(json.dumps(report, indent=2))
    return 0 if report["runtime_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
