"""Provider-neutral, read-only Swing client for Enterprise Market Data v1.0."""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "1.0"
STRATEGY_ID = "SWING-001"
DEFAULT_STATUS_PATH = Path("/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json")
DEFAULT_CONTRACT_PATH = Path("/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json")
DEFAULT_HEALTH_PATH = Path("/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_provider_health.json")
PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


class MarketDataUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EnterpriseQuote:
    symbol: str
    price: float
    quote_timestamp: str
    trading_date: str
    provider: str
    source_type: str
    confidence: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EnterpriseBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


@dataclass(frozen=True, slots=True)
class EnterpriseHistory:
    symbol: str
    interval: str
    period: str
    provider: str
    generated_at: str
    latest_bar_date: str
    corporate_action_adjusted: bool
    bars: tuple[EnterpriseBar, ...]
    warnings: tuple[str, ...] = ()


class EnterpriseMarketDataClient:
    """Reads AI CIO-published evidence; never selects or invokes providers."""

    def __init__(self, *, contract_path: Path = DEFAULT_CONTRACT_PATH,
                 status_path: Path = DEFAULT_STATUS_PATH,
                 strategy_id: str = STRATEGY_ID) -> None:
        self.contract_path = Path(contract_path)
        self.status_path = Path(status_path)
        self.strategy_id = strategy_id
        self.warnings: list[str] = []
        self._contract = _read_object(self.contract_path)
        self._status = _read_object(self.status_path)
        version = str(self._contract.get("contract_version") or self._contract.get("schema_version") or self._contract.get("version") or "")
        if version != CONTRACT_VERSION:
            raise MarketDataUnavailable(f"Enterprise market-data contract version {version or 'MISSING'} is unsupported")
        self._strategy = self._find_strategy()
        status = str(self._strategy.get("status", "")).upper()
        if status not in {"READY", "WARNING"}:
            raise MarketDataUnavailable(f"{strategy_id} market-data status is {status or 'MISSING'}")
        if status == "WARNING":
            self.warnings.append(f"{strategy_id} Enterprise market-data status is WARNING")

    def get_quote(self, symbol: str, *, required: bool = True) -> EnterpriseQuote | None:
        record = self._symbol_record(symbol, required=required)
        if record is None:
            return None
        payload = _payload(record, "quote")
        if payload is None or bool(payload.get("stale", True)):
            return self._missing(symbol, "fresh quote", required)
        timestamp = str(payload.get("quote_timestamp", "")).strip()
        trading_date = str(payload.get("trading_date", "")).strip()
        if not timestamp or not trading_date:
            return self._missing(symbol, "quote timestamp/date", required)
        return EnterpriseQuote(
            symbol=symbol.upper(), price=_positive(payload.get("price"), f"{symbol}.price"),
            quote_timestamp=timestamp, trading_date=trading_date,
            provider=str(payload.get("provider", "ENTERPRISE")),
            source_type=str(payload.get("source_type", "NORMALIZED_QUOTE")),
            confidence=_bounded(payload.get("confidence", 0.0), "confidence"),
            warnings=tuple(str(x) for x in payload.get("warnings", []) if str(x)),
        )

    def get_history(self, symbol: str, *, required: bool = True) -> EnterpriseHistory | None:
        record = self._symbol_record(symbol, required=required)
        if record is None:
            return None
        payload = _payload(record, "history")
        if payload is None or bool(payload.get("stale", True)):
            return self._missing(symbol, "fresh history", required)
        raw = payload.get("bars")
        if not isinstance(raw, list) or not raw:
            return self._missing(symbol, "history bars", required)
        bars: list[EnterpriseBar] = []
        seen: set[str] = set()
        for row in raw:
            if not isinstance(row, Mapping):
                raise MarketDataUnavailable(f"{symbol} history contains malformed bar")
            day = str(row.get("date", "")).strip()
            try:
                date.fromisoformat(day)
            except ValueError as exc:
                raise MarketDataUnavailable(f"{symbol} history contains invalid date") from exc
            if day in seen:
                raise MarketDataUnavailable(f"{symbol} history contains duplicate bar {day}")
            seen.add(day)
            close = _positive(row.get("close"), f"{symbol}.{day}.close")
            bar = EnterpriseBar(
                date=day, open=_positive(row.get("open"), f"{symbol}.{day}.open"),
                high=_positive(row.get("high"), f"{symbol}.{day}.high"),
                low=_positive(row.get("low"), f"{symbol}.{day}.low"), close=close,
                adjusted_close=_positive(row.get("adjusted_close", close), f"{symbol}.{day}.adjusted_close"),
                volume=_nonnegative_int(row.get("volume"), f"{symbol}.{day}.volume"),
            )
            if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                raise MarketDataUnavailable(f"{symbol} history contains invalid OHLC for {day}")
            bars.append(bar)
        if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
            raise MarketDataUnavailable(f"{symbol} history is not strictly chronological")
        latest = str(payload.get("latest_bar_date", "")).strip()
        if latest != bars[-1].date:
            raise MarketDataUnavailable(f"{symbol} latest_bar_date does not match final bar")
        return EnterpriseHistory(
            symbol=symbol.upper(), interval=str(payload.get("interval", "1d")),
            period=str(payload.get("period", "")), provider=str(payload.get("provider", "ENTERPRISE")),
            generated_at=str(payload.get("generated_at", "")), latest_bar_date=latest,
            corporate_action_adjusted=bool(payload.get("corporate_action_adjusted", False)),
            bars=tuple(bars), warnings=tuple(str(x) for x in payload.get("warnings", []) if str(x)),
        )

    def write_history_csv(self, symbol: str, destination: Path, *, required: bool = True) -> Path | None:
        history = self.get_history(symbol, required=required)
        if history is None:
            return None
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(("Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"))
                for bar in history.bars:
                    writer.writerow((bar.date, bar.open, bar.high, bar.low, bar.close, bar.adjusted_close, bar.volume))
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return destination

    def _find_strategy(self) -> Mapping[str, Any]:
        if str(self._status.get("strategy_id", "")) == self.strategy_id:
            return self._status
        for key in ("strategies", "strategy_statuses", "strategy_results"):
            value = self._status.get(key)
            if isinstance(value, Mapping) and isinstance(value.get(self.strategy_id), Mapping):
                return value[self.strategy_id]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping) and str(item.get("strategy_id", "")) == self.strategy_id:
                        return item
        raise MarketDataUnavailable(f"{self.strategy_id} record missing from Enterprise market-data status")

    def _symbol_record(self, symbol: str, *, required: bool) -> Mapping[str, Any] | None:
        target = symbol.upper()
        for key in ("symbols", "symbol_results", "records", "market_data"):
            value = self._strategy.get(key)
            if isinstance(value, Mapping) and isinstance(value.get(target), Mapping):
                return value[target]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping) and str(item.get("symbol", "")).upper() == target:
                        return item
        return self._missing(target, "symbol record", required)

    def _missing(self, symbol: str, detail: str, required: bool):
        message = f"{symbol.upper()} {'required ' if required else 'optional '}{detail} unavailable"
        if required:
            raise MarketDataUnavailable(message)
        self.warnings.append(message)
        return None


def _payload(record: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    value = record.get(kind)
    if isinstance(value, Mapping): return value
    value = record.get(kind + "s")
    if isinstance(value, Mapping): return value
    if kind == "quote" and "price" in record: return record
    if kind == "history" and "bars" in record: return record
    return None


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists(): raise MarketDataUnavailable(f"Enterprise market-data evidence missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict): raise MarketDataUnavailable(f"Expected JSON object: {path}")
    return payload


def _positive(value: Any, field: str) -> float:
    try: number = float(value)
    except (TypeError, ValueError) as exc: raise MarketDataUnavailable(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0: raise MarketDataUnavailable(f"{field} must be finite and positive")
    return number


def _bounded(value: Any, field: str) -> float:
    try: number = float(value)
    except (TypeError, ValueError) as exc: raise MarketDataUnavailable(f"{field} must be numeric") from exc
    if not math.isfinite(number) or not 0 <= number <= 1: raise MarketDataUnavailable(f"{field} must be between 0 and 1")
    return number


def _nonnegative_int(value: Any, field: str) -> int:
    try: number = int(value)
    except (TypeError, ValueError) as exc: raise MarketDataUnavailable(f"{field} must be an integer") from exc
    if number < 0: raise MarketDataUnavailable(f"{field} must be nonnegative")
    return number
