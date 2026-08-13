"""Scheduled paper-only Swing operational launcher."""
from __future__ import annotations

from pathlib import Path

import run_swing_bot_cycle
from swing_trade_bot.swing_operational_runtime import run_operational_cycle


def main() -> int:
    root = Path(__file__).resolve().parent
    return run_operational_cycle(root=root, run_cycle=run_swing_bot_cycle.main)


if __name__ == "__main__":
    raise SystemExit(main())
