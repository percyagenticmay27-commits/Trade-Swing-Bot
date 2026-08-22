"""Research-only shadow execution for manual SWING-001 strategies.

Signals are evaluated from the assigned underlying. Simulated P/L is measured
against the verified leveraged vehicle when a mapping and same-date vehicle bar
exist. No paper position, capital reservation, SGOV movement, order, or
promotion authority is exposed here.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .indicators import ema, rsi, sma, volume_average
from .manual_entry_strategy_registry import EntryRule, ManualEntryStrategy, load_manual_entry_strategy_registry
from .paper_runner import load_csv
from .position_state import MarketBar

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
DEFAULT_ALLOCATION_PATH = Path("results/portfolio_allocations.json")
DEFAULT_MAPPING_PATH = Path("results/discovery_candidate_state.csv")
DEFAULT_DATA_DIR = Path("data")
DEFAULT_LEDGER_PATH = Path("results/shadow_strategy_ledger.json")
DEFAULT_PERFORMANCE_PATH = Path("results/shadow_strategy_performance.json")

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
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _mapping(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            underlying = str(row.get("underlying_symbol") or "").strip().upper()
            vehicle = str(row.get("leveraged_symbol") or "").strip().upper()
            if underlying and vehicle:
                result[underlying] = vehicle
    return result


def _allocation(payload: Mapping[str, Any], underlying: str, vehicle: str) -> float | None:
    rows = payload.get("allocations")
    if not isinstance(rows, list):
        rows = payload.get("rows")
    if not isinstance(rows, list):
        return None
    wanted = {underlying.upper(), vehicle.upper()}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or row.get("vehicle_symbol") or "").strip().upper()
        if symbol not in wanted:
            continue
        for key in ("allocated_capital", "allocation", "allocation_amount", "dollar_allocation"):
            value = row.get(key)
            if isinstance(value, (int, float)) and float(value) > 0:
                return round(float(value), 2)
    return None


def _wma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    weights = range(1, period + 1)
    denominator = period * (period + 1) / 2
    return sum(value * weight for value, weight in zip(values[-period:], weights)) / denominator


def _hma(values: Sequence[float], period: int) -> float | None:
    if period <= 0:
        return None
    half = max(1, period // 2)
    root = max(1, int(math.sqrt(period)))
    if len(values) < period + root - 1:
        return None
    transformed: list[float] = []
    for end in range(period, len(values) + 1):
        window = values[:end]
        fast = _wma(window, half)
        slow = _wma(window, period)
        if fast is not None and slow is not None:
            transformed.append(2 * fast - slow)
    return _wma(transformed, root)


def _wilder(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = ((result * (period - 1)) + value) / period
    return result


def _ohlc_average(bar: MarketBar) -> float | None:
    if bar.open is None or bar.high is None or bar.low is None:
        return None
    return (bar.open + bar.high + bar.low + bar.close) / 4.0


def _true_ranges(bars: Sequence[MarketBar]) -> list[float] | None:
    if not bars or any(bar.high is None or bar.low is None for bar in bars):
        return None
    output: list[float] = []
    previous_close: float | None = None
    for bar in bars:
        assert bar.high is not None and bar.low is not None
        if previous_close is None:
            output.append(bar.high - bar.low)
        else:
            output.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        previous_close = bar.close
    return output


def _chop(bars: Sequence[MarketBar], period: int) -> float | None:
    if period <= 1 or len(bars) < period + 1:
        return None
    window = bars[-period:]
    if any(bar.high is None or bar.low is None for bar in window):
        return None
    ranges = _true_ranges(bars)
    if ranges is None:
        return None
    high = max(float(bar.high) for bar in window if bar.high is not None)
    low = min(float(bar.low) for bar in window if bar.low is not None)
    span = high - low
    if span <= 0:
        return None
    total = sum(ranges[-period:])
    if total <= 0:
        return None
    return 100.0 * math.log10(total / span) / math.log10(period)


def _indicator(token: object, rule: EntryRule, bars: Sequence[MarketBar], position_pl: float) -> float | str | None:
    if isinstance(token, (int, float)):
        return float(token)
    text = str(token).strip()
    lowered = text.lower()
    closes = [bar.close for bar in bars]
    period = rule.period or 14
    if lowered == "close":
        return closes[-1]
    if lowered == "volume":
        return bars[-1].volume
    if lowered == "ema":
        return ema(closes, period)
    if lowered == "sma":
        return sma(closes, period)
    if lowered == "rsi":
        return rsi(closes, period)
    if lowered == "volume_average":
        return volume_average([bar.volume for bar in bars], period)
    if lowered == "hma":
        return _hma(closes, period)
    if lowered == "chop":
        return _chop(bars, period)
    if lowered == "position_pl":
        return position_pl
    if lowered == "keltner_middle":
        if (rule.smoothing or "WILDER").upper() != "WILDER":
            return None
        source = (rule.price_source or "OHLC_AVERAGE").upper()
        if source == "OHLC_AVERAGE":
            values = [_ohlc_average(bar) for bar in bars]
            if any(value is None for value in values):
                return None
            return _wilder([float(value) for value in values if value is not None], period)
        if source == "CLOSE":
            return _wilder(closes, period)
        return None
    return text


def _compare(left: float | str | None, operator: str, right: float | str | list[float] | None) -> bool:
    if left is None or right is None:
        return False
    if operator == "between":
        if not isinstance(right, list) or len(right) != 2:
            return False
        return float(right[0]) <= float(left) <= float(right[1])
    if isinstance(left, str) or isinstance(right, str):
        return operator == "==" and str(left).lower() == str(right).lower()
    a, b = float(left), float(right)
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b, "==": a == b}.get(operator, False)


def _rule_passes(rule: EntryRule, bars: Sequence[MarketBar], position_pl: float) -> bool:
    left = _indicator(rule.left, rule, bars, position_pl)
    if isinstance(rule.right, list):
        right: float | str | list[float] | None = rule.right
    else:
        right = _indicator(rule.right, rule, bars, position_pl)
    return _compare(left, rule.operator, right)


def _rules_pass(rules: Sequence[EntryRule], logic: str, bars: Sequence[MarketBar], position_pl: float) -> bool:
    if not rules:
        return True
    values = [_rule_passes(rule, bars, position_pl) for rule in rules]
    return all(values) if logic == "ALL" else any(values)


def _vehicle_close_map(bars: Sequence[MarketBar]) -> dict[Any, float]:
    return {bar.date: bar.close for bar in bars}


def _simulate(strategy: ManualEntryStrategy, underlying: str, vehicle: str, allocation: float, signal_bars: Sequence[MarketBar], vehicle_bars: Sequence[MarketBar]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if strategy.timeframe != "1D":
        return [], {"evidence_status": "UNSUPPORTED_TIMEFRAME", "reason": f"Shadow runner currently requires 1D data; strategy uses {strategy.timeframe}"}
    prices = _vehicle_close_map(vehicle_bars)
    ledger: list[dict[str, Any]] = []
    slices: list[dict[str, float]] = []
    realized = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = losses = 0
    confirmation = 0
    cooldown = 0
    equity_peak = 0.0
    max_drawdown = 0.0
    slice_amount = allocation / strategy.number_of_entries

    def open_pl(price: float) -> float:
        return sum(item["shares"] * (price - item["price"]) for item in slices)

    for index, bar in enumerate(signal_bars):
        vehicle_price = prices.get(bar.date)
        if vehicle_price is None:
            continue
        history = signal_bars[: index + 1]
        unrealized = open_pl(vehicle_price)
        equity = realized + unrealized
        equity_peak = max(equity_peak, equity)
        max_drawdown = min(max_drawdown, equity - equity_peak)

        if slices:
            normal_exit = bool(strategy.normal_exit_rules) and _rules_pass(strategy.normal_exit_rules, strategy.normal_exit_logic, history, unrealized)
            conditional_exit = False
            conditional_label = ""
            conditional_cooldown = 0
            for branch in strategy.conditional_exits:
                if _rule_passes(branch.condition, history, unrealized) and _rules_pass(branch.rules, branch.rule_logic, history, unrealized):
                    conditional_exit = True
                    conditional_label = branch.label or "CONDITIONAL_EXIT"
                    conditional_cooldown = branch.cooldown_bars
                    break
            if normal_exit or conditional_exit:
                trade_pl = unrealized
                realized += trade_pl
                if trade_pl > 0:
                    wins += 1
                    gross_profit += trade_pl
                elif trade_pl < 0:
                    losses += 1
                    gross_loss += trade_pl
                ledger.append({
                    "date": bar.date.isoformat(), "underlying_symbol": underlying, "vehicle_symbol": vehicle,
                    "strategy_id": strategy.strategy_id, "event": "EXIT", "vehicle_price": round(vehicle_price, 6),
                    "simulated_allocation": round(sum(item["amount"] for item in slices), 2), "trade_pl": round(trade_pl, 2),
                    "realized_pl": round(realized, 2), "exit_reason": conditional_label if conditional_exit else "NORMAL_EXIT",
                })
                slices.clear()
                confirmation = 0
                cooldown = conditional_cooldown
                continue

        if cooldown > 0:
            cooldown -= 1
            confirmation = 0
            continue

        if len(slices) >= strategy.number_of_entries:
            continue
        entry_ok = _rules_pass(strategy.rules, strategy.rule_logic, history, unrealized) and _rules_pass(strategy.regime_filters, strategy.regime_logic, history, unrealized)
        confirmation = confirmation + 1 if entry_ok else 0
        if confirmation >= strategy.confirmation_bars:
            shares = slice_amount / vehicle_price
            slices.append({"price": vehicle_price, "shares": shares, "amount": slice_amount})
            ledger.append({
                "date": bar.date.isoformat(), "underlying_symbol": underlying, "vehicle_symbol": vehicle,
                "strategy_id": strategy.strategy_id, "event": "ENTRY", "entry_number": len(slices),
                "vehicle_price": round(vehicle_price, 6), "simulated_allocation": round(slice_amount, 2),
                "shares": round(shares, 8), "realized_pl": round(realized, 2),
            })
            confirmation = 0

    final_price = prices.get(signal_bars[-1].date) if signal_bars else None
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
        "promotion_recommended": False,
        "promotion_recommendation_status": "NOT_EVALUATED_BY_SHADOW_RUNNER",
    }
    return ledger, performance


def run_shadow_strategies(*, registry_path: Path = DEFAULT_REGISTRY_PATH, allocation_path: Path = DEFAULT_ALLOCATION_PATH, mapping_path: Path = DEFAULT_MAPPING_PATH, data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
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
        underlying_path = data_dir / f"{underlying}.csv"
        vehicle_path = data_dir / f"{vehicle}.csv"
        if not underlying_path.is_file() or not vehicle_path.is_file():
            performance_rows.append({**base, "simulated_allocation": allocation, "evidence_status": "MISSING_MARKET_DATA", "promotion_recommended": False})
            continue
        try:
            signal_bars = load_csv(underlying_path)
            vehicle_bars = load_csv(vehicle_path)
            ledger, performance = _simulate(strategy, underlying, vehicle, allocation, signal_bars, vehicle_bars)
        except (OSError, ValueError, TypeError) as exc:
            performance_rows.append({**base, "simulated_allocation": allocation, "evidence_status": "EVIDENCE_ERROR", "error": f"{type(exc).__name__}: {exc}", "promotion_recommended": False})
            continue
        ledger_rows.extend(ledger)
        performance_rows.append({**base, "simulated_allocation": allocation, **performance})

    return {
        "schema_version": "1.0", "strategy_id": "SWING-001", "paper_trade_mode": True,
        "shadow_allocation_model": "SAME_CURRENT_SWING_ALLOCATION_SIMULATED_ONLY",
        "signal_price_authority": "UNDERLYING_MARKET_DATA", "pnl_price_authority": "VERIFIED_MAPPED_VEHICLE_MARKET_DATA",
        "shadow_capital_reserved": False, "capital_movement_enabled": False, "paper_positions_created": 0,
        "auto_promotion_enabled": False, "promotion_authority": "USER_EXPLICIT_ACTION_ONLY",
        "ledger_rows": ledger_rows, "rows": performance_rows,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def build_and_write_shadow_strategies(*, registry_path: Path = DEFAULT_REGISTRY_PATH, allocation_path: Path = DEFAULT_ALLOCATION_PATH, mapping_path: Path = DEFAULT_MAPPING_PATH, data_dir: Path = DEFAULT_DATA_DIR, ledger_path: Path = DEFAULT_LEDGER_PATH, performance_path: Path = DEFAULT_PERFORMANCE_PATH) -> dict[str, Any]:
    payload = run_shadow_strategies(registry_path=registry_path, allocation_path=allocation_path, mapping_path=mapping_path, data_dir=data_dir)
    ledger_payload = {key: value for key, value in payload.items() if key != "rows"}
    ledger_payload["rows"] = payload["ledger_rows"]
    ledger_payload.pop("ledger_rows", None)
    performance_payload = {key: value for key, value in payload.items() if key != "ledger_rows"}
    _atomic_json(ledger_path, ledger_payload)
    _atomic_json(performance_path, performance_payload)
    return payload


if __name__ == "__main__":
    result = build_and_write_shadow_strategies()
    available = sum(1 for row in result["rows"] if row.get("evidence_status") == "AVAILABLE")
    print(f"Shadow strategy runner: {len(result['rows'])} shadow assignments; {available} with performance evidence")
