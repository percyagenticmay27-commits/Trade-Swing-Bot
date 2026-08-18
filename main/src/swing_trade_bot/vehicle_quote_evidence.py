"""Field-level, read-only quote fallback for weekend leveraged-vehicle review.

Provider order is Yahoo -> Stooq -> optional Robinhood read-only provider -> local
CSV cache. Quotes are sanity-checked before use. A provider may contribute only
some fields; provenance is retained per field. No account, broker, order, or
position API is used here.
"""
from __future__ import annotations

import csv
import html
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; Trade-Swing-Bot/1.0; read-only-market-data)"
MAX_SPREAD_PCT = 5.0
MAX_MIDPOINT_PRICE_DEVIATION_PCT = 10.0


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    source: str
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    stale: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedQuoteEvidence:
    symbol: str
    price: float | None
    bid: float | None
    ask: float | None
    volume: float | None
    spread_pct: float | None
    price_source: str | None
    bid_source: str | None
    ask_source: str | None
    volume_source: str | None
    spread_source: str | None
    quote_quality: str
    provider_attempts: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def validate_bid_ask(
    *,
    price: float | None,
    bid: float | None,
    ask: float | None,
    max_spread_pct: float = MAX_SPREAD_PCT,
    max_midpoint_deviation_pct: float = MAX_MIDPOINT_PRICE_DEVIATION_PCT,
) -> tuple[bool, float | None, str | None]:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return False, None, "MISSING_OR_INVALID_BID_ASK"
    midpoint = (bid + ask) / 2.0
    if midpoint <= 0:
        return False, None, "INVALID_QUOTE_MIDPOINT"
    spread_pct = (ask - bid) / midpoint * 100.0
    if spread_pct > max_spread_pct:
        return False, spread_pct, "SPREAD_EXCEEDS_SANITY_LIMIT"
    if price is not None and price > 0:
        deviation_pct = abs(midpoint - price) / price * 100.0
        if deviation_pct > max_midpoint_deviation_pct:
            return False, spread_pct, "QUOTE_MIDPOINT_TOO_FAR_FROM_PRICE"
    return True, spread_pct, None


def yahoo_quote_observation(
    symbol: str,
    *,
    ticker_factory: Callable[[str], Any] | None = None,
) -> QuoteObservation | None:
    if ticker_factory is None:
        import yfinance as yf

        ticker_factory = yf.Ticker
    ticker = ticker_factory(symbol)
    try:
        info = ticker.get_info()
    except Exception:
        try:
            info = ticker.info
        except Exception:
            info = {}
    info = info if isinstance(info, Mapping) else {}
    price = _number(
        info.get("regularMarketPrice", info.get("currentPrice", info.get("navPrice")))
    )
    bid = _number(info.get("bid"))
    ask = _number(info.get("ask"))
    volume = _number(info.get("regularMarketVolume", info.get("volume")))
    if price is None:
        try:
            history = ticker.history(period="5d", auto_adjust=False)
            if not getattr(history, "empty", True):
                price = float(history["Close"].dropna().iloc[-1])
                if volume is None:
                    volume = float(history["Volume"].dropna().iloc[-1])
        except Exception:
            pass
    if all(value is None for value in (price, bid, ask, volume)):
        return None
    return QuoteObservation("YAHOO", price=price, bid=bid, ask=ask, volume=volume)


def _read_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/csv,*/*"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def _stooq_page_value(text: str, label: str) -> float | None:
    plain = re.sub(r"<[^>]+>", " ", html.unescape(text))
    plain = re.sub(r"\s+", " ", plain)
    match = re.search(rf"\b{re.escape(label)}\b\s*([0-9]+(?:[.,][0-9]+)?)", plain, re.IGNORECASE)
    if match is None:
        return None
    return _number(match.group(1).replace(",", "."))


def stooq_quote_observation(
    symbol: str,
    *,
    reader: Callable[[str], str] | None = None,
) -> QuoteObservation | None:
    reader = reader or _read_url
    ticker = f"{symbol.strip().lower()}.us"
    price = None
    volume = None
    try:
        csv_text = reader(f"https://stooq.com/q/l/?s={ticker}&f=sd2t2ohlcv&h&e=csv")
        rows = list(csv.DictReader(csv_text.splitlines()))
        if rows:
            row = rows[0]
            price = _number(row.get("Close"))
            volume = _number(row.get("Volume"))
    except Exception:
        pass
    bid = None
    ask = None
    try:
        page = reader(f"https://stooq.com/q/?s={ticker}")
        bid = _stooq_page_value(page, "Bid")
        ask = _stooq_page_value(page, "Ask")
    except Exception:
        pass
    if all(value is None for value in (price, bid, ask, volume)):
        return None
    return QuoteObservation("STOOQ", price=price, bid=bid, ask=ask, volume=volume)


def local_csv_quote_observation(symbol: str, *, data_dir: str | Path = "data") -> QuoteObservation | None:
    path = Path(data_dir) / f"{symbol.strip().upper()}.csv"
    if not path.is_file():
        return None
    try:
        rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
        if not rows:
            return None
        row = rows[-1]
        price = _number(row.get("close") or row.get("Close"))
        volume = _number(row.get("volume") or row.get("Volume"))
    except Exception:
        return None
    if price is None and volume is None:
        return None
    return QuoteObservation("LOCAL_CSV_STALE_FALLBACK", price=price, volume=volume, stale=True)


def resolve_quote_evidence(
    symbol: str,
    *,
    yahoo_provider: Callable[[str], QuoteObservation | None] | None = None,
    stooq_provider: Callable[[str], QuoteObservation | None] | None = None,
    robinhood_read_only_provider: Callable[[str], QuoteObservation | None] | None = None,
    cache_provider: Callable[[str], QuoteObservation | None] | None = None,
) -> ResolvedQuoteEvidence:
    """Resolve quote fields in strict provider order while preserving provenance."""
    yahoo_provider = yahoo_provider or yahoo_quote_observation
    stooq_provider = stooq_provider or stooq_quote_observation
    cache_provider = cache_provider or local_csv_quote_observation

    providers: list[tuple[str, Callable[[str], QuoteObservation | None] | None]] = [
        ("YAHOO", yahoo_provider),
        ("STOOQ", stooq_provider),
        ("ROBINHOOD_READ_ONLY", robinhood_read_only_provider),
        ("LOCAL_CSV_STALE_FALLBACK", cache_provider),
    ]
    price = bid = ask = volume = None
    price_source = bid_source = ask_source = volume_source = None
    warnings: list[str] = []
    attempts: list[dict[str, Any]] = []

    for provider_name, provider in providers:
        if provider is None:
            attempts.append({"provider": provider_name, "status": "NOT_CONFIGURED"})
            continue
        try:
            observation = provider(symbol)
        except Exception as exc:
            attempts.append({"provider": provider_name, "status": "ERROR", "error": str(exc)})
            warnings.append(f"QUOTE_PROVIDER_ERROR:{symbol}:{provider_name}")
            continue
        if observation is None:
            attempts.append({"provider": provider_name, "status": "NO_DATA"})
            continue
        attempts.append({"provider": provider_name, "status": "AVAILABLE", **asdict(observation)})
        if price is None and observation.price is not None and observation.price > 0:
            price, price_source = observation.price, observation.source
        if volume is None and observation.volume is not None and observation.volume >= 0:
            volume, volume_source = observation.volume, observation.source

        valid, _, reason = validate_bid_ask(
            price=price or observation.price,
            bid=observation.bid,
            ask=observation.ask,
        )
        if bid is None and ask is None and valid:
            bid, ask = observation.bid, observation.ask
            bid_source = ask_source = observation.source
        elif observation.bid is not None or observation.ask is not None:
            warnings.append(f"UNRELIABLE_BID_ASK:{symbol}:{provider_name}:{reason}")

        if price is not None and volume is not None and bid is not None and ask is not None:
            break

    valid, spread_pct, reason = validate_bid_ask(price=price, bid=bid, ask=ask)
    spread_source = bid_source if valid and bid_source == ask_source else None
    if not valid:
        spread_pct = None
        if reason:
            warnings.append(f"QUOTE_SPREAD_UNAVAILABLE:{symbol}:{reason}")

    quality = "COMPLETE"
    if price is None or volume is None or spread_pct is None:
        quality = "INCOMPLETE"
    if price_source == "LOCAL_CSV_STALE_FALLBACK" or volume_source == "LOCAL_CSV_STALE_FALLBACK":
        quality = "STALE_FALLBACK" if quality == "COMPLETE" else "INCOMPLETE_STALE_FALLBACK"

    return ResolvedQuoteEvidence(
        symbol=symbol.strip().upper(),
        price=price,
        bid=bid,
        ask=ask,
        volume=volume,
        spread_pct=spread_pct,
        price_source=price_source,
        bid_source=bid_source,
        ask_source=ask_source,
        volume_source=volume_source,
        spread_source=spread_source,
        quote_quality=quality,
        provider_attempts=tuple(attempts),
        warnings=tuple(dict.fromkeys(warnings)),
    )
