from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "deploy/systemd/swing-operational.service"
TIMER = ROOT / "deploy/systemd/swing-operational.timer"


def test_service_runs_only_swing_operational_launcher() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    assert "User=tradebot" in text
    assert "WorkingDirectory=/home/tradebot/Trade-Swing-Bot/main" in text
    assert "run_swing_operational_cycle.py" in text
    assert "ReadWritePaths=/home/tradebot/Trade-Swing-Bot/main" in text
    assert "ReadOnlyPaths=/home/tradebot/Trade-Dividend-Bot" in text
    assert "robinhood" not in text.lower()
    assert "live" not in "\n".join(
        line for line in text.lower().splitlines() if line.startswith("execstart=")
    )


def test_service_has_scheduler_safety_controls() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    assert "NoNewPrivileges=true" in text
    assert "PrivateTmp=true" in text
    assert "ProtectSystem=full" in text
    assert "TimeoutStartSec=30min" in text
    assert "UMask=0077" in text


def test_timer_is_weekday_post_close_and_persistent() -> None:
    text = TIMER.read_text(encoding="utf-8")
    assert "OnCalendar=Mon..Fri *-*-* 18:30:00 America/New_York" in text
    assert "Persistent=true" in text
    assert "Unit=swing-operational.service" in text
    assert "WantedBy=timers.target" in text


def test_systemd_units_do_not_reference_dividend_execution() -> None:
    service = SERVICE.read_text(encoding="utf-8").lower()
    timer = TIMER.read_text(encoding="utf-8").lower()
    assert "dividend-bot.service" not in service + timer
    assert "dividend-allocation.service" not in service + timer
    assert "trade-dividend-bot" in service  # read-only evidence boundary only
