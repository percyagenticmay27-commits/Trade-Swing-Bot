from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from swing_trade_bot.data_download import _read_url, build_historical_data


def _csv(day: date, rows: int = 1) -> str:
    lines = ["date,open,high,low,close,volume"]
    for offset in range(rows):
        current = day - timedelta(days=rows - offset - 1)
        lines.append(f"{current.isoformat()},100,102,99,101,1000")
    return "\n".join(lines) + "\n"


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self):
        return self.text.encode("utf-8")


def _validation_patches():
    return (
        patch("swing_trade_bot.data_download.validate_data_directory", return_value=[]),
        patch("swing_trade_bot.data_download.format_validation_summary", return_value="OK"),
    )


def test_fresh_cache_prevents_unnecessary_provider_calls(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "SPY.csv").write_text(_csv(date.today(), rows=60), encoding="utf-8")
    validation, formatter = _validation_patches()
    with validation, formatter, patch("swing_trade_bot.data_download.urlopen") as opened:
        run = build_historical_data(data_dir, symbols=("SPY",))
    opened.assert_not_called()
    summary = run.summaries[0]
    assert summary.source == "cache_fresh"
    assert summary.data_source == "CACHE_FRESH"
    assert summary.is_stale is False
    assert summary.error is None


def test_provider_failure_uses_stale_cache_but_keeps_warning_and_failure(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "SPY.csv").write_text(_csv(date.today() - timedelta(days=30), rows=60), encoding="utf-8")
    validation, formatter = _validation_patches()
    with validation, formatter, patch("swing_trade_bot.data_download.urlopen", side_effect=URLError("down")):
        run = build_historical_data(data_dir, symbols=("SPY",))
    summary = run.summaries[0]
    assert summary.source == "cache_stale"
    assert summary.data_source == "CACHE_STALE_FALLBACK"
    assert summary.is_stale is True
    assert "yahoo:" in summary.error
    assert "yahoo_chart:" in summary.error
    assert "stooq:" in summary.error


def test_no_cache_and_all_provider_failures_reports_unavailable(tmp_path: Path):
    validation, formatter = _validation_patches()
    with validation, formatter, patch("swing_trade_bot.data_download.urlopen", side_effect=URLError("down")):
        run = build_historical_data(tmp_path / "data", symbols=("SPY",))
    summary = run.summaries[0]
    assert summary.source is None
    assert summary.data_source == "UNAVAILABLE"
    assert summary.is_stale is False
    assert summary.rows == 0
    assert summary.error


def test_http_429_uses_bounded_backoff_then_succeeds():
    throttled = HTTPError("https://example.test", 429, "Too Many Requests", hdrs=None, fp=None)
    with patch(
        "swing_trade_bot.data_download.urlopen",
        side_effect=[throttled, throttled, FakeResponse("ok")],
    ) as opened, patch("swing_trade_bot.data_download.time.sleep") as sleeper:
        assert _read_url("https://example.test") == "ok"
    assert opened.call_count == 3
    assert sleeper.call_count == 2
