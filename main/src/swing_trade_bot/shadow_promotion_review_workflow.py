"""Monthly paper-only Primary-versus-Shadow promotion review workflow.

Promotion evidence is produced on an apples-to-apples research basis: the current
DIRECT strategy and each SHADOW strategy are simulated against the same verified
mapped vehicle, the same market-history span, and the exact same current Primary
paper-position share quantity. Current Swing dollar allocation is retained only
as a common return/drawdown normalization denominator; it is not Shadow sizing
authority. The actual DIRECT paper portfolio remains the capital authority; this
module never creates positions, reserves/moves capital, or places orders.

The workflow runs at most once per calendar month per underlying. This protects the
frozen "three consecutive reviews" gate from being incremented by a daily Swing
cycle. A veto-window duration must be supplied explicitly (or through the
SWING_SHADOW_PROMOTION_VETO_WINDOW_DAYS environment variable); the workflow does
not invent a governance deadline.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .manual_entry_strategy_registry import load_manual_entry_strategy_registry
from .manual_strategy_shadow_runner import (
    DEFAULT_ALLOCATION_PATH,
    DEFAULT_DATA_DIR,
    DEFAULT_MAPPING_PATH,
    DEFAULT_PERFORMANCE_PATH,
    DEFAULT_PRIMARY_POSITIONS_PATH,
    DEFAULT_REGISTRY_PATH,
    SHADOW_SIZING_BASIS,
    _allocation,
    _load_json,
    _mapping,
    _primary_share_quantity,
    _simulate,
)
from .paper_runner import load_csv
from .shadow_promotion_qualification import (
    MAX_ACTIVE_SHADOWS,
    PromotionPerformance,
    review_and_queue_qualified_shadow,
)

DEFAULT_MONTHLY_REVIEW_STATE_PATH = Path("results/shadow_promotion_monthly_review_state.json")
DEFAULT_REVIEW_REPORT_PATH = Path("results/shadow_promotion_review_report.json")
VETO_WINDOW_ENV = "SWING_SHADOW_PROMOTION_VETO_WINDOW_DAYS"
EVIDENCE_BASIS = "SAME_PRIMARY_SHARE_QUANTITY_SAME_MARKET_HISTORY_SIMULATION"
NORMALIZATION_BASIS = "CURRENT_SWING_ALLOCATION"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


@dataclass(frozen=True, slots=True)
class PromotionReviewRow:
    underlying_symbol: str
    primary_strategy_id: str
    shadow_strategy_ids: tuple[str, ...]
    review_period: str
    status: str
    qualified_strategy_id: str | None
    queued_pending_veto: bool
    primary_reference_quantity: float | None = None
    evidence_basis: str = EVIDENCE_BASIS
    normalization_basis: str = NORMALIZATION_BASIS


@dataclass(frozen=True, slots=True)
class PromotionReviewReport:
    generated_at: str
    review_period: str
    veto_window_days: int | None
    rows: tuple[PromotionReviewRow, ...]
    warnings: tuple[str, ...]
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    capital_movement_enabled: bool = False


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


def _load_monthly_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "last_review_period_by_symbol": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("monthly promotion review state root must be an object")
    if payload.get("strategy_id") != "SWING-001" or payload.get("paper_trade_mode") is not True:
        raise ValueError("monthly promotion review state is not authoritative SWING-001 paper evidence")
    periods = payload.get("last_review_period_by_symbol")
    if not isinstance(periods, dict):
        raise ValueError("last_review_period_by_symbol must be an object")
    return payload


def _resolve_veto_window_days(explicit: int | None) -> int | None:
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


def _canonical_performance(strategy_id: str, allocation: float, performance: Mapping[str, Any], *, shadow_order: int = 0) -> PromotionPerformance:
    """Normalize dollar P/L and drawdown to the common current Swing allocation."""
    if allocation <= 0:
        raise ValueError("allocation must be positive")
    net_pl = float(performance.get("net_pl", 0.0))
    raw_drawdown = float(performance.get("max_drawdown", 0.0))
    gross_profit = float(performance.get("gross_profit", 0.0))
    gross_loss = float(performance.get("gross_loss", 0.0))
    raw_pf = performance.get("profit_factor")
    if raw_pf is None:
        profit_factor = math.inf if gross_profit > 0 and gross_loss == 0 else 0.0
    else:
        profit_factor = float(raw_pf)
    return PromotionPerformance(
        strategy_id=strategy_id,
        total_return=round((net_pl / allocation) * 100.0, 6),
        profit_factor=profit_factor,
        max_drawdown=round((abs(raw_drawdown) / allocation) * 100.0, 6),
        trade_count=int(performance.get("trade_count", 0)),
        shadow_order=shadow_order,
    )


def _direct_benchmark(
    *,
    underlying: str,
    strategy: Any,
    vehicle: str,
    allocation: float,
    primary_quantity: float,
    data_dir: Path,
) -> PromotionPerformance:
    underlying_path = data_dir / f"{underlying}.csv"
    vehicle_path = data_dir / f"{vehicle}.csv"
    if not underlying_path.is_file() or not vehicle_path.is_file():
        raise FileNotFoundError(f"missing market data for {underlying}/{vehicle}")
    signal_bars = load_csv(underlying_path)
    vehicle_bars = load_csv(vehicle_path)
    _, performance = _simulate(
        strategy,
        underlying,
        vehicle,
        allocation,
        signal_bars,
        vehicle_bars,
        test_quantity=primary_quantity,
    )
    return _canonical_performance(strategy.strategy_id, allocation, performance)


def _shadow_performance_by_key(path: Path) -> dict[tuple[str, str], Mapping[str, Any]]:
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


def _quantity_matches(evidence: Mapping[str, Any], primary_quantity: float) -> bool:
    if evidence.get("sizing_basis") != SHADOW_SIZING_BASIS:
        return False
    try:
        reference = float(evidence.get("primary_reference_quantity"))
        test_quantity = float(evidence.get("shadow_test_quantity"))
    except (TypeError, ValueError):
        return False
    return (
        math.isclose(reference, primary_quantity, rel_tol=0.0, abs_tol=1e-8)
        and math.isclose(test_quantity, primary_quantity, rel_tol=0.0, abs_tol=1e-8)
    )


def build_monthly_promotion_review(
    *,
    now: str | None = None,
    veto_window_days: int | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    allocation_path: Path = DEFAULT_ALLOCATION_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    shadow_performance_path: Path = DEFAULT_PERFORMANCE_PATH,
    data_dir: Path = DEFAULT_DATA_DIR,
    primary_positions_path: Path = DEFAULT_PRIMARY_POSITIONS_PATH,
    monthly_state_path: Path = DEFAULT_MONTHLY_REVIEW_STATE_PATH,
    review_report_path: Path = DEFAULT_REVIEW_REPORT_PATH,
    review_history_path: Path = Path("results/shadow_promotion_review_history.json"),
    lifecycle_path: Path = Path("results/shadow_promotion_lifecycle.json"),
) -> PromotionReviewReport:
    """Review each DIRECT strategy against up to three SHADOWS once per month."""
    current = _parse_now(now)
    review_period = current.strftime("%Y-%m")
    window_days = _resolve_veto_window_days(veto_window_days)
    registry = load_manual_entry_strategy_registry(registry_path)
    mappings = _mapping(mapping_path)
    allocations = _load_json(allocation_path)
    shadow_rows = _shadow_performance_by_key(shadow_performance_path)
    state = _load_monthly_state(monthly_state_path)
    last_periods = {str(k).upper(): str(v) for k, v in state["last_review_period_by_symbol"].items()}
    by_id = {item.strategy_id: item for item in registry.strategies}
    rows: list[PromotionReviewRow] = []
    warnings: list[str] = []
    state_changed = False

    direct_assignments = [item for item in registry.assignments if item.assignment_mode == "DIRECT" and item.enabled]
    for direct in direct_assignments:
        symbol = direct.underlying_symbol
        shadows = [item for item in registry.assignments if item.underlying_symbol == symbol and item.assignment_mode == "SHADOW" and item.enabled]
        shadow_ids = tuple(item.strategy_id for item in shadows)
        if not shadows:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, (), review_period, "NO_ACTIVE_SHADOWS", None, False))
            continue
        if len(shadows) > MAX_ACTIVE_SHADOWS:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "TOO_MANY_ACTIVE_SHADOWS", None, False))
            warnings.append(f"{symbol}: more than three active Shadows; promotion review skipped.")
            continue
        if last_periods.get(symbol) == review_period:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "ALREADY_REVIEWED_THIS_MONTH", None, False))
            continue
        if window_days is None:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "VETO_WINDOW_NOT_CONFIGURED", None, False))
            warnings.append(f"{symbol}: {VETO_WINDOW_ENV} is not configured; monthly counter was not changed.")
            continue
        vehicle = mappings.get(symbol)
        if not vehicle:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "MISSING_VERIFIED_MAPPING", None, False))
            continue
        allocation = _allocation(allocations, symbol, vehicle)
        if allocation is None:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "MISSING_SWING_ALLOCATION", None, False))
            continue
        try:
            primary_quantity = _primary_share_quantity(primary_positions_path, vehicle)
        except (OSError, ValueError, TypeError) as exc:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "PRIMARY_SHARE_QUANTITY_ERROR", None, False))
            warnings.append(f"{symbol}: Primary share quantity unavailable: {type(exc).__name__}: {exc}")
            continue
        if primary_quantity is None:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "MISSING_PRIMARY_SHARE_QUANTITY", None, False))
            continue
        direct_strategy = by_id.get(direct.strategy_id)
        if direct_strategy is None or not direct_strategy.enabled:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "PRIMARY_STRATEGY_UNAVAILABLE", None, False, primary_quantity))
            continue
        try:
            primary = _direct_benchmark(
                underlying=symbol,
                strategy=direct_strategy,
                vehicle=vehicle,
                allocation=allocation,
                primary_quantity=primary_quantity,
                data_dir=data_dir,
            )
        except (OSError, ValueError, TypeError) as exc:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "PRIMARY_EVIDENCE_ERROR", None, False, primary_quantity))
            warnings.append(f"{symbol}: Primary benchmark unavailable: {type(exc).__name__}: {exc}")
            continue

        canonical_shadows: list[PromotionPerformance] = []
        missing_shadow = False
        quantity_mismatch = False
        for order, assignment in enumerate(shadows, start=1):
            evidence = shadow_rows.get((symbol, assignment.strategy_id))
            if evidence is None:
                missing_shadow = True
                warnings.append(f"{symbol}/{assignment.strategy_id}: Shadow performance evidence unavailable.")
                continue
            if not _quantity_matches(evidence, primary_quantity):
                quantity_mismatch = True
                warnings.append(f"{symbol}/{assignment.strategy_id}: Shadow quantity does not match current Primary quantity {primary_quantity}.")
                continue
            canonical_shadows.append(
                _canonical_performance(assignment.strategy_id, allocation, evidence, shadow_order=order)
            )
        if quantity_mismatch:
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "SHADOW_QUANTITY_MISMATCH", None, False, primary_quantity))
            continue
        if missing_shadow or len(canonical_shadows) != len(shadows):
            rows.append(PromotionReviewRow(symbol, direct.strategy_id, shadow_ids, review_period, "INCOMPLETE_SHADOW_EVIDENCE", None, False, primary_quantity))
            continue

        qualified_at = _utc_text(current)
        veto_deadline = _utc_text(current + timedelta(days=window_days))
        result, queued = review_and_queue_qualified_shadow(
            underlying_symbol=symbol,
            primary=primary,
            shadows=tuple(canonical_shadows),
            qualified_at=qualified_at,
            veto_deadline=veto_deadline,
            review_history_path=review_history_path,
            lifecycle_path=lifecycle_path,
        )
        last_periods[symbol] = review_period
        state_changed = True
        rows.append(
            PromotionReviewRow(
                symbol,
                direct.strategy_id,
                shadow_ids,
                review_period,
                "QUALIFIED_PENDING_VETO" if queued is not None else "REVIEWED_NOT_QUALIFIED",
                result.qualified_strategy_id,
                queued is not None,
                primary_quantity,
            )
        )

    if state_changed:
        updated_state = dict(state)
        updated_state["last_review_period_by_symbol"] = last_periods
        updated_state["last_reviewed_at"] = _utc_text(current)
        _atomic_json(monthly_state_path, updated_state)

    report = PromotionReviewReport(
        generated_at=_utc_text(current),
        review_period=review_period,
        veto_window_days=window_days,
        rows=tuple(rows),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    _atomic_json(
        review_report_path,
        {
            **asdict(report),
            "rows": [asdict(row) for row in report.rows],
        },
    )
    return report
