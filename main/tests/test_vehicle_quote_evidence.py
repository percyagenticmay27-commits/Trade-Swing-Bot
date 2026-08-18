from __future__ import annotations

from pathlib import Path

from swing_trade_bot.vehicle_quote_evidence import (
    QuoteObservation,
    resolve_quote_evidence,
    stooq_quote_observation,
    validate_bid_ask,
)


def test_sane_bid_ask_is_accepted() -> None:
    valid, spread, reason = validate_bid_ask(price=20.0, bid=19.99, ask=20.01)
    assert valid is True
    assert spread is not None and spread < 1.0
    assert reason is None


def test_extreme_spread_is_rejected() -> None:
    valid, spread, reason = validate_bid_ask(price=36.67, bid=25.0, ask=43.0)
    assert valid is False
    assert spread is not None and spread > 5.0
    assert reason == "SPREAD_EXCEEDS_SANITY_LIMIT"


def test_midpoint_far_from_market_price_is_rejected() -> None:
    valid, _, reason = validate_bid_ask(price=50.0, bid=29.9, ask=30.1)
    assert valid is False
    assert reason == "QUOTE_MIDPOINT_TOO_FAR_FROM_PRICE"


def test_invalid_yahoo_bid_ask_falls_back_to_stooq_without_losing_yahoo_price_volume() -> None:
    def yahoo(_: str):
        return QuoteObservation("YAHOO", price=36.67, bid=20.0, ask=35.0, volume=12_000_000)

    def stooq(_: str):
        return QuoteObservation("STOOQ", price=36.68, bid=36.66, ask=36.70, volume=11_500_000)

    result = resolve_quote_evidence(
        "NVDL",
        yahoo_provider=yahoo,
        stooq_provider=stooq,
        robinhood_read_only_provider=None,
        cache_provider=lambda _: None,
    )
    assert result.price == 36.67
    assert result.price_source == "YAHOO"
    assert result.volume == 12_000_000
    assert result.volume_source == "YAHOO"
    assert result.bid == 36.66
    assert result.ask == 36.70
    assert result.bid_source == "STOOQ"
    assert result.spread_source == "STOOQ"
    assert result.quote_quality == "COMPLETE"
    assert any("UNRELIABLE_BID_ASK:NVDL:YAHOO" in item for item in result.warnings)


def test_robinhood_slot_is_third_and_read_only_provider_can_rescue_quote() -> None:
    calls: list[str] = []

    def yahoo(_: str):
        calls.append("YAHOO")
        return QuoteObservation("YAHOO", price=19.43, volume=100_000)

    def stooq(_: str):
        calls.append("STOOQ")
        return QuoteObservation("STOOQ", price=19.06)

    def robinhood(_: str):
        calls.append("ROBINHOOD_READ_ONLY")
        return QuoteObservation("ROBINHOOD_READ_ONLY", price=19.43, bid=19.42, ask=19.44)

    result = resolve_quote_evidence(
        "SNXX",
        yahoo_provider=yahoo,
        stooq_provider=stooq,
        robinhood_read_only_provider=robinhood,
        cache_provider=lambda _: None,
    )
    assert calls == ["YAHOO", "STOOQ", "ROBINHOOD_READ_ONLY"]
    assert result.bid_source == "ROBINHOOD_READ_ONLY"
    assert result.quote_quality == "COMPLETE"


def test_local_csv_is_last_and_marked_stale() -> None:
    result = resolve_quote_evidence(
        "TEST",
        yahoo_provider=lambda _: None,
        stooq_provider=lambda _: None,
        robinhood_read_only_provider=None,
        cache_provider=lambda _: QuoteObservation(
            "LOCAL_CSV_STALE_FALLBACK", price=10.0, volume=1000, stale=True
        ),
    )
    assert result.price == 10.0
    assert result.price_source == "LOCAL_CSV_STALE_FALLBACK"
    assert result.quote_quality == "INCOMPLETE_STALE_FALLBACK"
    assert result.spread_pct is None


def test_stooq_parser_reads_visible_bid_ask_and_quote_csv() -> None:
    def reader(url: str) -> str:
        if "/q/l/" in url:
            return "Symbol,Date,Time,Open,High,Low,Close,Volume\nSNXX.US,2026-08-17,22:00,17.36,19.88,17.36,19.06,109000000\n"
        return "<html><body><table><tr><td>Bid</td><td>19.3900</td></tr><tr><td>Ask</td><td>19.4000</td></tr></table></body></html>"

    row = stooq_quote_observation("SNXX", reader=reader)
    assert row is not None
    assert row.source == "STOOQ"
    assert row.price == 19.06
    assert row.volume == 109000000
    assert row.bid == 19.39
    assert row.ask == 19.40


def test_no_broker_or_order_execution_is_introduced() -> None:
    import swing_trade_bot.vehicle_quote_evidence as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("place_order", "submit_order", "execute_trade", "broker_adapter")
    assert all(term not in source for term in forbidden)
