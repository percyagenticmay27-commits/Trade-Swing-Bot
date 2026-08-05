"""Materialize fresh AI CIO normalized history for existing Swing analytics.

The AI CIO owns provider selection and publishes normalized history exports.
Swing reads the export directory and filename pattern from the Version 1.0
contract, validates the corresponding fresh status evidence, and atomically
copies each approved CSV into results/enterprise_market_data.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from swing_trade_bot.enterprise_market_data_client import CONTRACT_VERSION, MarketDataUnavailable
from swing_trade_bot.enterprise_paper_portfolio_manager import write_blocked_state


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MarketDataUnavailable(f"Enterprise market-data evidence missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MarketDataUnavailable(f"Expected JSON object: {path}")
    return payload


def _find_strategy(status: Mapping[str, Any], strategy_id: str) -> Mapping[str, Any]:
    if str(status.get("strategy_id", "")) == strategy_id:
        return status
    for key in ("strategies", "strategy_statuses", "strategy_results"):
        value = status.get(key)
        if isinstance(value, Mapping) and isinstance(value.get(strategy_id), Mapping):
            return value[strategy_id]
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and str(item.get("strategy_id", "")) == strategy_id:
                    return item
    raise MarketDataUnavailable(f"{strategy_id} record missing from Enterprise market-data status")


def _find_symbol(strategy: Mapping[str, Any], symbol: str) -> Mapping[str, Any] | None:
    target = symbol.upper()
    for key in ("symbols", "symbol_results", "records", "market_data"):
        value = strategy.get(key)
        if isinstance(value, Mapping) and isinstance(value.get(target), Mapping):
            return value[target]
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and str(item.get("symbol", "")).upper() == target:
                    return item
    return None


def _history_payload(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("history", "histories"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return value
    return record if "latest_bar_date" in record else None


def _history_exports(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the declared export contract without requiring a legacy flag.

    Version 1.0 deployments may declare an export through directory/pattern
    fields and omit ``enabled``. An explicit ``enabled: false`` still disables
    the export. This is contract compatibility only; it does not relax any
    history freshness or validation rule.
    """
    exports = contract.get("history_exports")
    if not isinstance(exports, Mapping):
        raise MarketDataUnavailable("Enterprise history exports are not declared")
    if "enabled" in exports and exports.get("enabled") is not True:
        raise MarketDataUnavailable("Enterprise history exports are not enabled")
    return exports


def _export_source(contract_path: Path, contract: Mapping[str, Any], symbol: str) -> Path:
    exports = _history_exports(contract)
    directory = str(exports.get("directory", "")).strip()
    pattern = str(exports.get("csv_pattern", "{symbol}.csv")).strip()
    if not directory or not pattern:
        raise MarketDataUnavailable("Enterprise history export directory/pattern is missing")
    try:
        filename = pattern.format(symbol=symbol.upper())
    except (KeyError, ValueError) as exc:
        raise MarketDataUnavailable("Enterprise history csv_pattern is invalid") from exc

    root = contract_path.parent.resolve()
    export_dir = Path(directory)
    if not export_dir.is_absolute():
        export_dir = root / export_dir
    export_dir = export_dir.resolve()
    if root != export_dir and root not in export_dir.parents:
        raise MarketDataUnavailable("Enterprise history export directory escapes the evidence root")

    source = (export_dir / filename).resolve()
    if export_dir != source.parent:
        raise MarketDataUnavailable("Enterprise history export filename escapes the export directory")
    return source


def _validate_export(path: Path, symbol: str, expected_latest: str) -> None:
    if not path.exists():
        raise MarketDataUnavailable(f"{symbol} Enterprise history export missing: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise MarketDataUnavailable(f"{symbol} Enterprise history export has no headers")
        names = {name.strip().lower().replace("_", " "): name for name in reader.fieldnames}
        required = ("date", "open", "high", "low", "close", "volume")
        if any(field not in names for field in required):
            raise MarketDataUnavailable(f"{symbol} Enterprise history export is missing required columns")

        previous: date | None = None
        latest = ""
        count = 0
        for row in reader:
            try:
                bar_date = date.fromisoformat(str(row[names["date"]]).strip())
                values = [float(row[names[field]]) for field in ("open", "high", "low", "close")]
                volume = float(row[names["volume"]])
            except (TypeError, ValueError) as exc:
                raise MarketDataUnavailable(f"{symbol} Enterprise history export contains malformed data") from exc
            if previous is not None and bar_date <= previous:
                raise MarketDataUnavailable(f"{symbol} Enterprise history export is not strictly chronological")
            if any(not math.isfinite(value) or value <= 0 for value in values):
                raise MarketDataUnavailable(f"{symbol} Enterprise history export contains invalid OHLC data")
            open_, high, low, close = values
            if high < max(open_, close) or low > min(open_, close):
                raise MarketDataUnavailable(f"{symbol} Enterprise history export contains invalid OHLC relationships")
            if not math.isfinite(volume) or volume < 0:
                raise MarketDataUnavailable(f"{symbol} Enterprise history export contains invalid volume")
            previous = bar_date
            latest = bar_date.isoformat()
            count += 1

    if count == 0:
        raise MarketDataUnavailable(f"{symbol} Enterprise history export contains no bars")
    if not expected_latest or latest != expected_latest:
        raise MarketDataUnavailable(f"{symbol} Enterprise history export latest bar does not match status evidence")


def _atomic_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return destination


def sync_exported_history(
    *,
    contract_path: Path,
    status_path: Path,
    output_dir: Path,
    required_symbols: list[str],
    optional_symbols: list[str],
    strategy_id: str = "SWING-001",
) -> dict[str, Any]:
    contract = _read_object(contract_path)
    version = str(contract.get("contract_version") or contract.get("schema_version") or contract.get("version") or "")
    if version != CONTRACT_VERSION:
        raise MarketDataUnavailable(f"Enterprise market-data contract version {version or 'MISSING'} is unsupported")

    status = _read_object(status_path)
    strategy = _find_strategy(status, strategy_id)
    strategy_status = str(strategy.get("status", "")).upper()
    if strategy_status not in {"READY", "WARNING"}:
        raise MarketDataUnavailable(f"{strategy_id} market-data status is {strategy_status or 'MISSING'}")

    warnings: list[str] = []
    if strategy_status == "WARNING":
        warnings.append(f"{strategy_id} Enterprise market-data status is WARNING")
    written: list[str] = []

    def materialize(symbol: str, required: bool) -> None:
        target = symbol.upper()
        record = _find_symbol(strategy, target)
        payload = _history_payload(record) if record is not None else None
        if payload is None or bool(payload.get("stale", True)):
            message = f"{target} {'required' if required else 'optional'} fresh history unavailable"
            if required:
                raise MarketDataUnavailable(message)
            warnings.append(message)
            return

        latest = str(payload.get("latest_bar_date", "")).strip()
        source = _export_source(contract_path, contract, target)
        try:
            _validate_export(source, target, latest)
        except MarketDataUnavailable as exc:
            if required:
                raise
            warnings.append(str(exc))
            return
        destination = _atomic_copy(source, output_dir / f"{target}.csv")
        written.append(str(destination))

    for symbol in dict.fromkeys(required_symbols):
        materialize(symbol, True)
    for symbol in dict.fromkeys(optional_symbols):
        materialize(symbol, False)

    result = {
        "strategy_id": strategy_id,
        "status": "READY" if not warnings else "WARNING",
        "normalized_history_files": written,
        "warnings": warnings,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "sync_status.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-path", default="/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json")
    parser.add_argument("--status-path", default="/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json")
    parser.add_argument("--output-dir", default="results/enterprise_market_data")
    parser.add_argument("--required-symbol", action="append", default=["SOXL", "TQQQ"])
    parser.add_argument("--optional-symbol", action="append", default=[])
    args = parser.parse_args()
    try:
        result = sync_exported_history(
            contract_path=Path(args.contract_path),
            status_path=Path(args.status_path),
            output_dir=Path(args.output_dir),
            required_symbols=args.required_symbol,
            optional_symbols=args.optional_symbol,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except MarketDataUnavailable as exc:
        path = write_blocked_state(Path("results/paper_ledger"), exc)
        print(json.dumps({"strategy_id": "SWING-001", "status": "BLOCKED", "artifact": str(path), "reason": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
