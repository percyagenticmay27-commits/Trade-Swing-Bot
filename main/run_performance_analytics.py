from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from swing_trade_bot.performance_analytics_engine import (
    build_and_write_performance_analytics_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build paper-only performance analytics evidence.")
    parser.add_argument("--ledger-dir", type=Path, default=Path("results/paper_ledger"))
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    report = build_and_write_performance_analytics_report(
        ledger_dir=args.ledger_dir,
        output_dir=args.output_dir,
    )
    payload = asdict(report)
    payload["strategy_performance"] = [asdict(item) for item in report.strategy_performance]
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
