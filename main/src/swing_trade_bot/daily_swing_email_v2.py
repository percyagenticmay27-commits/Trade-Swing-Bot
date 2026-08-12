"""Daily Swing CSV email v2 with the executive summary as a required attachment."""

from __future__ import annotations

from pathlib import Path

from . import daily_swing_email as base
from .swing_executive_summary import write_swing_executive_summary

EXECUTIVE_SUMMARY_PATH = Path("results/swing_executive_summary.csv")
REQUIRED_ATTACHMENTS = (
    EXECUTIVE_SUMMARY_PATH,
    Path("results/daily_swing_summary.csv"),
    Path("results/paper_ledger/paper_performance.csv"),
)
OPTIONAL_ATTACHMENTS = base.OPTIONAL_ATTACHMENTS


def send_daily_swing_email(
    env_path: Path = base.DEFAULT_ENV_PATH,
    delivery_log: Path = base.DEFAULT_DELIVERY_LOG,
    status_path: Path = base.DEFAULT_STATUS_PATH,
    summary_path: Path = base.DEFAULT_SUMMARY_PATH,
    executive_summary_path: Path = EXECUTIVE_SUMMARY_PATH,
    transport=base.send_via_sendgrid,
    force: bool = False,
) -> base.DailySwingEmailStatus:
    """Generate both summaries and send all required CSV evidence through SendGrid."""
    write_swing_executive_summary(output_path=executive_summary_path)

    original_collect = base.collect_attachments

    def collect_with_executive_summary():
        required = (
            executive_summary_path,
            summary_path,
            Path("results/paper_ledger/paper_performance.csv"),
        )
        return original_collect(required=required, optional=OPTIONAL_ATTACHMENTS)

    original = base.collect_attachments
    base.collect_attachments = collect_with_executive_summary
    try:
        return base.send_daily_swing_email(
            env_path=env_path,
            delivery_log=delivery_log,
            status_path=status_path,
            summary_path=summary_path,
            transport=transport,
            force=force,
        )
    finally:
        base.collect_attachments = original
