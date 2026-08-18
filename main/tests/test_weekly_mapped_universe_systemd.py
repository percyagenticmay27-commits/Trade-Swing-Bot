from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "deploy/systemd/swing-weekly-mapped-universe-review.service"
TIMER = REPO_ROOT / "deploy/systemd/swing-weekly-mapped-universe-review.timer"


def test_service_runs_weekly_mapped_universe_review_only() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    assert "WorkingDirectory=/home/tradebot/Trade-Swing-Bot/main" in text
    assert "-m swing_trade_bot.weekly_mapped_universe_review" in text
    lowered = text.lower()
    assert "robinhood" not in lowered
    assert "order" not in lowered
    assert "broker" not in lowered


def test_timer_runs_tuesday_after_us_market_close() -> None:
    text = TIMER.read_text(encoding="utf-8")
    assert "OnCalendar=Tue *-*-* 16:30:00 America/New_York" in text
    assert "Persistent=true" in text
    assert "Unit=swing-weekly-mapped-universe-review.service" in text


def test_weekend_vehicle_timer_remains_separate() -> None:
    weekend_timer = REPO_ROOT / "deploy/systemd/swing-weekend-vehicle-maintenance.timer"
    text = weekend_timer.read_text(encoding="utf-8")
    assert "OnCalendar=Sun *-*-* 09:00:00" in text
    assert "swing-weekend-vehicle-maintenance.service" in text
