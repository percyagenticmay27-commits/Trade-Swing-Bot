"""Runtime report generation for frozen Opportunity Quality calculations."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swing_trade_bot.opportunity_quality_engine import (
    COMPONENT_WEIGHTS,
    OpportunityQualityEngine,
    OpportunityQualityInput,
    OpportunityQualityReport,
    format_opportunity_quality_markdown,
)

SAFETY_FLAGS = {
    "paper_trade_mode": True,
    "live_trading_enabled": False,
    "broker_execution_enabled": False,
    "order_placement_enabled": False,
    "capital_movement_enabled": False,
    "direct_database_writes": False,
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "fundamental_analysis_score": ("fundamental_analysis_score", "fundamental_score", "financial_health_score"),
    "market_intelligence_score": ("market_intelligence_score", "market_intel_score", "intelligence_score"),
    "conviction_score": ("conviction_score", "confidence_score", "source_confluence_score"),
    "momentum_score": ("momentum_score", "theme_momentum_score"),
    "technical_analysis_score": ("technical_analysis_score", "technical_score"),
    "market_regime_support_score": ("market_regime_support_score", "regime_support_score", "market_regime_score"),
    "portfolio_risk_adjustment_score": ("portfolio_risk_adjustment_score", "portfolio_risk_score", "risk_adjustment_score"),
    "entry_score": ("entry_score", "entry_timing_score"),
}

DEFAULT_SOURCE_FILES = (
    "mapped_underlying_quantitative_evidence.json",
    "mapped_underlying_fundamental_evidence.json",
    "opportunity_quality_inputs.json",
    "portfolio_allocations.json",
    "watchlist_report.json",
    "confidence_report.json",
    "momentum_scores.json",
    "market_intelligence.json",
    "market_regime.json",
    "technical_analysis.json",
    "fundamental_analysis.json",
)


def generate_runtime_opportunity_quality_report(*, results_dir: Path, source_paths: Sequence[Path] | None = None, system_mode: str = "QA") -> OpportunityQualityReport:
    evidence = collect_runtime_evidence(results_dir=results_dir, source_paths=source_paths)
    inputs = build_inputs_from_evidence(evidence)
    if not inputs:
        raise FileNotFoundError("No symbol-level Opportunity Quality evidence was found")
    report = OpportunityQualityEngine(paper_trade_mode=True, system_mode=system_mode).evaluate(inputs)
    write_runtime_reports_atomic(results_dir, report, evidence)
    return report


def collect_runtime_evidence(*, results_dir: Path, source_paths: Sequence[Path] | None = None) -> dict[str, dict[str, Any]]:
    paths = list(source_paths or [results_dir / name for name in DEFAULT_SOURCE_FILES])
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        for row in _read_rows(path):
            symbol = str(row.get("symbol", row.get("underlying_symbol", row.get("ticker", "")))).strip().upper()
            if not symbol:
                continue
            target = merged.setdefault(symbol, {"symbol": symbol, "sources": []})
            target["sources"].append(str(path))
            for output_field, aliases in FIELD_ALIASES.items():
                value = _first_numeric(row, aliases)
                if value is not None:
                    target[output_field] = value
    return merged


def build_inputs_from_evidence(evidence: Mapping[str, Mapping[str, Any]]) -> list[OpportunityQualityInput]:
    inputs: list[OpportunityQualityInput] = []
    for symbol in sorted(evidence):
        row = evidence[symbol]
        inputs.append(
            OpportunityQualityInput(
                symbol=symbol,
                fundamental_analysis_score=_optional_score(row.get("fundamental_analysis_score")),
                market_intelligence_score=_optional_score(row.get("market_intelligence_score")),
                conviction_score=_optional_score(row.get("conviction_score")),
                momentum_score=_optional_score(row.get("momentum_score")),
                technical_analysis_score=_optional_score(row.get("technical_analysis_score")),
                market_regime_support_score=_optional_score(row.get("market_regime_support_score")),
                portfolio_risk_adjustment_score=_optional_score(row.get("portfolio_risk_adjustment_score")),
                entry_score=_optional_score(row.get("entry_score")),
            )
        )
    return inputs


def write_runtime_reports_atomic(results_dir: Path, report: OpportunityQualityReport, evidence: Mapping[str, Mapping[str, Any]]) -> tuple[Path, Path, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    ranked_rows = sorted((asdict(row) for row in report.rows), key=lambda row: (-float(row["opportunity_quality_score"]), str(row["symbol"])))
    for rank, row in enumerate(ranked_rows, start=1):
        row["rank"] = rank
        row["evidence_sources"] = list(evidence.get(str(row["symbol"]), {}).get("sources", []))

    json_payload = {
        **SAFETY_FLAGS,
        "generated_at": generated_at,
        "schema_version": "1.0",
        "system_mode": report.system_mode,
        "entry_score_display_only": True,
        "entry_score_not_part_of_opportunity_quality": True,
        "missing_evidence_rule": "missing evidence = 0",
        "component_weights": dict(COMPONENT_WEIGHTS),
        "opportunity_count": len(ranked_rows),
        "rows": ranked_rows,
        "warnings": [],
        "errors": [],
    }

    json_path = results_dir / "opportunity_quality_report.json"
    csv_path = results_dir / "opportunity_quality_report.csv"
    md_path = results_dir / "opportunity_quality_report.md"
    _atomic_write_text(json_path, json.dumps(json_payload, indent=2) + "\n")

    fieldnames = list(ranked_rows[0].keys()) if ranked_rows else []
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False, dir=results_dir) as temp:
        writer = csv.DictWriter(temp, fieldnames=fieldnames)
        writer.writeheader()
        for row in ranked_rows:
            serializable = dict(row)
            serializable["evidence_sources"] = "|".join(serializable.get("evidence_sources", []))
            writer.writerow(serializable)
        temp_path = Path(temp.name)
    os.replace(temp_path, csv_path)

    markdown = format_opportunity_quality_markdown(report)
    markdown += f"\n\nGenerated at: {generated_at}\n"
    _atomic_write_text(md_path, markdown)
    return json_path, csv_path, md_path


def _read_rows(path: Path) -> list[Mapping[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _extract_rows(payload)


def _extract_rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("rows", "opportunities", "candidates", "items", "allocations", "watchlist"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return [payload] if any(key in payload for key in ("symbol", "ticker", "underlying_symbol")) else []


def _first_numeric(row: Mapping[str, Any], aliases: Sequence[str]) -> float | None:
    for alias in aliases:
        if alias not in row or row[alias] in (None, ""):
            continue
        try:
            return float(row[alias])
        except (TypeError, ValueError):
            continue
    return None


def _optional_score(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not 0.0 <= number <= 100.0:
        raise ValueError("Opportunity Quality component scores must be between 0 and 100")
    return number


def _atomic_write_text(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as temp:
        temp.write(content)
        temp.flush()
        os.fsync(temp.fileno())
        temp_path = Path(temp.name)
    os.replace(temp_path, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate runtime Opportunity Quality reports")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--source", action="append", type=Path, default=None)
    parser.add_argument("--system-mode", default="QA")
    args = parser.parse_args()
    report = generate_runtime_opportunity_quality_report(results_dir=args.results_dir, source_paths=args.source, system_mode=args.system_mode)
    print(f"Published {len(report.rows)} Opportunity Quality rows to {args.results_dir}")


if __name__ == "__main__":
    main()
