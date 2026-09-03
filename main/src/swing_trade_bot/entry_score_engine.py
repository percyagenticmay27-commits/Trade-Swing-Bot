"""Entry Score V1.0 for the paper-only Swing Entry Committee.

Entry Score answers whether the current completed-daily-bar environment supports
entry consideration. It is independent from Opportunity Quality and from the
assigned frozen strategy's exact BUY trigger. Signal/underlying symbols are the
price-evidence authority; leveraged vehicles are not used to manufacture Entry
Score evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .indicators import ema, rsi, sma
from .paper_runner import load_csv
from .position_state import MarketBar

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "ENTRY_SCORE_V1_0"
STRATEGY_ID = "SWING-001"
ENTRY_MINIMUM = 70.0

RSI_POINTS = 20.0
STOCH_RSI_POINTS = 20.0
MOMENTUM_POINTS = 20.0
VOLUME_POINTS = 15.0
PRICE_TREND_POINTS = 15.0
EXTENSION_POINTS = 10.0

RSI_PERIOD = 14
STOCH_RSI_PERIOD = 14
STOCH_K_SMOOTH = 3
STOCH_D_SMOOTH = 3
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_PERIOD = 20
EMA_FAST = 20
EMA_SLOW = 50

RSI_FLAT_TOLERANCE = 0.25
STOCH_EQUAL_TOLERANCE = 1.0
STOCH_FLAT_TOLERANCE = 1.0

DEFAULT_RESULTS_DIR = Path("results")
DEFAULT_DATA_DIR = Path("data")
DEFAULT_OUTPUT_JSON = Path("results/entry_score_report.json")
DEFAULT_OUTPUT_CSV = Path("results/entry_score_report.csv")


@dataclass(frozen=True, slots=True)
class EntryEvidenceSnapshot:
    symbol: str
    completed_bar_date: str
    close: float
    previous_close: float
    rsi: float
    previous_rsi: float
    stochastic_rsi_k: float
    stochastic_rsi_d: float
    previous_stochastic_rsi_k: float
    previous_stochastic_rsi_d: float
    macd: float
    macd_signal: float
    macd_histogram: float
    previous_macd: float
    previous_macd_signal: float
    previous_macd_histogram: float
    volume: float
    prior_20_day_average_volume: float
    volume_ratio: float
    ema20: float
    ema50: float
    ema20_extension_percent: float


@dataclass(frozen=True, slots=True)
class EntryComponentScore:
    component_id: str
    points: float
    maximum_points: float
    status: str
    evidence: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class EntryScoreRow:
    symbol: str
    entry_score: float | None
    entry_minimum: float
    entry_score_gate_passed: bool
    entry_status: str
    completed_bar_date: str | None
    bar_status: str
    evidence_status: str
    components: tuple[EntryComponentScore, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["components"] = {
            component.component_id: {
                "points": component.points,
                "maximum_points": component.maximum_points,
                "status": component.status,
                "evidence": dict(component.evidence),
            }
            for component in self.components
        }
        return payload


def calculate_entry_evidence(symbol: str, bars: Sequence[MarketBar]) -> EntryEvidenceSnapshot:
    """Calculate V1.0 timing evidence from completed chronological daily bars."""
    if len(bars) < EMA_SLOW:
        raise ValueError(f"At least {EMA_SLOW} completed daily bars are required")
    if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
        raise ValueError("daily bars must be strictly chronological")

    closes = [float(bar.close) for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    if any(not math.isfinite(value) or value <= 0 for value in closes):
        raise ValueError("daily closes must be positive finite values")
    if any(not math.isfinite(value) or value < 0 for value in volumes):
        raise ValueError("daily volume must be non-negative and finite")

    current_rsi = _required(rsi(closes, RSI_PERIOD), "RSI")
    previous_rsi = _required(rsi(closes[:-1], RSI_PERIOD), "previous RSI")

    stoch_k, stoch_d = _stochastic_rsi_kd(closes)
    previous_stoch_k, previous_stoch_d = _stochastic_rsi_kd(closes[:-1])

    macd_line, signal_line, histogram = _macd_latest(closes)
    previous_macd, previous_signal, previous_histogram = _macd_latest(closes[:-1])

    ema20 = _required(ema(closes, EMA_FAST), "EMA20")
    ema50 = _required(ema(closes, EMA_SLOW), "EMA50")
    average_volume = _required(sma(volumes[:-1], VOLUME_PERIOD), "prior 20-day average volume")
    volume_ratio = volumes[-1] / average_volume if average_volume > 0 else 0.0
    extension = ((closes[-1] - ema20) / ema20) * 100.0

    return EntryEvidenceSnapshot(
        symbol=symbol.strip().upper(),
        completed_bar_date=bars[-1].date.isoformat(),
        close=closes[-1],
        previous_close=closes[-2],
        rsi=current_rsi,
        previous_rsi=previous_rsi,
        stochastic_rsi_k=stoch_k,
        stochastic_rsi_d=stoch_d,
        previous_stochastic_rsi_k=previous_stoch_k,
        previous_stochastic_rsi_d=previous_stoch_d,
        macd=macd_line,
        macd_signal=signal_line,
        macd_histogram=histogram,
        previous_macd=previous_macd,
        previous_macd_signal=previous_signal,
        previous_macd_histogram=previous_histogram,
        volume=volumes[-1],
        prior_20_day_average_volume=average_volume,
        volume_ratio=volume_ratio,
        ema20=ema20,
        ema50=ema50,
        ema20_extension_percent=extension,
    )


def score_entry_evidence(evidence: EntryEvidenceSnapshot) -> EntryScoreRow:
    """Score an already calculated snapshot under the frozen V1.0 point model."""
    components = (
        _score_daily_rsi(evidence),
        _score_stochastic_rsi(evidence),
        _score_momentum(evidence),
        _score_volume(evidence),
        _score_price_trend(evidence),
        _score_extension(evidence),
    )
    total = round(sum(component.points for component in components), 6)
    return EntryScoreRow(
        symbol=evidence.symbol,
        entry_score=total,
        entry_minimum=ENTRY_MINIMUM,
        entry_score_gate_passed=total >= ENTRY_MINIMUM,
        entry_status="PASS" if total >= ENTRY_MINIMUM else "FAIL",
        completed_bar_date=evidence.completed_bar_date,
        bar_status="COMPLETED_DAILY_BAR",
        evidence_status="AVAILABLE",
        components=components,
    )


def evaluate_symbol_entry_score(symbol: str, bars: Sequence[MarketBar]) -> EntryScoreRow:
    """Calculate and score one signal/underlying symbol."""
    try:
        return score_entry_evidence(calculate_entry_evidence(symbol, bars))
    except (ValueError, ZeroDivisionError) as exc:
        return _pending_row(symbol, f"{type(exc).__name__}: {exc}")


def build_entry_score_report(
    *,
    results_dir: str | Path = DEFAULT_RESULTS_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    """Build Entry Score rows for every active ranked watchlist underlying."""
    if not paper_trade_mode:
        raise ValueError("Entry Score requires paper_trade_mode=True")
    results_root = Path(results_dir)
    data_root = Path(data_dir)
    watchlist_path = results_root / "watchlist_report.json"
    if not watchlist_path.is_file():
        raise FileNotFoundError(watchlist_path)

    symbols = _active_underlyings(watchlist_path)
    rows: list[EntryScoreRow] = []
    for symbol in symbols:
        path = data_root / f"{symbol}.csv"
        if not path.is_file():
            rows.append(_pending_row(symbol, f"missing completed daily market data: {path}"))
            continue
        try:
            bars = load_csv(path)
        except (OSError, ValueError) as exc:
            rows.append(_pending_row(symbol, f"{type(exc).__name__}: {exc}"))
            continue
        rows.append(evaluate_symbol_entry_score(symbol, bars))

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "entry_score_independent_from_opportunity_quality": True,
        "frozen_strategy_signal_not_part_of_entry_score": True,
        "market_regime_hard_veto_used": False,
        "price_evidence_authority": "UNLEVERAGED_SIGNAL_OR_UNDERLYING_SYMBOL_COMPLETED_DAILY_BARS",
        "missing_required_evidence_rule": "ENTRY_SCORE_NULL_AND_EVIDENCE_PENDING",
        "entry_minimum": ENTRY_MINIMUM,
        "component_maximum_points": {
            "daily_rsi_direction": RSI_POINTS,
            "daily_stochastic_rsi_k_d_relationship": STOCH_RSI_POINTS,
            "momentum_direction": MOMENTUM_POINTS,
            "volume_confirmation": VOLUME_POINTS,
            "price_trend_confirmation": PRICE_TREND_POINTS,
            "extension_and_pullback_risk": EXTENSION_POINTS,
        },
        "rows": [row.to_dict() for row in rows],
    }


def write_entry_score_report(
    payload: Mapping[str, Any],
    *,
    json_path: str | Path = DEFAULT_OUTPUT_JSON,
    csv_path: str | Path = DEFAULT_OUTPUT_CSV,
) -> tuple[Path, Path]:
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("Entry Score output must remain paper_trade_mode=true")
    json_target = Path(json_path)
    csv_target = Path(csv_path)
    _atomic_json(json_target, payload)

    rows = payload.get("rows", [])
    flat_rows = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            flat_rows.append({
                "symbol": row.get("symbol"),
                "entry_score": row.get("entry_score"),
                "entry_minimum": row.get("entry_minimum"),
                "entry_score_gate_passed": row.get("entry_score_gate_passed"),
                "entry_status": row.get("entry_status"),
                "completed_bar_date": row.get("completed_bar_date"),
                "bar_status": row.get("bar_status"),
                "evidence_status": row.get("evidence_status"),
                "error": row.get("error"),
            })
    _atomic_csv(csv_target, flat_rows)
    return json_target, csv_target


def build_and_write_entry_score_report(
    *,
    results_dir: str | Path = DEFAULT_RESULTS_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict[str, Any]:
    payload = build_entry_score_report(results_dir=results_dir, data_dir=data_dir)
    results_root = Path(results_dir)
    write_entry_score_report(
        payload,
        json_path=results_root / "entry_score_report.json",
        csv_path=results_root / "entry_score_report.csv",
    )
    return payload


def _score_daily_rsi(e: EntryEvidenceSnapshot) -> EntryComponentScore:
    delta = e.rsi - e.previous_rsi
    if delta > RSI_FLAT_TOLERANCE:
        if e.rsi >= 50.0:
            points, status = 20.0, "RISING_AT_OR_ABOVE_50"
        elif e.rsi >= 40.0:
            points, status = 15.0, "RISING_40_TO_49_99"
        else:
            points, status = 10.0, "RISING_BELOW_40"
    elif delta < -RSI_FLAT_TOLERANCE:
        if e.rsi >= 50.0:
            points, status = 5.0, "FALLING_AT_OR_ABOVE_50"
        else:
            points, status = 0.0, "FALLING_BELOW_50"
    else:
        points, status = 5.0, "FLAT"
    return EntryComponentScore(
        "daily_rsi_direction", points, RSI_POINTS, status,
        {"rsi14": round(e.rsi, 6), "previous_rsi14": round(e.previous_rsi, 6), "delta": round(delta, 6)},
    )


def _score_stochastic_rsi(e: EntryEvidenceSnapshot) -> EntryComponentScore:
    k, d, pk, pd = (
        e.stochastic_rsi_k,
        e.stochastic_rsi_d,
        e.previous_stochastic_rsi_k,
        e.previous_stochastic_rsi_d,
    )
    if abs(k - d) <= STOCH_EQUAL_TOLERANCE:
        points, status = 5.0, "K_APPROXIMATELY_EQUALS_D"
    elif pk <= pd and k > d:
        points, status = 20.0, "FRESH_BULLISH_CROSSOVER"
    elif k > d and k > pk and d >= pd:
        points, status = 20.0, "K_ABOVE_D_AND_BOTH_RISING"
    elif k > d and k >= pk - STOCH_FLAT_TOLERANCE:
        points, status = 15.0, "K_ABOVE_D_FLATTENING"
    elif k > d:
        points, status = 10.0, "K_ABOVE_D_BUT_K_DECLINING"
    else:
        points, status = 0.0, "K_BELOW_D"
    return EntryComponentScore(
        "daily_stochastic_rsi_k_d_relationship", points, STOCH_RSI_POINTS, status,
        {"k": round(k, 6), "d": round(d, 6), "previous_k": round(pk, 6), "previous_d": round(pd, 6)},
    )


def _score_momentum(e: EntryEvidenceSnapshot) -> EntryComponentScore:
    bullish_cross = e.previous_macd <= e.previous_macd_signal and e.macd > e.macd_signal
    histogram_improving = e.macd_histogram > e.previous_macd_histogram
    neutral_tolerance = max(abs(e.close) * 0.001, 1e-12)
    if bullish_cross:
        points, status = 20.0, "MACD_BULLISH_CROSSOVER"
    elif e.macd > e.macd_signal and histogram_improving:
        points, status = 20.0, "MACD_ABOVE_SIGNAL_HISTOGRAM_INCREASING"
    elif e.macd > e.macd_signal:
        points, status = 15.0, "MACD_ABOVE_SIGNAL_HISTOGRAM_WEAKENING"
    elif e.macd < e.macd_signal and histogram_improving:
        points, status = 10.0, "MACD_BELOW_SIGNAL_BUT_IMPROVING"
    elif abs(e.macd_histogram) <= neutral_tolerance:
        points, status = 5.0, "MACD_APPROXIMATELY_NEUTRAL"
    else:
        points, status = 0.0, "MACD_BELOW_SIGNAL_AND_DETERIORATING"
    return EntryComponentScore(
        "momentum_direction", points, MOMENTUM_POINTS, status,
        {
            "macd": round(e.macd, 6),
            "signal": round(e.macd_signal, 6),
            "histogram": round(e.macd_histogram, 6),
            "previous_histogram": round(e.previous_macd_histogram, 6),
        },
    )


def _score_volume(e: EntryEvidenceSnapshot) -> EntryComponentScore:
    ratio = e.volume_ratio
    if ratio >= 1.50:
        raw_points, status = 15.0, "VOLUME_GTE_1_50X"
    elif ratio >= 1.20:
        raw_points, status = 12.0, "VOLUME_GTE_1_20X"
    elif ratio >= 1.00:
        raw_points, status = 10.0, "VOLUME_GTE_1_00X"
    elif ratio >= 0.80:
        raw_points, status = 5.0, "VOLUME_GTE_0_80X"
    else:
        raw_points, status = 0.0, "VOLUME_LT_0_80X"
    positive_bar = e.close >= e.previous_close
    points = raw_points if positive_bar else min(raw_points, 5.0)
    if not positive_bar and raw_points > 5.0:
        status += "_NEGATIVE_BAR_CAPPED_AT_5"
    return EntryComponentScore(
        "volume_confirmation", points, VOLUME_POINTS, status,
        {
            "volume": e.volume,
            "prior_20_day_average_volume": round(e.prior_20_day_average_volume, 6),
            "volume_ratio": round(ratio, 6),
            "close_gte_previous_close": positive_bar,
        },
    )


def _score_price_trend(e: EntryEvidenceSnapshot) -> EntryComponentScore:
    if e.close > e.ema20 > e.ema50:
        points, status = 15.0, "CLOSE_ABOVE_EMA20_ABOVE_EMA50"
    elif e.close > e.ema20:
        points, status = 10.0, "CLOSE_ABOVE_EMA20_EMA20_NOT_ABOVE_EMA50"
    elif e.close > e.ema50:
        points, status = 5.0, "CLOSE_BELOW_EMA20_ABOVE_EMA50"
    else:
        points, status = 0.0, "CLOSE_BELOW_EMA20_AND_EMA50"
    return EntryComponentScore(
        "price_trend_confirmation", points, PRICE_TREND_POINTS, status,
        {"close": e.close, "ema20": round(e.ema20, 6), "ema50": round(e.ema50, 6)},
    )


def _score_extension(e: EntryEvidenceSnapshot) -> EntryComponentScore:
    x = e.ema20_extension_percent
    if 0.0 <= x <= 3.0:
        points, status = 10.0, "ZERO_TO_3_PERCENT_ABOVE_EMA20"
    elif 3.0 < x <= 5.0:
        points, status = 8.0, "3_TO_5_PERCENT_ABOVE_EMA20"
    elif 5.0 < x <= 8.0:
        points, status = 5.0, "5_TO_8_PERCENT_ABOVE_EMA20"
    elif 8.0 < x <= 10.0:
        points, status = 2.0, "8_TO_10_PERCENT_ABOVE_EMA20"
    elif x > 10.0:
        points, status = 0.0, "MORE_THAN_10_PERCENT_ABOVE_EMA20"
    elif -3.0 <= x < 0.0:
        points, status = 7.0, "ZERO_TO_3_PERCENT_BELOW_EMA20"
    elif -5.0 <= x < -3.0:
        points, status = 4.0, "3_TO_5_PERCENT_BELOW_EMA20"
    else:
        points, status = 0.0, "MORE_THAN_5_PERCENT_BELOW_EMA20"
    return EntryComponentScore(
        "extension_and_pullback_risk", points, EXTENSION_POINTS, status,
        {"ema20_extension_percent": round(x, 6)},
    )


def _stochastic_rsi_kd(closes: Sequence[float]) -> tuple[float, float]:
    rsi_series: list[float | None] = []
    for index in range(len(closes)):
        prefix = closes[: index + 1]
        rsi_series.append(rsi(prefix, RSI_PERIOD))

    raw: list[float | None] = [None] * len(closes)
    for index, current in enumerate(rsi_series):
        if current is None:
            continue
        window = [value for value in rsi_series[max(0, index - STOCH_RSI_PERIOD + 1) : index + 1] if value is not None]
        if len(window) < STOCH_RSI_PERIOD:
            continue
        low, high = min(window), max(window)
        raw[index] = 50.0 if high == low else ((current - low) / (high - low)) * 100.0

    k_series = _rolling_sma_optional(raw, STOCH_K_SMOOTH)
    d_series = _rolling_sma_optional(k_series, STOCH_D_SMOOTH)
    k = _required_optional(k_series[-1], "Stochastic RSI K")
    d = _required_optional(d_series[-1], "Stochastic RSI D")
    return k, d


def _rolling_sma_optional(values: Sequence[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if any(value is None for value in window):
            continue
        output[index] = sum(float(value) for value in window if value is not None) / period
    return output


def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("EMA period must be positive")
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    seed = sum(values[:period]) / period
    output[period - 1] = seed
    multiplier = 2.0 / (period + 1)
    current = seed
    for index in range(period, len(values)):
        current = (values[index] - current) * multiplier + current
        output[index] = current
    return output


def _macd_latest(closes: Sequence[float]) -> tuple[float, float, float]:
    fast = _ema_series(closes, MACD_FAST)
    slow = _ema_series(closes, MACD_SLOW)
    macd_series: list[float | None] = [
        None if f is None or s is None else f - s for f, s in zip(fast, slow)
    ]
    valid_macd = [value for value in macd_series if value is not None]
    if len(valid_macd) < MACD_SIGNAL:
        raise ValueError("insufficient completed daily bars for MACD signal")
    signal_valid = _ema_series(valid_macd, MACD_SIGNAL)
    signal_values = iter(signal_valid)
    signal_series: list[float | None] = []
    for value in macd_series:
        signal_series.append(None if value is None else next(signal_values))
    macd_value = _required_optional(macd_series[-1], "MACD")
    signal_value = _required_optional(signal_series[-1], "MACD signal")
    return macd_value, signal_value, macd_value - signal_value


def _active_underlyings(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        raw = payload.get("rows", payload.get("candidates", []))
    else:
        raw = payload
    if not isinstance(raw, list):
        raise ValueError("watchlist_report must contain rows or candidates list")
    symbols: set[str] = set()
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        capacity = str(row.get("capacity_status", "ACTIVE")).strip().upper()
        status = str(row.get("watchlist_status", "WATCHLIST")).strip().upper()
        if capacity != "ACTIVE" or status == "REMOVED":
            continue
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or row.get("ticker") or "").strip().upper()
        if symbol:
            symbols.add(symbol)
    if not symbols:
        raise ValueError("watchlist_report contains no active underlying symbols")
    return sorted(symbols)


def _pending_row(symbol: str, error: str) -> EntryScoreRow:
    return EntryScoreRow(
        symbol=symbol.strip().upper(),
        entry_score=None,
        entry_minimum=ENTRY_MINIMUM,
        entry_score_gate_passed=False,
        entry_status="EVIDENCE_PENDING",
        completed_bar_date=None,
        bar_status="UNKNOWN",
        evidence_status="PENDING",
        components=(),
        error=error,
    )


def _required(value: float | None, label: str) -> float:
    if value is None or not math.isfinite(value):
        raise ValueError(f"{label} is unavailable")
    return float(value)


def _required_optional(value: float | None, label: str) -> float:
    return _required(value, label)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, allow_nan=False, sort_keys=True)
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


def _atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "symbol", "entry_score", "entry_minimum", "entry_score_gate_passed", "entry_status",
        "completed_bar_date", "bar_status", "evidence_status", "error",
    ]
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Build paper-only Entry Score V1.0 evidence")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    payload = build_and_write_entry_score_report(results_dir=args.results_dir, data_dir=args.data_dir)
    passed = sum(1 for row in payload["rows"] if row.get("entry_score_gate_passed"))
    pending = sum(1 for row in payload["rows"] if row.get("entry_status") == "EVIDENCE_PENDING")
    print(f"Entry Score V1.0: {len(payload['rows'])} evaluated; {passed} pass; {pending} evidence pending")


if __name__ == "__main__":
    main()
