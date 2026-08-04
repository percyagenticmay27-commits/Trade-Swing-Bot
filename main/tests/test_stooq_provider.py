from datetime import datetime, timezone

import pytest

from swing_trade_bot.providers.stooq_provider import StooqProvider, StooqProviderError


def _csv(rows: int = 60) -> bytes:
    lines = ["Date,Open,High,Low,Close,Volume"]
    for index in range(rows):
        day = index + 1
        month = 1 + (day - 1) // 28
        dom = 1 + (day - 1) % 28
        close = 100 + index
        lines.append(f"2026-{month:02d}-{dom:02d},{close-1},{close+1},{close-2},{close},1000")
    return ("\n".join(lines) + "\n").encode()


def test_stooq_normalizes_daily_bars_and_discloses_close_fallback():
    urls = []

    def downloader(url: str, timeout: int) -> bytes:
        urls.append(url)
        return _csv()

    provider = StooqProvider(downloader=downloader)
    bars = provider.fetch_daily_bars(
        "SOXL", target_completed_bars=51, as_of_utc=datetime(2026, 3, 31, tzinfo=timezone.utc)
    )
    assert len(bars) == 51
    assert bars[-1].adjusted_close == bars[-1].close
    assert provider.adjusted_close_source == "UNAVAILABLE_USE_CLOSE"
    assert provider.corporate_action_adjusted is False
    assert "soxl.us" in urls[0]


def test_stooq_rejects_short_history():
    provider = StooqProvider(downloader=lambda _url, _timeout: _csv(10))
    with pytest.raises(StooqProviderError) as exc:
        provider.fetch_daily_bars(
            "SOXL", target_completed_bars=250, as_of_utc=datetime(2026, 3, 31, tzinfo=timezone.utc)
        )
    assert exc.value.classification == "INSUFFICIENT_HISTORY"


def test_stooq_requires_mapping_for_index_symbols():
    provider = StooqProvider(downloader=lambda _url, _timeout: _csv())
    with pytest.raises(StooqProviderError) as exc:
        provider.fetch_daily_bars(
            "^VIX", target_completed_bars=51, as_of_utc=datetime(2026, 3, 31, tzinfo=timezone.utc)
        )
    assert exc.value.classification == "SYMBOL_MAPPING_REQUIRED"
