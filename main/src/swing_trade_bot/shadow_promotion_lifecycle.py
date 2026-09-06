"""Pending-veto lifecycle for qualified SWING-001 shadow promotions.

Qualification is an upstream concern. A qualified SHADOW enters PENDING_VETO with
an explicit veto deadline. Before that deadline no assignment changes occur. At or
after the deadline an active user veto blocks promotion; otherwise the qualified
shadow is promoted automatically through shadow_strategy_promotion.

This module is paper-only. It does not place orders, reserve or move capital, or
enable broker execution.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .shadow_strategy_promotion import promote_shadow_strategy
from .user_veto_control import DEFAULT_LEDGER_PATH as DEFAULT_VETO_LEDGER_PATH, symbol_is_vetoed

DEFAULT_LIFECYCLE_PATH = Path("results/shadow_promotion_lifecycle.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
AFFIRMATIVE_APPROVAL_REQUIRED = False
USER_VETO_ALLOWED = True
AUTO_PROMOTION_AFTER_VETO_DEADLINE = True

PENDING_VETO = "PENDING_VETO"
VETOED = "VETOED"
PROMOTED = "PROMOTED"


@dataclass(frozen=True, slots=True)
class PromotionLifecycleEvent:
    underlying_symbol: str
    strategy_id: str
    status: str
    qualified_at: str
    veto_deadline: str
    resolved_at: str | None = None
    previous_direct_strategy_id: str | None = None
    qualification_evidence: Mapping[str, Any] | None = None
    paper_trade_mode: bool = True


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("timestamp is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def load_promotion_lifecycle(path: str | Path = DEFAULT_LIFECYCLE_PATH) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        return {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "affirmative_approval_required": False,
            "user_veto_allowed": True,
            "events": [],
        }
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shadow promotion lifecycle root must be an object")
    if payload.get("strategy_id") != "SWING-001":
        raise ValueError("shadow promotion lifecycle strategy_id must be SWING-001")
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("shadow promotion lifecycle paper_trade_mode must be true")
    if payload.get("affirmative_approval_required") is not False:
        raise ValueError("affirmative approval must remain disabled")
    if not isinstance(payload.get("events"), list):
        raise ValueError("shadow promotion lifecycle events must be a list")
    return payload


def queue_qualified_shadow(
    *,
    underlying_symbol: str,
    strategy_id: str,
    qualified_at: str,
    veto_deadline: str,
    lifecycle_path: str | Path = DEFAULT_LIFECYCLE_PATH,
    qualification_evidence: Mapping[str, Any] | None = None,
) -> PromotionLifecycleEvent:
    """Create one PENDING_VETO event for a newly qualified shadow.

    The caller supplies the deadline so policy duration remains configurable and is
    not silently invented by this module.
    """
    symbol = underlying_symbol.strip().upper()
    target = strategy_id.strip().upper()
    if not symbol or not target:
        raise ValueError("underlying_symbol and strategy_id are required")
    qualified_time = _parse_utc(qualified_at)
    deadline_time = _parse_utc(veto_deadline)
    if deadline_time <= qualified_time:
        raise ValueError("veto_deadline must be after qualified_at")

    path = Path(lifecycle_path)
    payload = load_promotion_lifecycle(path)
    events = list(payload["events"])
    for row in events:
        if not isinstance(row, Mapping):
            continue
        if (
            str(row.get("underlying_symbol", "")).upper() == symbol
            and str(row.get("strategy_id", "")).upper() == target
            and row.get("status") == PENDING_VETO
        ):
            return PromotionLifecycleEvent(**dict(row))

    event = PromotionLifecycleEvent(
        underlying_symbol=symbol,
        strategy_id=target,
        status=PENDING_VETO,
        qualified_at=qualified_at,
        veto_deadline=veto_deadline,
        qualification_evidence=None if qualification_evidence is None else dict(qualification_evidence),
    )
    events.append(asdict(event))
    updated = dict(payload)
    updated["events"] = events
    _atomic_json(path, updated)
    return event


def process_pending_promotions(
    *,
    now: str | None = None,
    lifecycle_path: str | Path = DEFAULT_LIFECYCLE_PATH,
    veto_ledger_path: str | Path = DEFAULT_VETO_LEDGER_PATH,
    registry_path: Path,
    form_contract_path: Path,
    assignment_report_path: Path,
) -> tuple[PromotionLifecycleEvent, ...]:
    """Resolve expired pending events using veto-by-exception governance."""
    current_text = now or _utc_now()
    current = _parse_utc(current_text)
    path = Path(lifecycle_path)
    payload = load_promotion_lifecycle(path)
    rows = list(payload["events"])
    resolved: list[PromotionLifecycleEvent] = []
    changed = False

    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping) or raw.get("status") != PENDING_VETO:
            continue
        event = PromotionLifecycleEvent(**dict(raw))
        if current < _parse_utc(event.veto_deadline):
            continue

        if symbol_is_vetoed(event.underlying_symbol, ledger_path=veto_ledger_path):
            final = PromotionLifecycleEvent(
                underlying_symbol=event.underlying_symbol,
                strategy_id=event.strategy_id,
                status=VETOED,
                qualified_at=event.qualified_at,
                veto_deadline=event.veto_deadline,
                resolved_at=current_text,
                qualification_evidence=event.qualification_evidence,
            )
        else:
            promotion = promote_shadow_strategy(
                underlying_symbol=event.underlying_symbol,
                strategy_id=event.strategy_id,
                user_vetoed=False,
                registry_path=registry_path,
                form_contract_path=form_contract_path,
                assignment_report_path=assignment_report_path,
            )
            final = PromotionLifecycleEvent(
                underlying_symbol=event.underlying_symbol,
                strategy_id=event.strategy_id,
                status=PROMOTED,
                qualified_at=event.qualified_at,
                veto_deadline=event.veto_deadline,
                resolved_at=current_text,
                previous_direct_strategy_id=promotion.previous_direct_strategy_id,
                qualification_evidence=event.qualification_evidence,
            )
        rows[index] = asdict(final)
        resolved.append(final)
        changed = True

    if changed:
        updated = dict(payload)
        updated["events"] = rows
        _atomic_json(path, updated)
    return tuple(resolved)
