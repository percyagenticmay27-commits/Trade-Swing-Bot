"""CLI transport for SWING-001 manual entry-strategy intake.

Reads one JSON object from stdin, delegates all validation/persistence to the
Swing-owned intake handler, and emits a JSON result to stdout. This module is
paper-only and exists so an external host can submit a request without direct
write access to Swing strategy storage.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any

from .manual_entry_strategy_intake import apply_manual_entry_strategy_submission

PAPER_TRADE_MODE = True


def run_cli(stdin_text: str) -> tuple[int, dict[str, Any]]:
    """Run one intake request and always return a paper-only JSON envelope."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("submission must be a JSON object")
        result = apply_manual_entry_strategy_submission(payload)
        return 0, {
            "ok": True,
            "paper_trade_mode": True,
            "result": asdict(result),
        }
    except Exception as exc:  # transport boundary must never leak a traceback to the host
        return 2, {
            "ok": False,
            "paper_trade_mode": True,
            "error": str(exc) or exc.__class__.__name__,
            "error_type": exc.__class__.__name__,
        }


def main() -> int:
    code, response = run_cli(sys.stdin.read())
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
