"""Publish Swing paper-strategy KPI evidence for the existing AI CIO host."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from swing_trade_bot.enterprise_strategy_kpi_publisher import (
    DEFAULT_STRATEGY_ALLOCATIONS_PATH,
    build_and_write_enterprise_strategy_kpis,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output", default="results/enterprise_strategy_kpis.json")
    parser.add_argument(
        "--strategy-allocations-file",
        default=str(DEFAULT_STRATEGY_ALLOCATIONS_PATH),
        help="JSON containing strategy_allocations['SWING-001']; total account capital is not accepted.",
    )
    args = parser.parse_args()

    output = build_and_write_enterprise_strategy_kpis(
        args.results_dir,
        args.output,
        strategy_allocations_path=args.strategy_allocations_file,
    )
    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    print(json.dumps({
        "output": str(output),
        "strategy_id": payload["strategy_id"],
        "evidence_status": payload["evidence_status"],
        "allocated_capital": payload["allocated_capital"],
        "allocation_source": payload["allocation_source"],
        "portfolio_value": payload["portfolio_value"],
        "portfolio_value_source": payload["portfolio_value_source"],
        "position_count": payload["position_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
