"""Monthly promotion governance for frozen Primary/Shadow strategy stacks.

Frozen strategy evidence is reviewed with the same five Version-1 promotion gates
used by the manual Strategy Lab, but with separate state/history/lifecycle files so
frozen engine assignments cannot be accidentally mutated by the legacy registry
promotion path. A qualified frozen Shadow enters a three-day (configured) veto
window. After the deadline it is promoted automatically unless an active user veto
exists for the symbol. Promotion swaps strategy authority only; capital and shares
remain with the existing paper position.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks, promote_frozen_shadow
from .frozen_strategy_operational_workflow import DEFAULT_PERFORMANCE_PATH
from .manual_strategy_shadow_runner import DEFAULT_ALLOCATION_PATH, _allocation, _load_json
from .shadow_promotion_lifecycle import PENDING_VETO, PROMOTED, VETOED, PromotionLifecycleEvent, load_promotion_lifecycle
from .shadow_promotion_qualification import PromotionPerformance, review_and_queue_qualified_shadow
from .user_veto_control import DEFAULT_LEDGER_PATH as DEFAULT_VETO_LEDGER_PATH, active_vetoes, load_veto_ledger

DEFAULT_MONTHLY_STATE_PATH = Path("results/frozen_shadow_promotion_monthly_review_state.json")
DEFAULT_REVIEW_REPORT_PATH = Path("results/frozen_shadow_promotion_review_report.json")
DEFAULT_REVIEW_HISTORY_PATH = Path("results/frozen_shadow_promotion_review_history.json")
DEFAULT_LIFECYCLE_PATH = Path("results/frozen_shadow_promotion_lifecycle.json")
VETO_WINDOW_ENV = "SWING_SHADOW_PROMOTION_VETO_WINDOW_DAYS"
EVIDENCE_BASIS = "SAME_PRIMARY_SHARE_QUANTITY_SAME_INTRADAY_HISTORY_SIMULATION"
NORMALIZATION_BASIS = "CURRENT_SWING_ALLOCATION"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
AFFIRMATIVE_APPROVAL_REQUIRED = False
USER_VETO_ALLOWED = True
AUTO_PROMOTION_AFTER_VETO_DEADLINE = True


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def _parse_now(now: str | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    text = now.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("now must include timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _veto_window_days(explicit: int | None) -> int | None:
    if explicit is not None:
        if explicit <= 0:
            raise ValueError("veto_window_days must be positive")
        return explicit
    raw = os.environ.get(VETO_WINDOW_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{VETO_WINDOW_ENV} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{VETO_WINDOW_ENV} must be a positive integer")
    return value


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "registry_type": "FROZEN_ENGINE",
            "last_review_period_by_symbol": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("strategy_id") != "SWING-001" or payload.get("paper_trade_mode") is not True:
        raise ValueError("invalid frozen monthly promotion state")
    if not isinstance(payload.get("last_review_period_by_symbol"), dict):
        raise ValueError("last_review_period_by_symbol must be an object")
    return payload


def _performance_rows(path: Path) -> dict[tuple[str, str], Mapping[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {}
    output: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("evidence_status") != "AVAILABLE":
            continue
        symbol = str(row.get("underlying_symbol", "")).strip().upper()
        strategy_id = str(row.get("strategy_id", "")).strip().upper()
        if symbol and strategy_id:
            output[(symbol, strategy_id)] = row
    return output


def _common_quantity(rows: list[Mapping[str, Any]]) -> float | None:
    values: list[float] = []
    for row in rows:
        if str(row.get("sizing_basis", "")) != "PRIMARY_SHARE_QUANTITY":
            return None
        try:
            reference = float(row.get("primary_reference_quantity"))
            test = float(row.get("shadow_test_quantity"))
        except (TypeError, ValueError):
            return None
        if not math.isclose(reference, test, rel_tol=0.0, abs_tol=1e-8):
            return None
        values.append(reference)
    if not values or any(not math.isclose(value, values[0], rel_tol=0.0, abs_tol=1e-8) for value in values[1:]):
        return None
    return values[0]


def _canonical(strategy_id: str, allocation: float, row: Mapping[str, Any], *, order: int = 0) -> PromotionPerformance:
    if allocation <= 0:
        raise ValueError("allocation must be positive")
    gross_profit = float(row.get("gross_profit", 0.0))
    gross_loss = float(row.get("gross_loss", 0.0))
    raw_pf = row.get("profit_factor")
    pf = (math.inf if gross_profit > 0 and gross_loss == 0 else 0.0) if raw_pf is None else float(raw_pf)
    return PromotionPerformance(
        strategy_id=strategy_id,
        total_return=round(float(row.get("net_pl", 0.0)) / allocation * 100.0, 6),
        profit_factor=pf,
        max_drawdown=round(abs(float(row.get("max_drawdown", 0.0))) / allocation * 100.0, 6),
        trade_count=int(row.get("trade_count", 0)),
        shadow_order=order,
    )


def build_frozen_monthly_promotion_review(
    *,
    now: str | None = None,
    veto_window_days: int | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    performance_path: Path = DEFAULT_PERFORMANCE_PATH,
    allocation_path: Path = DEFAULT_ALLOCATION_PATH,
    monthly_state_path: Path = DEFAULT_MONTHLY_STATE_PATH,
    review_report_path: Path = DEFAULT_REVIEW_REPORT_PATH,
    review_history_path: Path = DEFAULT_REVIEW_HISTORY_PATH,
    lifecycle_path: Path = DEFAULT_LIFECYCLE_PATH,
) -> dict[str, Any]:
    current = _parse_now(now)
    review_period = current.strftime("%Y-%m")
    window = _veto_window_days(veto_window_days)
    state = _load_state(monthly_state_path)
    last_periods = {str(key).upper(): str(value) for key, value in state["last_review_period_by_symbol"].items()}
    evidence = _performance_rows(performance_path)
    allocations = _load_json(allocation_path)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    changed = False

    for stack in load_frozen_symbol_stacks(config_path):
        shadow_ids = [item.strategy_id for item in stack.shadows if item.enabled]
        if not shadow_ids:
            rows.append({"underlying_symbol": stack.symbol, "status": "NO_ACTIVE_SHADOWS", "review_period": review_period})
            continue
        if last_periods.get(stack.symbol) == review_period:
            rows.append({"underlying_symbol": stack.symbol, "status": "ALREADY_REVIEWED_THIS_MONTH", "review_period": review_period})
            continue
        if window is None:
            rows.append({"underlying_symbol": stack.symbol, "status": "VETO_WINDOW_NOT_CONFIGURED", "review_period": review_period})
            warnings.append(f"{stack.symbol}: {VETO_WINDOW_ENV} is not configured; monthly counter was not changed.")
            continue
        allocation = _allocation(allocations, stack.symbol, stack.symbol)
        if allocation is None:
            rows.append({"underlying_symbol": stack.symbol, "status": "MISSING_SWING_ALLOCATION", "review_period": review_period})
            continue
        primary_row = evidence.get((stack.symbol, stack.primary.strategy_id))
        shadow_rows = [evidence.get((stack.symbol, strategy_id)) for strategy_id in shadow_ids]
        if primary_row is None or any(row is None for row in shadow_rows):
            rows.append({"underlying_symbol": stack.symbol, "status": "INCOMPLETE_FROZEN_EVIDENCE", "review_period": review_period})
            continue
        comparable_rows = [primary_row, *[row for row in shadow_rows if row is not None]]
        quantity = _common_quantity(comparable_rows)
        if quantity is None:
            rows.append({"underlying_symbol": stack.symbol, "status": "SHADOW_QUANTITY_MISMATCH", "review_period": review_period})
            continue

        primary = _canonical(stack.primary.strategy_id, allocation, primary_row)
        shadows = tuple(
            _canonical(strategy_id, allocation, row, order=order)
            for order, (strategy_id, row) in enumerate(zip(shadow_ids, shadow_rows), start=1)
            if row is not None
        )
        qualified_at = _utc_text(current)
        deadline = _utc_text(current + timedelta(days=window))
        result, queued = review_and_queue_qualified_shadow(
            underlying_symbol=stack.symbol,
            primary=primary,
            shadows=shadows,
            qualified_at=qualified_at,
            veto_deadline=deadline,
            review_history_path=review_history_path,
            lifecycle_path=lifecycle_path,
        )
        last_periods[stack.symbol] = review_period
        changed = True
        rows.append({
            "underlying_symbol": stack.symbol,
            "primary_strategy_id": stack.primary.strategy_id,
            "shadow_strategy_ids": shadow_ids,
            "review_period": review_period,
            "status": "QUALIFIED_PENDING_VETO" if queued is not None else "REVIEWED_NOT_QUALIFIED",
            "qualified_strategy_id": result.qualified_strategy_id,
            "queued_pending_veto": queued is not None,
            "primary_reference_quantity": quantity,
            "evidence_basis": EVIDENCE_BASIS,
            "normalization_basis": NORMALIZATION_BASIS,
        })

    if changed:
        state = dict(state)
        state["last_review_period_by_symbol"] = last_periods
        state["last_reviewed_at"] = _utc_text(current)
        _atomic_json(monthly_state_path, state)

    report = {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "registry_type": "FROZEN_ENGINE",
        "generated_at": _utc_text(current),
        "review_period": review_period,
        "veto_window_days": window,
        "paper_trade_mode": True,
        "affirmative_approval_required": False,
        "user_veto_allowed": True,
        "rows": rows,
        "warnings": warnings,
    }
    _atomic_json(review_report_path, report)
    return report


def process_frozen_pending_promotions(
    *,
    now: str | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    lifecycle_path: Path = DEFAULT_LIFECYCLE_PATH,
    veto_ledger_path: Path = DEFAULT_VETO_LEDGER_PATH,
) -> tuple[PromotionLifecycleEvent, ...]:
    """Resolve expired frozen promotion events by veto-by-exception governance."""
    current = _parse_now(now)
    current_text = _utc_text(current)
    payload = load_promotion_lifecycle(lifecycle_path)
    lifecycle_rows = list(payload["events"])
    vetoed_symbols = set(active_vetoes(load_veto_ledger(veto_ledger_path)))
    resolved: list[PromotionLifecycleEvent] = []
    changed = False

    for index, raw in enumerate(lifecycle_rows):
        if not isinstance(raw, Mapping) or raw.get("status") != PENDING_VETO:
            continue
        event = PromotionLifecycleEvent(**dict(raw))
        deadline = _parse_now(event.veto_deadline)
        if current < deadline:
            continue
        if event.underlying_symbol in vetoed_symbols:
            final = PromotionLifecycleEvent(
                underlying_symbol=event.underlying_symbol,
                strategy_id=event.strategy_id,
                status=VETOED,
                qualified_at=event.qualified_at,
                veto_deadline=event.veto_deadline,
                resolved_at=current_text,
                qualification_evidence=event.qualification_evidence,
            )
        else:
            previous = promote_frozen_shadow(symbol=event.underlying_symbol, strategy_id=event.strategy_id, path=config_path)
            final = PromotionLifecycleEvent(
                underlying_symbol=event.underlying_symbol,
                strategy_id=event.strategy_id,
                status=PROMOTED,
                qualified_at=event.qualified_at,
                veto_deadline=event.veto_deadline,
                resolved_at=current_text,
                previous_direct_strategy_id=previous,
                qualification_evidence=event.qualification_evidence,
            )
        lifecycle_rows[index] = asdict(final)
        resolved.append(final)
        changed = True

    if changed:
        updated = dict(payload)
        updated["events"] = lifecycle_rows
        _atomic_json(lifecycle_path, updated)
    return tuple(resolved)
