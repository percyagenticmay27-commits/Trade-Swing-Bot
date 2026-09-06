"""Research-only shadow execution for manual SWING-001 strategies.

Signals are evaluated from the assigned underlying. Simulated P/L is measured
against the verified leveraged vehicle when a mapping and same-date vehicle bar
exist. Shadow sizing is anchored to the current Primary paper-position share
quantity. No paper position, capital reservation, SGOV movement, order, or
promotion authority is exposed here.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .indicators import ema, rsi, sma, volume_average
from .manual_entry_strategy_registry import EntryRule, ManualEntryStrategy, load_manual_entry_strategy_registry
from .paper_runner import load_csv
from .position_state import MarketBar
from .strategy_assignment_shadow_report import (
    DEFAULT_OUTPUT_PATH as DEFAULT_ASSIGNMENT_REPORT_PATH,
    build_and_write_strategy_assignment_shadow_report,
)

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
DEFAULT_ALLOCATION_PATH = Path("results/portfolio_allocations.json")
DEFAULT_MAPPING_PATH = Path("results/discovery_candidate_state.csv")
DEFAULT_DATA_DIR = Path("data")
DEFAULT_LEDGER_PATH = Path("results/shadow_strategy_ledger.json")
DEFAULT_PERFORMANCE_PATH = Path("results/shadow_strategy_performance.json")
DEFAULT_PRIMARY_POSITIONS_PATH = Path("results/paper_ledger/current_portfolio_positions.csv")
SHADOW_SIZING_BASIS = "PRIMARY_SHARE_QUANTITY"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
SHADOW_CAPITAL_RESERVED = False
AUTO_PROMOTION_ENABLED = False


def _load_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, Mapping) else {}


def _allocation(payload: Mapping[str, Any], underlying: str, vehicle: str) -> float | None:
    rows = payload.get("allocations")
    if not isinstance(rows, list):
        rows = payload.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper()
        execution = str(row.get("vehicle_symbol") or row.get("execution_symbol") or "").strip().upper()
        if symbol != underlying and execution != vehicle:
            continue
        for key in ("allocated_capital", "allocation", "allocation_amount", "dollar_allocation"):
            value = row.get(key)
            if isinstance(value, (int, float)) and float(value) > 0:
                return round(float(value), 2)
    return None


def _primary_share_quantity(path: Path, vehicle: str) -> float | None:
    """Return the current Primary paper-position quantity for the mapped vehicle.

    The paper portfolio CSV is the sizing authority. Multiple matching rows are
    summed so the resolver remains correct if the portfolio is represented as
    more than one open lot. Invalid non-empty share values fail closed.
    """
    if not path.is_file():
        return None
    target = vehicle.strip().upper()
    quantities: list[float] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol != target:
                continue
            raw = row.get("shares")
            try:
                shares = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid Primary share quantity for {target}: {raw!r}") from exc
            if not math.isfinite(shares) or shares < 0:
                raise ValueError(f"invalid Primary share quantity for {target}: {raw!r}")
            if shares > 0:
                quantities.append(shares)
    if not quantities:
        return None
    return round(sum(quantities), 8)


def _mapping(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            underlying = str(row.get("underlying_symbol", "")).strip().upper()
            vehicle = str(row.get("leveraged_symbol", "")).strip().upper()
            if underlying and vehicle:
                result[underlying] = vehicle
    return result


def _wilder(values: Sequence[float], period: int) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = ((result * (period - 1)) + value) / period
    return result


def _atr(bars: Sequence[MarketBar], period: int) -> float | None:
    if len(bars) < period + 1:
        return None
    values: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        high = current.high if current.high is not None else current.close
        low = current.low if current.low is not None else current.close
        values.append(max(high - low, abs(high - previous.close), abs(low - previous.close)))
    return _wilder(values, period)


def _chop(bars: Sequence[MarketBar], period: int) -> float | None:
    if len(bars) < period + 1:
        return None
    atr1_values: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        high = current.high if current.high is not None else current.close
        low = current.low if current.low is not None else current.close
        atr1_values.append(max(high - low, abs(high - previous.close), abs(low - previous.close)))
    recent = bars[-period:]
    highs = [(bar.high if bar.high is not None else bar.close) for bar in recent]
    lows = [(bar.low if bar.low is not None else bar.close) for bar in recent]
    span = max(highs) - min(lows)
    if span <= 0:
        return 100.0
    total_tr = sum(atr1_values[-period:])
    return 100.0 * math.log10(total_tr / span) / math.log10(period)


def _wma(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    weights = range(1, period + 1)
    denominator = period * (period + 1) / 2
    return sum(value * weight for value, weight in zip(values[-period:], weights)) / denominator


def _hma(values: Sequence[float], period: int) -> float | None:
    if period <= 1 or len(values) < period + int(math.sqrt(period)) - 1:
        return None
    half = max(1, period // 2)
    root = max(1, int(math.sqrt(period)))
    derived: list[float] = []
    for end in range(period, len(values) + 1):
        window = values[:end]
        full = _wma(window, period)
        short = _wma(window, half)
        if full is not None and short is not None:
            derived.append((2.0 * short) - full)
    return _wma(derived, root)


def _price_series(bars: Sequence[MarketBar], source: str | None) -> list[float]:
    if source != "OHLC_AVERAGE":
        return [bar.close for bar in bars]
    return [
        ((bar.open if bar.open is not None else bar.close)
         + (bar.high if bar.high is not None else bar.close)
         + (bar.low if bar.low is not None else bar.close)
         + bar.close) / 4.0
        for bar in bars
    ]


def _indicator(token: object, rule: EntryRule, bars: Sequence[MarketBar]) -> float | str | None:
    if isinstance(token, (int, float)):
        return float(token)
    if isinstance(token, list):
        return None
    name = str(token).strip().lower()
    closes = [bar.close for bar in bars]
    if name == "close":
        return bars[-1].close
    if name == "ema":
        return ema(closes, rule.period or 14)
    if name == "sma":
        return sma(closes, rule.period or 20)
    if name == "rsi":
        return rsi(closes, rule.period or 14)
    if name == "volume":
        return bars[-1].volume
    if name == "volume_average":
        return volume_average([bar.volume for bar in bars], rule.period or 20)
    if name == "hma":
        return _hma(closes, rule.period or 50)
    if name == "chop":
        return _chop(bars, rule.period or 14)
    if name == "keltner_middle":
        values = _price_series(bars, rule.price_source)
        period = rule.period or 14
        if str(rule.smoothing or "EMA").upper() == "WILDER":
            return _wilder(values, period)
        return ema(values, period)
    if name == "market_filter":
        return "satisfied"
    return str(token)


def _compare(left: object, operator: str, right: object) -> bool:
    if operator == "between":
        if not isinstance(right, list) or len(right) != 2 or not isinstance(left, (int, float)):
            return False
        return float(right[0]) <= float(left) <= float(right[1])
    if operator == "==":
        return left == right
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    return {
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }.get(operator, False)


def _rule_passes(rule: EntryRule, bars: Sequence[MarketBar]) -> bool:
    left = _indicator(rule.left, rule, bars)
    right = rule.right if isinstance(rule.right, list) else _indicator(rule.right, rule, bars)
    return _compare(left, rule.operator, right)


def _rules_pass(rules: Sequence[EntryRule], logic: str, bars: Sequence[MarketBar]) -> bool:
    if not rules:
        return True
    values = [_rule_passes(rule, bars) for rule in rules]
    return any(values) if logic == "ANY" else all(values)


def _minimum_bars(strategy: ManualEntryStrategy) -> int:
    periods = [2]
    for rule in (*strategy.rules, *strategy.regime_filters, *strategy.normal_exit_rules):
        periods.append(rule.period or 1)
    for conditional in strategy.conditional_exits:
        periods.append(conditional.condition.period or 1)
        periods.extend(rule.period or 1 for rule in conditional.rules)
    return max(periods) + 2


def _simulate(
    strategy: ManualEntryStrategy,
    underlying: str,
    vehicle: str,
    allocation: float,
    signal_bars: Sequence[MarketBar],
    vehicle_bars: Sequence[MarketBar],
    *,
    test_quantity: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if test_quantity is not None and (not math.isfinite(test_quantity) or test_quantity <= 0):
        raise ValueError("test_quantity must be a positive finite number")
    vehicle_by_date = {bar.date: bar for bar in vehicle_bars}
    minimum = _minimum_bars(strategy)
    ledger: list[dict[str, Any]] = []
    slices: list[dict[str, float]] = []
    confirmation = 0
    cooldown = 0
    realized = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    losses = 0
    equity_peak = 0.0
    max_drawdown = 0.0
    slice_amount = allocation / strategy.number_of_entries
    slice_shares = None if test_quantity is None else test_quantity / strategy.number_of_entries

    def open_pl(vehicle_price: float) -> float:
        return sum((vehicle_price - item["price"]) * item["shares"] for item in slices)

    for index in range(minimum - 1, len(signal_bars)):
        bars = signal_bars[: index + 1]
        bar = bars[-1]
        vehicle_bar = vehicle_by_date.get(bar.date)
        if vehicle_bar is None:
            continue
        vehicle_price = vehicle_bar.close
        current_open_pl = open_pl(vehicle_price) if slices else 0.0
        current_equity = realized + current_open_pl
        equity_peak = max(equity_peak, current_equity)
        max_drawdown = min(max_drawdown, current_equity - equity_peak)

        normal_exit = bool(slices) and _rules_pass(strategy.normal_exit_rules, strategy.normal_exit_logic, bars)
        conditional_exit = False
        conditional_cooldown = 0
        if slices:
            for conditional in strategy.conditional_exits:
                condition = conditional.condition
                condition_left: object
                if str(condition.left).lower() == "position_pl":
                    condition_left = current_open_pl
                else:
                    condition_left = _indicator(condition.left, condition, bars)
                condition_right = condition.right if isinstance(condition.right, list) else _indicator(condition.right, condition, bars)
                if _compare(condition_left, condition.operator, condition_right) and _rules_pass(conditional.rules, conditional.rule_logic, bars):
                    conditional_exit = True
                    conditional_cooldown = conditional.cooldown_bars
                    break

        if slices and (normal_exit or conditional_exit):
            trade_pl = current_open_pl
            realized += trade_pl
            if trade_pl > 0:
                wins += 1
                gross_profit += trade_pl
            elif trade_pl < 0:
                losses += 1
                gross_loss += trade_pl
            ledger.append({
                "date": bar.date.isoformat(), "underlying_symbol": underlying, "vehicle_symbol": vehicle,
                "strategy_id": strategy.strategy_id, "event": "EXIT", "exit_reason": "CONDITIONAL" if conditional_exit else "NORMAL",
                "vehicle_price": round(vehicle_price, 6), "simulated_allocation": round(allocation, 2),
                "primary_reference_quantity": None if test_quantity is None else round(test_quantity, 8),
                "shadow_test_quantity": None if test_quantity is None else round(test_quantity, 8),
                "sizing_basis": "DOLLAR_ALLOCATION" if test_quantity is None else SHADOW_SIZING_BASIS,
                "realized_pl": round(trade_pl, 2), "cumulative_realized_pl": round(realized, 2),
            })
            slices = []
            confirmation = 0
            cooldown = conditional_cooldown if conditional_exit else 0
            continue

        if slices:
            continue
        if cooldown > 0:
            cooldown -= 1
            confirmation = 0
            continue

        entry_ok = _rules_pass(strategy.rules, strategy.rule_logic, bars) and _rules_pass(strategy.regime_filters, strategy.regime_logic, bars)
        confirmation = confirmation + 1 if entry_ok else 0
        if confirmation >= strategy.confirmation_bars:
            shares = slice_amount / vehicle_price if slice_shares is None else slice_shares
            simulated_notional = shares * vehicle_price
            slices.append({"price": vehicle_price, "shares": shares, "amount": simulated_notional})
            ledger.append({
                "date": bar.date.isoformat(), "underlying_symbol": underlying, "vehicle_symbol": vehicle,
                "strategy_id": strategy.strategy_id, "event": "ENTRY", "entry_number": len(slices),
                "vehicle_price": round(vehicle_price, 6), "simulated_allocation": round(slice_amount, 2),
                "simulated_notional": round(simulated_notional, 2),
                "shares": round(shares, 8),
                "primary_reference_quantity": None if test_quantity is None else round(test_quantity, 8),
                "shadow_test_quantity": None if test_quantity is None else round(test_quantity, 8),
                "sizing_basis": "DOLLAR_ALLOCATION" if test_quantity is None else SHADOW_SIZING_BASIS,
                "realized_pl": round(realized, 2),
            })
            confirmation = 0

    final_price = vehicle_by_date.get(signal_bars[-1].date).close if signal_bars and vehicle_by_date.get(signal_bars[-1].date) is not None else None
    final_open = open_pl(final_price) if final_price is not None and slices else 0.0
    net_pl = realized + final_open
    closed = wins + losses
    profit_factor = None if gross_loss == 0 else gross_profit / abs(gross_loss)
    performance = {
        "evidence_status": "AVAILABLE",
        "trade_count": closed,
        "wins": wins,
        "losses": losses,
        "win_rate": None if closed == 0 else round(wins / closed * 100.0, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "realized_pl": round(realized, 2),
        "open_pl": round(final_open, 2),
        "net_pl": round(net_pl, 2),
        "max_drawdown": round(max_drawdown, 2),
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "open_entry_count": len(slices),
        "primary_reference_quantity": None if test_quantity is None else round(test_quantity, 8),
        "shadow_test_quantity": None if test_quantity is None else round(test_quantity, 8),
        "sizing_basis": "DOLLAR_ALLOCATION" if test_quantity is None else SHADOW_SIZING_BASIS,
        "promotion_recommended": False,
        "promotion_recommendation_status": "NOT_EVALUATED_BY_SHADOW_RUNNER",
    }
    return ledger, performance


def run_shadow_strategies(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    allocation_path: Path = DEFAULT_ALLOCATION_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    data_dir: Path = DEFAULT_DATA_DIR,
    primary_positions_path: Path = DEFAULT_PRIMARY_POSITIONS_PATH,
) -> dict[str, Any]:
    registry = load_manual_entry_strategy_registry(registry_path)
    mappings = _mapping(mapping_path)
    allocation_payload = _load_json(allocation_path)
    by_id = {item.strategy_id: item for item in registry.strategies}
    ledger_rows: list[dict[str, Any]] = []
    performance_rows: list[dict[str, Any]] = []

    for assignment in registry.assignments:
        if assignment.assignment_mode != "SHADOW" or not assignment.enabled:
            continue
        underlying = assignment.underlying_symbol
        strategy = by_id[assignment.strategy_id]
        vehicle = mappings.get(underlying)
        base = {"underlying_symbol": underlying, "strategy_id": strategy.strategy_id, "strategy_name": strategy.name, "vehicle_symbol": vehicle}
        if not vehicle:
            performance_rows.append({**base, "evidence_status": "MISSING_VERIFIED_MAPPING", "promotion_recommended": False})
            continue
        allocation = _allocation(allocation_payload, underlying, vehicle)
        if allocation is None:
            performance_rows.append({**base, "evidence_status": "MISSING_SWING_ALLOCATION", "promotion_recommended": False})
            continue
        try:
            primary_quantity = _primary_share_quantity(primary_positions_path, vehicle)
        except (OSError, ValueError, TypeError) as exc:
            performance_rows.append({**base, "simulated_allocation": allocation, "evidence_status": "PRIMARY_SHARE_QUANTITY_ERROR", "error": f"{type(exc).__name__}: {exc}", "promotion_recommended": False})
            continue
        if primary_quantity is None:
            performance_rows.append({**base, "simulated_allocation": allocation, "evidence_status": "MISSING_PRIMARY_SHARE_QUANTITY", "promotion_recommended": False})
            continue
        underlying_path = data_dir / f"{underlying}.csv"
        vehicle_path = data_dir / f"{vehicle}.csv"
        if not underlying_path.is_file() or not vehicle_path.is_file():
            performance_rows.append({**base, "simulated_allocation": allocation, "primary_reference_quantity": primary_quantity, "shadow_test_quantity": primary_quantity, "sizing_basis": SHADOW_SIZING_BASIS, "evidence_status": "MISSING_MARKET_DATA", "promotion_recommended": False})
            continue
        try:
            signal_bars = load_csv(underlying_path)
            vehicle_bars = load_csv(vehicle_path)
            ledger, performance = _simulate(
                strategy,
                underlying,
                vehicle,
                allocation,
                signal_bars,
                vehicle_bars,
                test_quantity=primary_quantity,
            )
        except (OSError, ValueError, TypeError) as exc:
            performance_rows.append({**base, "simulated_allocation": allocation, "primary_reference_quantity": primary_quantity, "shadow_test_quantity": primary_quantity, "sizing_basis": SHADOW_SIZING_BASIS, "evidence_status": "EVIDENCE_ERROR", "error": f"{type(exc).__name__}: {exc}", "promotion_recommended": False})
            continue
        ledger_rows.extend(ledger)
        performance_rows.append({**base, "simulated_allocation": allocation, **performance})

    return {
        "schema_version": "1.1", "strategy_id": "SWING-001", "paper_trade_mode": True,
        "shadow_allocation_model": "SAME_PRIMARY_SHARE_QUANTITY_SIMULATED_ONLY",
        "shadow_sizing_basis": SHADOW_SIZING_BASIS,
        "normalization_basis": "CURRENT_SWING_ALLOCATION",
        "signal_price_authority": "UNDERLYING_MARKET_DATA", "pnl_price_authority": "VERIFIED_MAPPED_VEHICLE_MARKET_DATA",
        "primary_quantity_authority": str(primary_positions_path),
        "shadow_capital_reserved": False, "capital_movement_enabled": False, "paper_positions_created": 0,
        "auto_promotion_enabled": False, "promotion_authority": "NONE_IN_SHADOW_RUNNER_SEPARATE_QUALIFICATION_LIFECYCLE",
        "ledger_rows": ledger_rows, "rows": performance_rows,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def build_and_write_shadow_strategies(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    allocation_path: Path = DEFAULT_ALLOCATION_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    data_dir: Path = DEFAULT_DATA_DIR,
    primary_positions_path: Path = DEFAULT_PRIMARY_POSITIONS_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    performance_path: Path = DEFAULT_PERFORMANCE_PATH,
    assignment_report_path: Path = DEFAULT_ASSIGNMENT_REPORT_PATH,
) -> dict[str, Any]:
    payload = run_shadow_strategies(
        registry_path=registry_path,
        allocation_path=allocation_path,
        mapping_path=mapping_path,
        data_dir=data_dir,
        primary_positions_path=primary_positions_path,
    )
    ledger_payload = {key: value for key, value in payload.items() if key != "rows"}
    ledger_payload["rows"] = payload["ledger_rows"]
    ledger_payload.pop("ledger_rows", None)
    performance_payload = {key: value for key, value in payload.items() if key != "ledger_rows"}
    _atomic_json(ledger_path, ledger_payload)
    _atomic_json(performance_path, performance_payload)
    build_and_write_strategy_assignment_shadow_report(
        registry_path=registry_path,
        allocation_path=allocation_path,
        shadow_performance_path=performance_path,
        output_path=assignment_report_path,
    )
    return payload


if __name__ == "__main__":
    result = build_and_write_shadow_strategies()
    available = sum(1 for row in result["rows"] if row.get("evidence_status") == "AVAILABLE")
    print(f"Shadow strategy runner: {len(result['rows'])} shadow assignments; {available} with performance evidence")
