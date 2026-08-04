"""Read-only Swing adapter for AI CIO Enterprise Market Data Provider v1.0.

The adapter reads normalized host evidence only. It never imports Dividend
production modules and never calls Codex, Robinhood, yfinance, or Stooq.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    """Fresh normalized Enterprise market data is unavailable for SWING-001."""


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
    def __init__(
        self,
        *,
        contract_path: Path = DEFAULT_CONTRACT_PATH,
        status_path: Path = DEFAULT_STATUS_PATH,
        strategy_id: str = STRATEGY_ID,
    ) -> None:
        self.contract_path = Path(contract_path)
        self.status_path = Path(status_path)
        self.strategy_id = strategy_id
        self._contract = self._read_object(self.contract_path)
        self._status = self._read_object(self.status_path)
        self._validate_contract()
        self._strategy = self._find_strategy_record()
        status = str(self._strategy.get("status", "")).upper()
        if status not in {"READY", "WARNING"}:
            raise MarketDataUnavailable(f"{strategy_id} market-data status is {status or 'MISSING'}")

    def get_quote(self, symbol: str, *, required: bool = True) -> EnterpriseQuote | None:
        record = self._symbol_record(symbol)
        payload = self._extract_payload(record, "quote")
        if payload is None:
            return self._missing(symbol, "quote", required)
        if bool(payload.get("stale", True)):
            return self._missing(symbol, "quote is stale", required)
        price = _positive(payload.get("price"), f"{symbol}.price")
        timestamp = str(payload.get("quote_timestamp", "")).strip()
        trading_date = str(payload.get("trading_date", "")).strip()
        if not timestamp or not trading_date:
            return self._missing(symbol, "quote timestamp/date missing", required)
        return EnterpriseQuote(
            symbol=symbol.upper(), price=price, quote_timestamp=timestamp,
            trading_date=trading_date, provider=str(payload.get("provider", "ENTERPRISE")),
            source_type=str(payload.get("source_type", "NORMALIZED_QUOTE")),
            confidence=_bounded(payload.get("confidence", 0.0), "confidence"),
            warnings=tuple(str(x) for x in payload.get("warnings", []) if str(x)),
        )

    def get_history(self, symbol: str, *, required: bool = True) -> EnterpriseHistory | None:
        record = self._symbol_record(symbol)
        payload = self._extract_payload(record, "history")
        if payload is None:
            return self._missing(symbol, "history", required)
        if bool(payload.get("stale", True)):
            return self._missing(symbol, "history is stale", required)
        raw_bars = payload.get("bars")
        if not isinstance(raw_bars, list) or not raw_bars:
            return self._missing(symbol, "history bars missing", required)
        bars: list[EnterpriseBar] = []
        seen: set[str] = set()
        for row in raw_bars:
            if not isinstance(row, Mapping):
                raise MarketDataUnavailable(f"{symbol} history contains malformed bar")
            day = str(row.get("date", "")).strip()
            date.fromisoformat(day)
            if day in seen:
                raise MarketDataUnavailable(f"{symbol} history contains duplicate bar {day}")
            seen.add(day)
            close = _positive(row.get("close"), f"{symbol}.{day}.close")
            item = EnterpriseBar(
                date=day,
                open=_positive(row.get("open"), f"{symbol}.{day}.open"),
                high=_positive(row.get("high"), f"{symbol}.{day}.high"),
                low=_positive(row.get("low"), f"{symbol}.{day}.low"),
                close=close,
                adjusted_close=_positive(row.get("adjusted_close", close), f"{symbol}.{day}.adjusted_close"),
                volume=_nonnegative_int(row.get("volume"), f"{symbol}.{day}.volume"),
            )
            if item.high < max(item.open, item.close) or item.low > min(item.open, item.close):
                raise MarketDataUnavailable(f"{symbol} history contains invalid OHLC for {day}")
            bars.append(item)
        if any(a.date >= b.date for a, b in zip(bars, bars[1:])):
            raise MarketDataUnavailable(f"{symbol} history is not strictly chronological")
        latest = str(payload.get("latest_bar_date", "")).strip()
        if not latest or latest != bars[-1].date:
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
        fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(("Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"))
                for bar in history.bars:
                    writer.writerow((bar.date, bar.open, bar.high, bar.low, bar.close, bar.adjusted_close, bar.volume))
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)
        return destination

    def _validate_contract(self) -> None:
        version = str(self._contract.get("contract_version") or self._contract.get("schema_version") or self._contract.get("version") or "")
        if version != CONTRACT_VERSION:
            raise MarketDataUnavailable(f"Enterprise market-data contract version {version or 'MISSING'} is unsupported")

    def _find_strategy_record(self) -> Mapping[str, Any]:
        root = self._status
        if str(root.get("strategy_id", "")) == self.strategy_id:
            return root
        for key in ("strategies", "strategy_statuses", "strategy_results"):
            value = root.get(key)
            if isinstance(value, Mapping) and isinstance(value.get(self.strategy_id), Mapping):
                return value[self.strategy_id]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping) and str(item.get("strategy_id", "")) == self.strategy_id:
                        return item
        raise MarketDataUnavailable(f"{self.strategy_id} record missing from Enterprise market-data status")

    def _symbol_record(self, symbol: str) -> Mapping[str, Any]:
        target = symbol.upper()
        for key in ("symbols", "symbol_results", "records", "market_data"):
            value = self._strategy.get(key)
            if isinstance(value, Mapping) and isinstance(value.get(target), Mapping):
                return value[target]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping) and str(item.get("symbol", "")).upper() == target:
                        return item
        raise MarketDataUnavailable(f"{target} record missing for {self.strategy_id}")

    @staticmethod
    def _extract_payload(record: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
        value = record.get(kind)
        if isinstance(value, Mapping): return value
        plural = record.get(kind + "s")
        if isinstance(plural, Mapping): return plural
        if kind == "quote" and "price" in record: return record
        if kind == "history" and "bars" in record: return record
        return None

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        if not path.exists(): raise MarketDataUnavailable(f"Enterprise market-data evidence missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict): raise MarketDataUnavailable(f"Expected JSON object: {path}")
        return payload

    @staticmethod
    def _missing(symbol: str, detail: str, required: bool):
        if required: raise MarketDataUnavailable(f"{symbol.upper()} required {detail} unavailable")
        return None


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
