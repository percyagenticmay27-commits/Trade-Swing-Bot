"""JSON-stdin CLI for Swing-owned manual strategy assignment removal."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any

from .manual_strategy_assignment_removal import remove_manual_strategy_assignment


def run_cli(raw: str) -> tuple[int, dict[str, Any]]:
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
        result = remove_manual_strategy_assignment(
            underlying_symbol=str(payload.get("underlying_symbol", "")),
            strategy_id=str(payload.get("strategy_id", "")),
            assignment_mode=str(payload.get("assignment_mode", "")),
            confirm=payload.get("confirm") is True,
            prune_unreferenced_strategy=payload.get("prune_unreferenced_strategy") is True,
        )
        response = asdict(result)
        response["paper_trade_mode"] = True
        return 0, response
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        return 2, {
            "status": "REJECTED",
            "paper_trade_mode": True,
            "error": f"{type(exc).__name__}: {exc}",
        }
    except Exception as exc:  # preserve fail-closed JSON envelope for host/operator diagnostics
        return 2, {
            "status": "ERROR",
            "paper_trade_mode": True,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    code, response = run_cli(sys.stdin.read())
    print(json.dumps(response))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
