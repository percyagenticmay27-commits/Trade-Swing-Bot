"""Publish canonical Opportunity Quality evidence for Enterprise KPI consumption."""
from __future__ import annotations

import argparse

from swing_trade_bot.opportunity_quality_publisher import (
    build_and_write_opportunity_quality_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish paper-only Opportunity Quality evidence.")
    parser.add_argument("--source", default="results/opportunity_quality_report.json")
    parser.add_argument("--output", default="results/opportunity_quality.json")
    args = parser.parse_args()
    output = build_and_write_opportunity_quality_evidence(args.source, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
