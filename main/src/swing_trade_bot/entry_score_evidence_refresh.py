"""Refresh current Daily evidence before publishing Entry Score V1.0.

This module is an operational wrapper around the already-frozen Entry Score
engine.  It does not change scoring weights, component semantics, Opportunity
Quality, strategy entry triggers, allocation, or execution.

Entry Score is a current deployment-timing gate, so only FRESH completed Daily
market-data evidence may authorize a numeric score.  WARNING, STALE, MISSING,
or failed refresh evidence is converted to EVIDENCE_PENDING for that symbol.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .entry_score_engine import (
    ENTRY_MINIMUM,
    build_entry_score_report,
    write_entry_score_report,
)
from .market_data_chain_factory import build_configured_provider_chain
from .market_data_provider import MarketDataProvider
from .market_data_refresh import (
    load_market_data_config,
    refresh_market_data,
)
from .providers.robinhood_agent_provider import McpInvoker

SCHEMA_VERSION = "1.0"
MODULE_VERSION = "1.0.0"
STRATEGY_ID = "SWING-001"
DEFAULT_RESULTS_DIR = Path("results")
DEFAULT_DATA_DIR = Path("data")
DEFAULT_CONFIG_PATH = Path("configs/swing_market_data.json")
DEFAULT_REFRESH_OUTPUT = Path("results/entry_score_market_data_refresh.json")


def active_entry_underlyings(watchlist_path: str | Path) -> tuple[str, ...]:
    """Return unique ACTIVE underlying symbols from the current Swing watchlist."""
    payload = json.loads(Path(watchlist_path).read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("watchlist_report.rows must be a list")

    symbols: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("capacity_status", "")).strip().upper() != "ACTIVE":
            continue
        symbol = str(row.get("underlying_symbol", "")).strip().upper()
        if symbol:
            symbols.add(symbol)
    if not symbols:
        raise ValueError("watchlist_report contains no ACTIVE underlying symbols")
    return tuple(sorted(symbols))


def build_entry_market_data_config(
    base_config: Mapping[str, Any],
    *,
    symbols: Sequence[str],
) -> dict[str, Any]:
    """Create an isolated market-data config for current Entry Score underlyings.

    The global market-data configuration is not mutated.  Entry Score symbols are
    treated as required configured-strategy requests so a provider failure is
    visible in the refresh report.  Per-symbol scoring still fails closed without
    suppressing valid evidence for other symbols.
    """
    config = copy.deepcopy(dict(base_config))
    normalized = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    if not normalized:
        raise ValueError("Entry Score market-data refresh requires at least one symbol")
    config["configured_strategy_symbols"] = normalized
    config["portfolio_symbols"] = []
    config["watchlist_symbols"] = []
    config["candidate_symbols"] = []
    return config


def _provider_factory_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Translate publication config to runnable provider-factory configuration.

    PRIOR_LOCAL_CSV is not a network provider.  market_data_refresh owns that
    fallback after provider failure, so it must not be passed to the factory.
    """
    payload = dict(config)
    raw_order = payload.get("provider_order")
    if isinstance(raw_order, Sequence) and not isinstance(raw_order, (str, bytes)):
        payload["provider_order"] = [
            str(item).strip().upper()
            for item in raw_order
            if str(item).strip().upper() != "PRIOR_LOCAL_CSV"
        ]
    return payload


def _pending_entry_row(symbol: str, error: str, *, completed_bar_date: str | None = None) -> dict[str, Any]:
    return {
        "symbol": symbol.strip().upper(),
        "entry_score": None,
        "entry_minimum": ENTRY_MINIMUM,
        "entry_score_gate_passed": False,
        "entry_status": "EVIDENCE_PENDING",
        "completed_bar_date": completed_bar_date,
        "bar_status": "UNKNOWN" if completed_bar_date is None else "COMPLETED_DAILY_BAR_NOT_CURRENT",
        "evidence_status": "PENDING",
        "components": {},
        "error": error,
    }


def enforce_fresh_entry_evidence(
    score_payload: Mapping[str, Any],
    refresh_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Mask every non-FRESH symbol to fail-closed EVIDENCE_PENDING."""
    freshness_by_symbol: dict[str, Mapping[str, Any]] = {}
    for item in refresh_payload.get("symbol_results", []):
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if symbol:
            freshness_by_symbol[symbol] = item

    governed = copy.deepcopy(dict(score_payload))
    governed_rows: list[dict[str, Any]] = []
    for raw_row in governed.get("rows", []):
        if not isinstance(raw_row, Mapping):
            continue
        row = dict(raw_row)
        symbol = str(row.get("symbol", "")).strip().upper()
        market = freshness_by_symbol.get(symbol)
        freshness = str(market.get("freshness_status", "MISSING")).strip().upper() if market else "MISSING"
        errors = market.get("errors", []) if market else []
        usable = bool(market) and freshness == "FRESH" and not errors
        if usable:
            governed_rows.append(row)
            continue

        latest = market.get("latest_completed_date") if market else None
        reason_parts = [f"current Daily market data is {freshness}"]
        if errors:
            if isinstance(errors, (list, tuple)):
                reason_parts.append("; ".join(str(item) for item in errors if item))
            else:
                reason_parts.append(str(errors))
        governed_rows.append(_pending_entry_row(symbol, ": ".join(reason_parts), completed_bar_date=str(latest) if latest else None))

    governed["rows"] = governed_rows
    governed["current_daily_evidence_required"] = True
    governed["accepted_market_data_freshness"] = ["FRESH"]
    governed["warning_market_data_authorizes_entry_score"] = False
    governed["stale_market_data_authorizes_entry_score"] = False
    return governed


def _write_json(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True, allow_nan=False)
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


def refresh_entry_score_evidence(
    *,
    project_root: str | Path = ".",
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    results_dir: str | Path = DEFAULT_RESULTS_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    provider: MarketDataProvider | None = None,
    invoke_mcp: McpInvoker | None = None,
) -> dict[str, Any]:
    """Refresh Daily evidence, then publish freshness-governed Entry Score V1.0."""
    root = Path(project_root).resolve()
    results_root = Path(results_dir)
    if not results_root.is_absolute():
        results_root = root / results_root
    data_root = Path(data_dir)
    if not data_root.is_absolute():
        data_root = root / data_root
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file

    watchlist_path = results_root / "watchlist_report.json"
    symbols = active_entry_underlyings(watchlist_path)
    base_config = load_market_data_config(config_file)
    config = build_entry_market_data_config(base_config, symbols=symbols)
    config["data_directory"] = str(data_root.relative_to(root)) if data_root.is_relative_to(root) else str(data_root)

    market_provider = provider or build_configured_provider_chain(
        config=_provider_factory_config(config),
        invoke_mcp=invoke_mcp,
    )
    report = refresh_market_data(config, market_provider, project_root=root)
    refresh_payload = report.to_dict()
    refresh_payload.update({
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "entry_score_symbols": list(symbols),
        "entry_score_freshness_policy": "FRESH_ONLY",
        "warning_authorizes_numeric_entry_score": False,
        "stale_authorizes_numeric_entry_score": False,
    })
    _write_json(refresh_payload, results_root / "entry_score_market_data_refresh.json")

    raw_scores = build_entry_score_report(results_dir=results_root, data_dir=data_root)
    governed_scores = enforce_fresh_entry_evidence(raw_scores, refresh_payload)
    write_entry_score_report(
        governed_scores,
        json_path=results_root / "entry_score_report.json",
        csv_path=results_root / "entry_score_report.csv",
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "symbols": list(symbols),
        "market_data_overall_status": refresh_payload.get("overall_status"),
        "fresh_symbols": [
            item.get("symbol") for item in refresh_payload.get("symbol_results", [])
            if isinstance(item, Mapping) and item.get("freshness_status") == "FRESH" and not item.get("errors")
        ],
        "entry_score_pass_symbols": [
            row.get("symbol") for row in governed_scores.get("rows", [])
            if isinstance(row, Mapping) and row.get("entry_score_gate_passed") is True
        ],
        "entry_score_pending_symbols": [
            row.get("symbol") for row in governed_scores.get("rows", [])
            if isinstance(row, Mapping) and row.get("entry_status") == "EVIDENCE_PENDING"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh current Daily evidence and publish Entry Score V1.0")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    summary = refresh_entry_score_evidence(
        project_root=args.root,
        config_path=args.config,
        results_dir=args.results_dir,
        data_dir=args.data_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
