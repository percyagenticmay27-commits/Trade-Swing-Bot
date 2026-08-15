"""Persist authoritative closed-paper-trade excursion evidence.

The trade-history manager deterministically rebuilds closed positions from the
append-only paper ledger. This module enriches those derived rows with lifetime
maximum-drawdown evidence from completed daily bars and archives the evidence by
closed_trade_id so a later shortened market-data window cannot erase a drawdown
that was already observed authoritatively.

It is paper-only, performs no execution, and never writes outside the supplied
Swing ledger directory.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .paper_position_excursion import calculate_closed_long_trade_excursion

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False
SCHEMA_VERSION = "1.0"
ARCHIVE_NAME = "closed_trade_excursion_archive.json"

_DRAW_FIELDS = (
    "max_drawdown_amount",
    "max_drawdown_percent",
    "max_drawdown_peak_price",
    "max_drawdown_peak_date",
    "max_drawdown_trough_price",
    "max_drawdown_trough_date",
    "drawdown_observation_count",
    "drawdown_source",
)


def enrich_and_archive_closed_trade_excursions(
    *,
    closed_positions_path: Path,
    data_dir: Path,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    """Enrich closed_positions.json and persist immutable excursion evidence."""
    payload = _load_json(closed_positions_path)
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("closed_positions evidence must declare paper_trade_mode=true")
    rows = payload.get("closed_trades")
    if not isinstance(rows, list):
        raise ValueError("closed_positions.json must contain a closed_trades list")

    archive_file = archive_path or closed_positions_path.parent / ARCHIVE_NAME
    archive = _load_archive(archive_file)
    archived_rows = archive.get("closed_trades", {})
    if not isinstance(archived_rows, dict):
        raise ValueError("closed trade excursion archive must contain an object keyed by closed_trade_id")

    enriched: list[dict[str, Any]] = []
    warnings: list[str] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("closed trade rows must be objects")
        row = dict(raw)
        closed_id = str(row.get("closed_trade_id", "")).strip()
        symbol = str(row.get("symbol", "")).strip().upper()
        if not closed_id or not symbol:
            raise ValueError("closed_trade_id and symbol are required for excursion evidence")

        archived = archived_rows.get(closed_id)
        if isinstance(archived, Mapping):
            _validate_archive_identity(row, archived)
            for field in _DRAW_FIELDS:
                if field in archived:
                    row[field] = archived[field]
            enriched.append(row)
            continue

        evidence = None
        try:
            evidence = calculate_closed_long_trade_excursion(
                market_data_path=data_dir / f"{symbol}.csv",
                entry_date=date.fromisoformat(str(row.get("entry_date", ""))[:10]),
                exit_date=date.fromisoformat(str(row.get("exit_date", ""))[:10]),
                entry_price=float(row.get("entry_price")),
                shares=float(row.get("shares")),
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            warnings.append(f"{closed_id}: closed-trade drawdown unavailable ({exc})")

        if evidence is None:
            if not any(message.startswith(f"{closed_id}:") for message in warnings):
                warnings.append(
                    f"{closed_id}: closed-trade drawdown unavailable "
                    "(authoritative market-data history does not cover the full trade lifetime)"
                )
        else:
            values = asdict(evidence)
            values["drawdown_observation_count"] = values.pop("observation_count")
            values["drawdown_source"] = values.pop("source")
            row.update(values)
            archived_rows[closed_id] = {
                "closed_trade_id": closed_id,
                "symbol": symbol,
                "entry_date": row.get("entry_date"),
                "exit_date": row.get("exit_date"),
                "entry_price": row.get("entry_price"),
                "exit_price": row.get("exit_price"),
                "shares": row.get("shares"),
                **values,
            }
        enriched.append(row)

    payload["closed_trades"] = enriched
    payload["drawdown_evidence_policy"] = "AUTHORITATIVE_COMPLETED_DAILY_BARS_WITH_PERSISTED_ARCHIVE"
    payload["drawdown_inference_allowed"] = False
    payload["drawdown_warnings"] = warnings
    _atomic_json(closed_positions_path, payload)
    _atomic_json(
        archive_file,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "order_placement_enabled": False,
            "capital_movement_enabled": False,
            "direct_database_writes": False,
            "closed_trades": archived_rows,
        },
    )
    return payload


def _validate_archive_identity(current: Mapping[str, Any], archived: Mapping[str, Any]) -> None:
    for field in ("closed_trade_id", "symbol", "entry_date", "exit_date", "entry_price", "exit_price", "shares"):
        if archived.get(field) != current.get(field):
            raise ValueError(
                f"archived closed-trade excursion identity mismatch for {current.get('closed_trade_id')}: {field}"
            )


def _load_archive(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "paper_trade_mode": True,
            "closed_trades": {},
        }
    payload = _load_json(path)
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("closed trade excursion archive must declare paper_trade_mode=true")
    for field in (
        "live_trading_enabled",
        "broker_execution_enabled",
        "order_placement_enabled",
        "capital_movement_enabled",
        "direct_database_writes",
    ):
        if payload.get(field, False) is not False:
            raise ValueError(f"unsafe closed trade excursion archive value: {field}")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
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
