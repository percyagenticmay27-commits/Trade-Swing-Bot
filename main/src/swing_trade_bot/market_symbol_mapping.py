"""Authoritative symbol-purpose mapping for Swing market evidence.

Trade/valuation symbols remain the actual paper-traded security.  Signal and
earnings symbols may point at a verified underlying when a leveraged single-
stock ETF does not have enough native history for technical/earnings evidence.
No mapping is inferred from ticker spelling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class MarketSymbolMapping:
    trade_symbol: str
    valuation_symbol: str
    signal_symbol: str | None
    earnings_symbol: str | None
    inception_date: date | None = None


# Verified issuer relationships only.  Basket/index products remain self-mapped
# unless an explicit strategy-specific signal proxy is approved later.
_MAPPINGS: dict[str, MarketSymbolMapping] = {
    "BEX": MarketSymbolMapping(
        trade_symbol="BEX",
        valuation_symbol="BEX",
        signal_symbol="BE",
        earnings_symbol="BE",
        inception_date=date(2025, 11, 12),
    ),
    "IRE": MarketSymbolMapping(
        trade_symbol="IRE",
        valuation_symbol="IRE",
        signal_symbol="IREN",
        earnings_symbol="IREN",
        inception_date=date(2025, 10, 20),
    ),
    "IONL": MarketSymbolMapping(
        trade_symbol="IONL",
        valuation_symbol="IONL",
        signal_symbol="IONQ",
        earnings_symbol="IONQ",
        inception_date=date(2025, 3, 25),
    ),
    "DRAM": MarketSymbolMapping(
        trade_symbol="DRAM",
        valuation_symbol="DRAM",
        signal_symbol=None,
        earnings_symbol=None,
        inception_date=date(2026, 4, 2),
    ),
}


def get_market_symbol_mapping(symbol: str) -> MarketSymbolMapping:
    """Return explicit mapping or a conservative self-map for ordinary symbols."""
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return _MAPPINGS.get(
        normalized,
        MarketSymbolMapping(
            trade_symbol=normalized,
            valuation_symbol=normalized,
            signal_symbol=normalized,
            earnings_symbol=normalized,
        ),
    )


def resolve_symbol(symbol: str, purpose: str) -> str:
    """Resolve a symbol for VALUATION, TECHNICAL_SIGNAL, or EARNINGS purpose.

    Explicitly unmapped technical/earnings purposes fail closed instead of
    guessing a similarly named ticker or exchange suffix.
    """
    mapping = get_market_symbol_mapping(symbol)
    purpose_key = purpose.strip().upper()
    if purpose_key in {"TRADE", "TRADE_SYMBOL"}:
        return mapping.trade_symbol
    if purpose_key in {"VALUATION", "QUOTE", "POSITION_VALUATION"}:
        return mapping.valuation_symbol
    if purpose_key in {"TECHNICAL_SIGNAL", "SIGNAL", "HISTORY"}:
        if mapping.signal_symbol is None:
            raise ValueError(f"SIGNAL_SYMBOL_NOT_CONFIGURED:{mapping.trade_symbol}")
        return mapping.signal_symbol
    if purpose_key in {"EARNINGS", "EARNINGS_RISK"}:
        if mapping.earnings_symbol is None:
            raise ValueError(f"EARNINGS_SYMBOL_NOT_CONFIGURED:{mapping.trade_symbol}")
        return mapping.earnings_symbol
    raise ValueError(f"unsupported market-data purpose: {purpose}")


def known_inception_date(symbol: str) -> date | None:
    """Return verified fund inception date when configured."""
    return get_market_symbol_mapping(symbol).inception_date
