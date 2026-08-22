"""JSON-stdin CLI boundary for explicit user shadow-strategy promotion."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .shadow_strategy_promotion import promote_shadow_strategy


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("promotion payload must be a JSON object")
        result = promote_shadow_strategy(
            underlying_symbol=str(payload.get("underlying_symbol") or ""),
            strategy_id=str(payload.get("strategy_id") or ""),
            user_confirmed=payload.get("user_confirmed") is True,
        )
        print(json.dumps({"ok": True, "paper_trade_mode": True, "result": asdict(result)}))
        return 0
    except (ValueError, PermissionError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "paper_trade_mode": True, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
