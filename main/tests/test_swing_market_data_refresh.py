from datetime import date
from pathlib import Path
from unittest.mock import patch

from swing_trade_bot.data_download import DownloadRun, DownloadSummary
from swing_trade_bot.swing_market_data_refresh import (
    build_market_data_refresh_status,
    refresh_swing_market_data,
)


def _run(*, ok: bool = True, error: str | None = None) -> DownloadRun:
    return DownloadRun(
        summaries=(
            DownloadSummary(
                symbol="SPY",
                rows=300,
                start_date=date(2025, 1, 1),
                end_date=date(2026, 8, 11),
                updated=True,
                source="yahoo_chart",
                error=error,
            ),
        ),
        validation_summary="OK" if ok else "BLOCKED",
        validation_ok=ok,
    )


def test_status_is_swing_owned_and_paper_safe():
    payload = build_market_data_refresh_status(_run(), generated_at_utc="2026-08-12T17:00:00Z")
    assert payload["strategy_id"] == "SWING-001"
    assert payload["data_owner"] == "SWING-001"
    assert payload["status"] == "AVAILABLE"
    assert payload["market_data_dependent_publication_allowed"] is True
    assert payload["paper_trade_mode"] is True
    assert payload["advisory_only"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["direct_ai_cio_database_writes"] is False


def test_failed_required_symbol_blocks_publication():
    payload = build_market_data_refresh_status(_run(error="provider unavailable"))
    assert payload["status"] == "BLOCKED"
    assert payload["market_data_dependent_publication_allowed"] is False
    assert payload["failed_symbols"] == ["SPY"]


def test_refresh_writes_only_inside_swing_repository(tmp_path: Path):
    run = _run()
    with patch(
        "swing_trade_bot.swing_market_data_refresh.build_historical_data",
        return_value=run,
    ) as build:
        assert refresh_swing_market_data(tmp_path) == 0

    build.assert_called_once_with(tmp_path / "data", years=5, refresh=False)
    status_path = tmp_path / "results" / "market_data_refresh_status.json"
    assert status_path.is_file()
    assert not (tmp_path / "results" / "market_data_refresh_status.json.tmp").exists()


def test_module_has_no_dividend_repository_dependency():
    source = Path("src/swing_trade_bot/swing_market_data_refresh.py").read_text(encoding="utf-8")
    assert "/home/tradebot/Trade-Dividend-Bot" not in source
    assert "sync_enterprise_market_data" not in source
