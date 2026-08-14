from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.swing_operational_health import write_operational_health


def main() -> int:
    root = Path(__file__).resolve().parent
    results_dir = root / "results"
    payload, path = write_operational_health(results_dir)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(path)
    return 0 if payload.get("status") == "HEALTHY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
