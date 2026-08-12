"""Build and send the paper-only daily Swing CSV report through SendGrid.

This module is intentionally isolated from Trade-Dividend-Bot production code.
It reads a shared protected environment file and uses SendGrid's HTTPS API.
"""

from __future__ import annotations

import csv
import json
import mimetypes
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False

SENDGRID_ENDPOINT = "https://api.sendgrid.com/v3/mail/send"
DEFAULT_ENV_PATH = Path("/home/tradebot/.config/tradebot/email.env")
DEFAULT_RESULTS_DIR = Path("results")
DEFAULT_DELIVERY_LOG = Path("results/swing_email_delivery_log.csv")
DEFAULT_STATUS_PATH = Path("results/swing_email_delivery_status.json")
DEFAULT_SUMMARY_PATH = Path("results/daily_swing_summary.csv")

REQUIRED_ATTACHMENTS = (
    Path("results/daily_swing_summary.csv"),
    Path("results/paper_ledger/paper_performance.csv"),
)
OPTIONAL_ATTACHMENTS = (
    Path("results/opportunity_quality_report.csv"),
    Path("results/watchlist_report.csv"),
    Path("results/paper_ledger/paper_portfolio_positions.csv"),
    Path("results/paper_ledger/managed_trade_history.csv"),
)

DELIVERY_COLUMNS = (
    "sent_at",
    "report_date",
    "sender",
    "recipient",
    "subject",
    "attachments",
    "status",
    "provider_status_code",
)


@dataclass(frozen=True)
class EmailSettings:
    api_key: str
    from_email: str
    from_name: str
    reply_to: str
    recipient: str


@dataclass
class DailySwingEmailStatus:
    generated_at: str
    report_date: str
    status: str
    sender: str
    recipient: str
    attachments: list[str] = field(default_factory=list)
    missing_optional_attachments: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    provider: str = "SENDGRID"
    provider_status_code: int | None = None
    paper_trade_mode: bool = PAPER_TRADE_MODE
    live_trading_enabled: bool = LIVE_TRADING_ENABLED
    broker_execution_enabled: bool = BROKER_EXECUTION_ENABLED
    order_placement_enabled: bool = ORDER_PLACEMENT_ENABLED
    capital_movement_enabled: bool = CAPITAL_MOVEMENT_ENABLED
    direct_database_writes: bool = DIRECT_DATABASE_WRITES


def load_env_file(path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Shared email environment file not found: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_email_settings(
    env_path: Path = DEFAULT_ENV_PATH,
    environ: Mapping[str, str] | None = None,
) -> EmailSettings:
    merged = load_env_file(env_path)
    merged.update(dict(os.environ if environ is None else environ))
    required = (
        "SENDGRID_API_KEY",
        "SENDGRID_FROM_EMAIL",
        "SENDGRID_FROM_NAME",
        "SENDGRID_REPLY_TO",
        "REPORT_RECIPIENT",
    )
    missing = [name for name in required if not merged.get(name)]
    if missing:
        raise ValueError("Missing shared email settings: " + ", ".join(missing))
    api_key = merged["SENDGRID_API_KEY"]
    if not api_key.startswith("SG."):
        raise ValueError("SENDGRID_API_KEY must include the SendGrid SG. prefix")
    return EmailSettings(
        api_key=api_key,
        from_email=merged["SENDGRID_FROM_EMAIL"],
        from_name=merged["SENDGRID_FROM_NAME"],
        reply_to=merged["SENDGRID_REPLY_TO"],
        recipient=merged["REPORT_RECIPIENT"],
    )


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_daily_swing_summary(
    output_path: Path = DEFAULT_SUMMARY_PATH,
    kpi_path: Path = Path("results/enterprise_strategy_kpis.json"),
) -> Path:
    data = _read_json(kpi_path)
    if not data:
        raise FileNotFoundError(f"Enterprise Swing KPI evidence not found: {kpi_path}")
    row = {
        "report_date": date.today().isoformat(),
        "strategy_id": data.get("strategy_id", "SWING-001"),
        "allocated_capital": data.get("allocated_capital"),
        "portfolio_value": data.get("portfolio_value"),
        "cash_balance": data.get("cash_balance"),
        "invested_capital": data.get("invested_capital"),
        "positions_market_value": data.get("positions_market_value"),
        "position_count": data.get("position_count"),
        "trade_count": data.get("trade_count"),
        "closed_trade_count": data.get("closed_trade_count"),
        "realized_pnl": data.get("realized_pnl"),
        "unrealized_pnl": data.get("unrealized_pnl"),
        "total_pnl": data.get("total_pnl"),
        "portfolio_return_percent": data.get("portfolio_return_percent"),
        "win_rate_percent": data.get("win_rate_percent"),
        "opportunity_quality": data.get("opportunity_quality"),
        "evidence_status": data.get("evidence_status"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_csv_write(output_path, [row], tuple(row.keys()))
    return output_path


def collect_attachments(
    required: Sequence[Path] = REQUIRED_ATTACHMENTS,
    optional: Sequence[Path] = OPTIONAL_ATTACHMENTS,
) -> tuple[list[Path], list[Path]]:
    missing_required = [path for path in required if not path.exists()]
    if missing_required:
        raise FileNotFoundError(
            "Required Swing email CSV files are missing: "
            + ", ".join(str(path) for path in missing_required)
        )
    invalid = [path for path in (*required, *optional) if path.exists() and path.suffix.lower() != ".csv"]
    if invalid:
        raise ValueError("Swing daily email attachments must be CSV files only")
    existing = [path for path in (*required, *optional) if path.exists()]
    missing_optional = [path for path in optional if not path.exists()]
    return existing, missing_optional


def already_sent(log_path: Path, report_date: str, recipient: str) -> bool:
    if not log_path.exists():
        return False
    with log_path.open(newline="", encoding="utf-8") as handle:
        return any(
            row.get("report_date") == report_date
            and row.get("recipient") == recipient
            and row.get("status") == "SENT"
            for row in csv.DictReader(handle)
        )


def build_sendgrid_payload(
    settings: EmailSettings,
    report_date: str,
    attachments: Sequence[Path],
    missing_optional: Sequence[Path],
) -> dict:
    import base64

    subject = f"PAPER ONLY Swing Bot Daily CSV Report - {report_date}"
    warning_text = (
        "\nMissing optional CSV files:\n"
        + "\n".join(f"- {path}" for path in missing_optional)
        if missing_optional
        else ""
    )
    body = (
        "PAPER ONLY - NO REAL ORDERS OR BROKER EXECUTION\n\n"
        f"Attached are the Trade Swing Bot CSV reports for {report_date}.\n"
        + warning_text
    )
    encoded = []
    for path in attachments:
        mime_type, _ = mimetypes.guess_type(path.name)
        encoded.append(
            {
                "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                "type": mime_type or "text/csv",
                "filename": path.name,
                "disposition": "attachment",
            }
        )
    return {
        "personalizations": [{"to": [{"email": settings.recipient}]}],
        "from": {"email": settings.from_email, "name": settings.from_name},
        "reply_to": {"email": settings.reply_to},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
        "attachments": encoded,
    }


def send_via_sendgrid(payload: dict, api_key: str, timeout: int = 30) -> int:
    request = urllib.request.Request(
        SENDGRID_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SendGrid HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"SendGrid network failure: {exc.reason}") from exc


def append_delivery_log(
    path: Path,
    status: DailySwingEmailStatus,
    subject: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DELIVERY_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "sent_at": status.generated_at,
                "report_date": status.report_date,
                "sender": status.sender,
                "recipient": status.recipient,
                "subject": subject,
                "attachments": ";".join(status.attachments),
                "status": status.status,
                "provider_status_code": status.provider_status_code or "",
            }
        )


def write_status(path: Path, status: DailySwingEmailStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text_write(path, json.dumps(asdict(status), indent=2, sort_keys=True) + "\n")


def send_daily_swing_email(
    env_path: Path = DEFAULT_ENV_PATH,
    delivery_log: Path = DEFAULT_DELIVERY_LOG,
    status_path: Path = DEFAULT_STATUS_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    transport=send_via_sendgrid,
    force: bool = False,
) -> DailySwingEmailStatus:
    generated_at = datetime.now(timezone.utc).isoformat()
    report_date = date.today().isoformat()
    settings = load_email_settings(env_path)
    status = DailySwingEmailStatus(
        generated_at=generated_at,
        report_date=report_date,
        status="PENDING",
        sender=settings.from_email,
        recipient=settings.recipient,
    )
    try:
        write_daily_swing_summary(summary_path)
        attachments, missing_optional = collect_attachments()
        status.attachments = [str(path) for path in attachments]
        status.missing_optional_attachments = [str(path) for path in missing_optional]
        status.warnings.extend(
            f"Optional Swing email CSV unavailable: {path}" for path in missing_optional
        )
        if already_sent(delivery_log, report_date, settings.recipient) and not force:
            status.status = "SKIPPED_ALREADY_SENT"
            write_status(status_path, status)
            return status
        payload = build_sendgrid_payload(settings, report_date, attachments, missing_optional)
        provider_status = transport(payload, settings.api_key)
        if provider_status not in (200, 202):
            raise RuntimeError(f"Unexpected SendGrid status: {provider_status}")
        status.status = "SENT"
        status.provider_status_code = provider_status
        append_delivery_log(delivery_log, status, str(payload["subject"]))
    except Exception as exc:  # status artifact must survive operational failures
        status.status = "FAILED"
        status.errors.append(str(exc))
        write_status(status_path, status)
        raise
    write_status(status_path, status)
    return status


def _atomic_text_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _atomic_csv_write(path: Path, rows: Iterable[dict], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
