from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "deploy/systemd/swing-operational-health.service"
TIMER = ROOT / "deploy/systemd/swing-operational-health.timer"
LAUNCHER = ROOT / "run_swing_operational_health.py"


def test_health_launcher_is_read_only_assessment_entrypoint() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "write_operational_health" in text
    assert "run_swing_bot_cycle" not in text
    assert "order" not in text.lower()
    assert "broker" not in text.lower()


def test_health_service_runs_as_tradebot_and_only_writes_results() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    assert "User=tradebot" in text
    assert "Group=tradebot" in text
    assert "run_swing_operational_health.py" in text
    assert "ReadWritePaths=/home/tradebot/Trade-Swing-Bot/main/results" in text
    assert "ProtectHome=read-only" in text
    assert "NoNewPrivileges=true" in text
    assert "Trade-Dividend-Bot" not in text


def test_health_timer_runs_after_cycle_and_next_morning() -> None:
    text = TIMER.read_text(encoding="utf-8")
    assert "Mon..Fri *-*-* 20:15:00 America/New_York" in text
    assert "Tue..Sat *-*-* 08:00:00 America/New_York" in text
    assert "Persistent=true" in text
    assert "Unit=swing-operational-health.service" in text


def test_health_units_do_not_execute_trading_cycle() -> None:
    combined = SERVICE.read_text(encoding="utf-8") + TIMER.read_text(encoding="utf-8")
    assert "run_swing_operational_cycle.py" not in combined
    assert "run_swing_bot_cycle.py" not in combined
    assert "publish_enterprise_strategy_kpis" not in combined
