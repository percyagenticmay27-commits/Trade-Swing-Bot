import csv
import json
from pathlib import Path

from swing_trade_bot.daily_swing_email_v2 import send_daily_swing_email


def test_email_v2_requires_and_attaches_executive_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results/paper_ledger").mkdir(parents=True)
    (tmp_path / "results/paper_ledger/paper_performance.csv").write_text("metric,value\nreturn,0\n", encoding="utf-8")
    (tmp_path / "results/enterprise_strategy_kpis.json").write_text(
        json.dumps(
            {
                "strategy_id": "SWING-001",
                "allocated_capital": 4500.0,
                "portfolio_value": 4500.0,
                "cash_balance": 2700.0,
                "invested_capital": 1800.0,
                "position_count": 1,
                "open_positions": [{"symbol": "SOXL", "shares": 2, "entry_price": 100, "current_price": 105}],
                "evidence_status": "AVAILABLE",
            }
        ),
        encoding="utf-8",
    )
    env = tmp_path / "email.env"
    env.write_text(
        "SENDGRID_API_KEY=SG.example\n"
        "SENDGRID_FROM_EMAIL=bot@example.com\n"
        "SENDGRID_FROM_NAME=Trade Swing Bot\n"
        "SENDGRID_REPLY_TO=reply@example.com\n"
        "REPORT_RECIPIENT=owner@example.com\n",
        encoding="utf-8",
    )
    captured = {}

    def transport(payload, api_key):
        captured["payload"] = payload
        return 202

    status = send_daily_swing_email(
        env_path=env,
        delivery_log=tmp_path / "results/delivery.csv",
        status_path=tmp_path / "results/status.json",
        summary_path=tmp_path / "results/daily_swing_summary.csv",
        executive_summary_path=tmp_path / "results/swing_executive_summary.csv",
        transport=transport,
    )

    assert status.status == "SENT"
    filenames = [item["filename"] for item in captured["payload"]["attachments"]]
    assert "swing_executive_summary.csv" in filenames
    assert "daily_swing_summary.csv" in filenames
    assert "paper_performance.csv" in filenames
    with (tmp_path / "results/swing_executive_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[1]["symbol"] == "SOXL"
