from pathlib import Path

import pytest

from swing_trade_bot.daily_swing_email import (
    EmailSettings,
    build_sendgrid_payload,
    collect_attachments,
    load_email_settings,
)


def test_load_email_settings(tmp_path: Path) -> None:
    env = tmp_path / "email.env"
    env.write_text(
        "SENDGRID_API_KEY=SG.example\n"
        "SENDGRID_FROM_EMAIL=bot@example.com\n"
        "SENDGRID_FROM_NAME=Trade Swing Bot\n"
        "SENDGRID_REPLY_TO=reply@example.com\n"
        "REPORT_RECIPIENT=owner@example.com\n",
        encoding="utf-8",
    )
    settings = load_email_settings(env, environ={})
    assert settings.api_key.startswith("SG.")
    assert settings.recipient == "owner@example.com"


def test_rejects_missing_sg_prefix(tmp_path: Path) -> None:
    env = tmp_path / "email.env"
    env.write_text(
        "SENDGRID_API_KEY=example\n"
        "SENDGRID_FROM_EMAIL=bot@example.com\n"
        "SENDGRID_FROM_NAME=Trade Swing Bot\n"
        "SENDGRID_REPLY_TO=reply@example.com\n"
        "REPORT_RECIPIENT=owner@example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SG. prefix"):
        load_email_settings(env, environ={})


def test_collects_csv_and_warns_for_optional(tmp_path: Path) -> None:
    required = tmp_path / "required.csv"
    optional = tmp_path / "optional.csv"
    required.write_text("a\n1\n", encoding="utf-8")
    files, missing = collect_attachments((required,), (optional,))
    assert files == [required]
    assert missing == [optional]


def test_sendgrid_payload_contains_attachment(tmp_path: Path) -> None:
    report = tmp_path / "report.csv"
    report.write_text("a,b\n1,2\n", encoding="utf-8")
    settings = EmailSettings(
        api_key="SG.example",
        from_email="bot@example.com",
        from_name="Trade Swing Bot",
        reply_to="reply@example.com",
        recipient="owner@example.com",
    )
    payload = build_sendgrid_payload(settings, "2026-08-04", [report], [])
    assert payload["subject"].startswith("PAPER ONLY")
    assert payload["attachments"][0]["filename"] == "report.csv"


def test_safety_flags_locked() -> None:
    from swing_trade_bot import daily_swing_email as module

    assert module.PAPER_TRADE_MODE is True
    assert module.LIVE_TRADING_ENABLED is False
    assert module.BROKER_EXECUTION_ENABLED is False
    assert module.ORDER_PLACEMENT_ENABLED is False
    assert module.CAPITAL_MOVEMENT_ENABLED is False
    assert module.DIRECT_DATABASE_WRITES is False


def test_no_dividend_production_imports() -> None:
    source = Path("src/swing_trade_bot/daily_swing_email.py").read_text(encoding="utf-8").lower()
    assert "shared.notifications" not in source
    assert "trade_dividend_bot" not in source
