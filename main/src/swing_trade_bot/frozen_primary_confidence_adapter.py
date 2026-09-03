"""Adapt completed frozen Primary paper trades into confidence-engine metrics.

The adapter deliberately does not consume frozen_strategy_performance.json because
that artifact is a strategy simulation over the available intraday archive. Stock-
level confidence must use completed forward paper trades from the persistent paper
ledger and only those trades whose BUY-side active_strategy matches the currently
assigned frozen DIRECT Primary.

Historical frozen checkpoints and SHADOW simulations are excluded by construction.
No allocation, strategy promotion, paper execution, broker execution, or capital
movement occurs here.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False

DEFAULT_CLOSED_POSITIONS_PATH = Path("results/paper_ledger/closed_positions.json")
DEFAULT_WATCHLIST_PATH = Path("results/watchlist_report.json")
DEFAULT_METRICS_CSV_PATH = Path("results/frozen_primary_confidence_metrics.csv")
DEFAULT_PROVENANCE_JSON_PATH = Path("results/frozen_primary_confidence_metrics.json")
EVIDENCE_SCOPE = "CURRENT_FROZEN_PRIMARY_FORWARD_COMPLETED_PAPER_TRADES_ONLY"


@dataclass(frozen=True, slots=True)
class ForwardPrimaryConfidenceMetric:
    symbol: str
    vehicle_symbol: str
    signal_symbol: str
    strategy_id: str
    win_rate: float | None
    profit_factor: float | None
    number_of_trades: int
    gross_profit: float
    gross_loss: float
    realized_pnl: float
    evidence_scope: str = EVIDENCE_SCOPE


def build_forward_primary_confidence_metrics(
    *,
    closed_positions_path: Path = DEFAULT_CLOSED_POSITIONS_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    watchlist_path: Path | None = DEFAULT_WATCHLIST_PATH,
) -> tuple[ForwardPrimaryConfidenceMetric, ...]:
    """Return confidence-compatible metrics for every current frozen Primary.

    Closed trades are attributed by the BUY-side ``active_strategy`` recorded by
    ``trade_history_manager``. This preserves entry provenance: an inherited
    position closed by a newly assigned Primary is not credited to the new Primary.
    """
    closed_payload = _load_json(closed_positions_path)
    if closed_payload.get("paper_trade_mode") is not True:
        raise ValueError("closed-position evidence must be paper_trade_mode=true")
    raw_closed = closed_payload.get("closed_trades")
    if not isinstance(raw_closed, list) or any(not isinstance(row, Mapping) for row in raw_closed):
        raise ValueError("closed_positions.json must contain a closed_trades list of objects")

    watchlist_rows = _watchlist_rows(watchlist_path) if watchlist_path is not None and watchlist_path.is_file() else ()
    output: list[ForwardPrimaryConfidenceMetric] = []
    for stack in load_frozen_symbol_stacks(config_path):
        primary = stack.primary
        allocation_symbol = _allocation_symbol(
            signal_symbol=primary.signal_symbol,
            vehicle_symbol=primary.vehicle_symbol,
            watchlist_rows=watchlist_rows,
        )
        matched = [
            row
            for row in raw_closed
            if str(row.get("symbol", "")).strip().upper() == primary.vehicle_symbol
            and str(row.get("active_strategy", "")).strip().upper() == primary.strategy_id
        ]
        realized_values = [_finite_float(row.get("realized_pnl"), "closed_trade.realized_pnl") for row in matched]
        wins = [value for value in realized_values if value > 0]
        losses = [value for value in realized_values if value < 0]
        decided = len(wins) + len(losses)
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        pf: float | None
        if not matched:
            pf = None
        elif gross_loss < 0:
            pf = gross_profit / abs(gross_loss)
        elif gross_profit > 0:
            pf = math.inf
        else:
            pf = None
        output.append(
            ForwardPrimaryConfidenceMetric(
                symbol=allocation_symbol,
                vehicle_symbol=primary.vehicle_symbol,
                signal_symbol=primary.signal_symbol,
                strategy_id=primary.strategy_id,
                win_rate=None if decided == 0 else round(len(wins) / decided * 100.0, 6),
                profit_factor=None if pf is None else pf,
                number_of_trades=len(matched),
                gross_profit=round(gross_profit, 2),
                gross_loss=round(gross_loss, 2),
                realized_pnl=round(sum(realized_values), 2),
            )
        )
    return tuple(output)


def build_and_write_forward_primary_confidence_metrics(
    *,
    closed_positions_path: Path = DEFAULT_CLOSED_POSITIONS_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    watchlist_path: Path | None = DEFAULT_WATCHLIST_PATH,
    metrics_csv_path: Path = DEFAULT_METRICS_CSV_PATH,
    provenance_json_path: Path = DEFAULT_PROVENANCE_JSON_PATH,
) -> tuple[ForwardPrimaryConfidenceMetric, ...]:
    rows = build_forward_primary_confidence_metrics(
        closed_positions_path=closed_positions_path,
        config_path=config_path,
        watchlist_path=watchlist_path,
    )
    _write_csv(metrics_csv_path, rows)
    _atomic_json(
        provenance_json_path,
        {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "order_placement_enabled": False,
            "capital_movement_enabled": False,
            "evidence_scope": EVIDENCE_SCOPE,
            "source_artifact": str(closed_positions_path),
            "registry_artifact": str(config_path),
            "watchlist_artifact": None if watchlist_path is None else str(watchlist_path),
            "historical_backtest_evidence_allowed": False,
            "shadow_performance_allowed": False,
            "frozen_strategy_performance_allowed": False,
            "rows": [asdict(row) for row in rows],
        },
    )
    return rows


def _allocation_symbol(
    *,
    signal_symbol: str,
    vehicle_symbol: str,
    watchlist_rows: Sequence[Mapping[str, Any]],
) -> str:
    """Resolve the allocator/watchlist key without changing signal/vehicle authority."""
    signal = signal_symbol.strip().upper()
    vehicle = vehicle_symbol.strip().upper()
    matches = []
    for row in watchlist_rows:
        underlying = str(row.get("underlying_symbol", "")).strip().upper()
        leveraged = str(row.get("leveraged_symbol", "")).strip().upper()
        if underlying == signal or underlying == vehicle or leveraged == vehicle:
            matches.append(underlying)
    unique = sorted({value for value in matches if value})
    if len(unique) > 1:
        raise ValueError(f"ambiguous watchlist mapping for {signal}->{vehicle}: {unique}")
    return unique[0] if unique else signal


def _watchlist_rows(path: Path) -> tuple[Mapping[str, Any], ...]:
    payload = _load_json(path)
    raw = payload.get("rows")
    if not isinstance(raw, list) or any(not isinstance(row, Mapping) for row in raw):
        raise ValueError("watchlist_report.json must contain a rows list of objects")
    return tuple(raw)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _finite_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _write_csv(path: Path, rows: Sequence[ForwardPrimaryConfidenceMetric]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "symbol",
                    "win_rate",
                    "profit_factor",
                    "number_of_trades",
                    "vehicle_symbol",
                    "signal_symbol",
                    "strategy_id",
                    "evidence_scope",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "symbol": row.symbol,
                        "win_rate": "" if row.win_rate is None else row.win_rate,
                        "profit_factor": "" if row.profit_factor is None or not math.isfinite(row.profit_factor) else row.profit_factor,
                        "number_of_trades": row.number_of_trades,
                        "vehicle_symbol": row.vehicle_symbol,
                        "signal_symbol": row.signal_symbol,
                        "strategy_id": row.strategy_id,
                        "evidence_scope": row.evidence_scope,
                    }
                )
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


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, allow_nan=False)
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
