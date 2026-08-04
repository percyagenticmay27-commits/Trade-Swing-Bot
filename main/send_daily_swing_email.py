"""Command-line entry point for the paper-only Swing CSV email."""

from __future__ import annotations

import argparse
from pathlib import Path

from swing_trade_bot.daily_swing_email_v2 import send_daily_swing_email


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send the paper-only Swing daily CSV report")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path("/home/tradebot/.config/tradebot/email.env"),
        help="Shared protected SendGrid environment file",
    )
    parser.add_argument("--force", action="store_true", help="Allow a repeated send for the same date")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    status = send_daily_swing_email(env_path=args.env_file, force=args.force)
    print(f"Daily Swing email: {status.status}")
    print(f"Report date: {status.report_date}")
    print(f"Recipient: {status.recipient}")
    print("Attachments: " + ", ".join(status.attachments))
    if status.warnings:
        print("Warnings:")
        for warning in status.warnings:
            print(f"- {warning}")
    return 0 if status.status in {"SENT", "SKIPPED_ALREADY_SENT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
