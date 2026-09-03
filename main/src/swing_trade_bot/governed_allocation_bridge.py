"""Bridge forward Primary confidence and committee eligibility into allocation.

The bridge is paper-only and fail-closed. It refreshes confidence from completed
current-Primary paper trades, rebuilds current committee allocation eligibility,
and passes only symbols that are both committee-eligible and backed by explicit
forward-confidence rows to the existing portfolio allocation engine.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .committee_allocation_eligibility import build_and_write_committee_allocation_eligibility
from .confidence_engine import build_confidence_report
from .frozen_primary_confidence_adapter import build_and_write_forward_primary_confidence_metrics
from .portfolio_allocation_engine import build_portfolio_allocation_report

PAPER_TRADE_MODE = True
FORWARD_POLICY_VERSION = "FORWARD_PRIMARY_V1"


def refresh_forward_confidence_and_governed_allocation(
    *,
    results_dir: Path = Path("results"),
    ledger_dir: Path = Path("results/paper_ledger"),
    data_dir: Path = Path("data"),
    config_path: Path = Path("configs/frozen_strategy_assignments.json"),
    strategy_recommendations_path: Path = Path("results/strategy_recommendations.csv"),
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    if not paper_trade_mode:
        raise ValueError("Governed allocation bridge requires paper_trade_mode=True")
    results_dir = Path(results_dir)
    ledger_dir = Path(ledger_dir)
    watchlist_path = results_dir / "watchlist_report.json"
    closed_positions_path = ledger_dir / "closed_positions.json"
    if not closed_positions_path.is_file():
        raise FileNotFoundError(closed_positions_path)
    if not watchlist_path.is_file():
        raise FileNotFoundError(watchlist_path)
    if not strategy_recommendations_path.is_file():
        raise FileNotFoundError(strategy_recommendations_path)

    metrics_csv = results_dir / "frozen_primary_confidence_metrics.csv"
    metrics_json = results_dir / "frozen_primary_confidence_metrics.json"
    metrics = build_and_write_forward_primary_confidence_metrics(
        closed_positions_path=closed_positions_path,
        config_path=config_path,
        watchlist_path=watchlist_path,
        metrics_csv_path=metrics_csv,
        provenance_json_path=metrics_json,
    )

    confidence_path = results_dir / "confidence_report.json"
    starting = _prior_forward_confidence(confidence_path)
    candidate_symbols = [row.symbol for row in metrics]
    confidence_rows = build_confidence_report(
        metrics_csv,
        Path(data_dir),
        output_dir=results_dir,
        starting_confidence=starting,
        candidate_symbols=candidate_symbols,
        paper_trade_mode=True,
    )

    eligibility_path = results_dir / "committee_allocation_eligibility.json"
    eligibility = build_and_write_committee_allocation_eligibility(
        results_dir,
        eligibility_path,
        paper_trade_mode=True,
    )
    eligible = {str(value).strip().upper() for value in eligibility.get("eligible_symbols", [])}
    confidence_symbols = {row.symbol for row in confidence_rows}
    governed_symbols = sorted(eligible & confidence_symbols)
    missing_confidence = sorted(eligible - confidence_symbols)

    with _filtered_inputs(
        results_dir=results_dir,
        watchlist_path=watchlist_path,
        confidence_csv=results_dir / "confidence_report.csv",
        strategy_path=Path(strategy_recommendations_path),
        symbols=set(governed_symbols),
    ) as filtered:
        report = build_portfolio_allocation_report(
            confidence_path=filtered["confidence"],
            watchlist_path=filtered["watchlist"],
            strategy_recommendations_path=filtered["strategy"],
            output_dir=results_dir,
            paper_trade_mode=True,
        )

    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "confidence_policy_version": FORWARD_POLICY_VERSION,
        "eligible_symbols": sorted(eligible),
        "forward_confidence_symbols": sorted(confidence_symbols),
        "governed_allocation_symbols": governed_symbols,
        "eligible_symbols_missing_forward_confidence": missing_confidence,
        "allocation_row_count": len(report.rows),
        "sgov_allocation": report.sgov_allocation,
        "allocation_bypass_allowed": False,
    }


def _prior_forward_confidence(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("confidence_policy_version") != FORWARD_POLICY_VERSION:
        return {}
    raw = payload.get("rows")
    if not isinstance(raw, list):
        return {}
    output: dict[str, str] = {}
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        confidence = str(row.get("confidence", "")).strip().upper()
        if symbol and confidence in {"LOW", "MEDIUM", "HIGH", "WATCHLIST"}:
            output[symbol] = confidence
    return output


class _filtered_inputs:
    def __init__(self, *, results_dir: Path, watchlist_path: Path, confidence_csv: Path, strategy_path: Path, symbols: set[str]) -> None:
        self.results_dir = results_dir
        self.watchlist_path = watchlist_path
        self.confidence_csv = confidence_csv
        self.strategy_path = strategy_path
        self.symbols = symbols
        self.paths: dict[str, Path] = {}

    def __enter__(self) -> dict[str, Path]:
        temp_dir = self.results_dir / ".governed_allocation_inputs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        confidence = temp_dir / "confidence.csv"
        strategy = temp_dir / "strategy.csv"
        watchlist = temp_dir / "watchlist.json"
        _filter_csv(self.confidence_csv, confidence, "symbol", self.symbols)
        _filter_csv(self.strategy_path, strategy, "symbol", self.symbols)
        payload = json.loads(self.watchlist_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise ValueError("watchlist_report.json must contain rows list")
        filtered_rows = []
        for row in payload["rows"]:
            if not isinstance(row, Mapping):
                continue
            underlying = str(row.get("underlying_symbol", "")).strip().upper()
            leveraged = str(row.get("leveraged_symbol", "")).strip().upper()
            if underlying in self.symbols or leveraged in self.symbols:
                filtered_rows.append(dict(row))
        filtered_payload = dict(payload)
        filtered_payload["rows"] = filtered_rows
        watchlist.write_text(json.dumps(filtered_payload, indent=2) + "\n", encoding="utf-8")
        self.paths = {"confidence": confidence, "strategy": strategy, "watchlist": watchlist}
        return self.paths

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for path in self.paths.values():
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        temp_dir = self.results_dir / ".governed_allocation_inputs"
        try:
            temp_dir.rmdir()
        except OSError:
            pass


def _filter_csv(source: Path, destination: Path, symbol_field: str, symbols: set[str]) -> None:
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or symbol_field not in reader.fieldnames:
            raise ValueError(f"{source} missing required column {symbol_field}")
        rows = [row for row in reader if str(row.get(symbol_field, "")).strip().upper() in symbols]
        fields = list(reader.fieldnames)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
