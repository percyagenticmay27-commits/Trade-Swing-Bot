"""Opportunity quality scoring for paper-only swing trading candidates.

Opportunity Quality answers whether an opportunity is attractive enough to deserve
capital consideration. It intentionally does not answer whether today is the
right entry. Entry Score is accepted only for display transparency.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

SYSTEM_MODE = "QA"
ENTRY_SCORE_GATE = 70.0

COMPONENT_WEIGHTS: dict[str, float] = {
    "fundamental_analysis_score": 0.20,
    "market_intelligence_score": 0.20,
    "conviction_score": 0.20,
    "momentum_score": 0.15,
    "technical_analysis_score": 0.15,
    "market_regime_support_score": 0.05,
    "portfolio_risk_adjustment_score": 0.05,
}

QUALITY_COLUMNS = (
    "symbol",
    "opportunity_quality_score",
    "opportunity_quality_level",
    "fundamental_analysis_score",
    "market_intelligence_score",
    "conviction_score",
    "momentum_score",
    "technical_analysis_score",
    "market_regime_support_score",
    "portfolio_risk_adjustment_score",
    "entry_score",
    "entry_score_gate_passed",
    "system_mode",
    "paper_trade_mode",
)


@dataclass(frozen=True, slots=True)
class OpportunityQualityInput:
    """Input evidence for one opportunity quality evaluation."""

    symbol: str
    fundamental_analysis_score: float | None = None
    market_intelligence_score: float | None = None
    conviction_score: float | None = None
    momentum_score: float | None = None
    technical_analysis_score: float | None = None
    market_regime_support_score: float | None = None
    portfolio_risk_adjustment_score: float | None = None
    entry_score: float | None = None


@dataclass(frozen=True, slots=True)
class OpportunityQualityRow:
    """One scored opportunity quality row."""

    symbol: str
    opportunity_quality_score: float
    opportunity_quality_level: str
    fundamental_analysis_score: float
    market_intelligence_score: float
    conviction_score: float
    momentum_score: float
    technical_analysis_score: float
    market_regime_support_score: float
    portfolio_risk_adjustment_score: float
    entry_score: float
    entry_score_gate_passed: bool
    system_mode: str
    paper_trade_mode: bool = True


@dataclass(frozen=True, slots=True)
class OpportunityQualityReport:
    """Full opportunity quality report."""

    rows: tuple[OpportunityQualityRow, ...]
    component_weights: Mapping[str, float]
    system_mode: str = SYSTEM_MODE
    paper_trade_mode: bool = True
    entry_score_display_only: bool = True


class OpportunityQualityEngine:
    """Evaluate opportunity attractiveness separately from entry timing."""

    def __init__(self, *, paper_trade_mode: bool = True, system_mode: str = SYSTEM_MODE) -> None:
        if not paper_trade_mode:
            raise ValueError("Opportunity quality engine requires paper_trade_mode=True")
        self.paper_trade_mode = paper_trade_mode
        self.system_mode = system_mode.upper()

    def evaluate(self, opportunities: Sequence[OpportunityQualityInput]) -> OpportunityQualityReport:
        rows = tuple(self._evaluate_one(opportunity) for opportunity in opportunities)
        return OpportunityQualityReport(
            rows=rows,
            component_weights=COMPONENT_WEIGHTS,
            system_mode=self.system_mode,
            paper_trade_mode=True,
            entry_score_display_only=True,
        )

    def _evaluate_one(self, opportunity: OpportunityQualityInput) -> OpportunityQualityRow:
        component_scores = {
            name: _score(getattr(opportunity, name))
            for name in COMPONENT_WEIGHTS
        }
        quality = sum(component_scores[name] * weight for name, weight in COMPONENT_WEIGHTS.items())
        entry_score = _score(opportunity.entry_score)
        return OpportunityQualityRow(
            symbol=opportunity.symbol.upper(),
            opportunity_quality_score=round(quality, 6),
            opportunity_quality_level=_quality_level(quality),
            fundamental_analysis_score=component_scores["fundamental_analysis_score"],
            market_intelligence_score=component_scores["market_intelligence_score"],
            conviction_score=component_scores["conviction_score"],
            momentum_score=component_scores["momentum_score"],
            technical_analysis_score=component_scores["technical_analysis_score"],
            market_regime_support_score=component_scores["market_regime_support_score"],
            portfolio_risk_adjustment_score=component_scores["portfolio_risk_adjustment_score"],
            entry_score=entry_score,
            entry_score_gate_passed=entry_score >= ENTRY_SCORE_GATE,
            system_mode=self.system_mode,
            paper_trade_mode=True,
        )


def build_opportunity_quality_report(
    *,
    input_path: Path,
    output_dir: Path,
    paper_trade_mode: bool = True,
    system_mode: str = SYSTEM_MODE,
) -> OpportunityQualityReport:
    """Read opportunity inputs and write opportunity_quality_report files."""
    if not paper_trade_mode:
        raise ValueError("Opportunity quality engine requires paper_trade_mode=True")
    report = OpportunityQualityEngine(paper_trade_mode=True, system_mode=system_mode).evaluate(
        read_opportunity_quality_inputs(input_path)
    )
    write_opportunity_quality_reports(output_dir, report)
    return report


def read_opportunity_quality_inputs(path: Path) -> list[OpportunityQualityInput]:
    """Read opportunity quality inputs from CSV or JSON."""
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows", payload if isinstance(payload, list) else [])
        return [_input_from_mapping(row) for row in rows]
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return [_input_from_mapping(row) for row in csv.DictReader(input_file)]


def write_opportunity_quality_reports(output_dir: Path, report: OpportunityQualityReport) -> tuple[Path, Path, Path]:
    """Write opportunity_quality_report.csv, .json, and .md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "opportunity_quality_report.csv"
    json_path = output_dir / "opportunity_quality_report.json"
    md_path = output_dir / "opportunity_quality_report.md"
    row_dicts = [asdict(row) for row in report.rows]
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(QUALITY_COLUMNS))
        writer.writeheader()
        writer.writerows(row_dicts)
    json_path.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "system_mode": report.system_mode,
                "entry_score_display_only": True,
                "entry_score_not_part_of_opportunity_quality": True,
                "missing_evidence_rule": "missing evidence = 0",
                "component_weights": report.component_weights,
                "rows": row_dicts,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_opportunity_quality_markdown(report) + "\n", encoding="utf-8")
    return csv_path, json_path, md_path


def format_opportunity_quality_markdown(report: OpportunityQualityReport) -> str:
    """Render a Markdown report."""
    lines = [
        "# Opportunity Quality Report",
        "",
        "Paper-only: true",
        f"System mode: {report.system_mode}",
        "Entry Score: display-only and not part of Opportunity Quality.",
        "Missing evidence: 0.",
        "",
        "| Symbol | Quality | Level | Entry Score | Entry Gate |",
        "|---|---:|---|---:|---|",
    ]
    for row in report.rows:
        lines.append(
            f"| {row.symbol} | {row.opportunity_quality_score:.2f} | {row.opportunity_quality_level} | "
            f"{row.entry_score:.2f} | {'PASS' if row.entry_score_gate_passed else 'FAIL'} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create paper-only opportunity quality reports")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--system-mode", default=SYSTEM_MODE)
    args = parser.parse_args()
    report = build_opportunity_quality_report(input_path=args.input, output_dir=args.output_dir, system_mode=args.system_mode)
    print(format_opportunity_quality_markdown(report))


def _input_from_mapping(row: Mapping[str, object]) -> OpportunityQualityInput:
    return OpportunityQualityInput(
        symbol=str(row.get("symbol", row.get("underlying_symbol", ""))).strip(),
        fundamental_analysis_score=_optional(row.get("fundamental_analysis_score")),
        market_intelligence_score=_optional(row.get("market_intelligence_score")),
        conviction_score=_optional(row.get("conviction_score")),
        momentum_score=_optional(row.get("momentum_score")),
        technical_analysis_score=_optional(row.get("technical_analysis_score")),
        market_regime_support_score=_optional(row.get("market_regime_support_score")),
        portfolio_risk_adjustment_score=_optional(row.get("portfolio_risk_adjustment_score")),
        entry_score=_optional(row.get("entry_score")),
    )


def _optional(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _score(value: float | None) -> float:
    if value is None:
        return 0.0
    if value < 0 or value > 100:
        raise ValueError("opportunity quality scores must be between 0 and 100")
    return float(value)


def _quality_level(score: float) -> str:
    if score >= 80.0:
        return "HIGH"
    if score >= 65.0:
        return "MEDIUM"
    if score >= 50.0:
        return "LOW"
    return "WATCHLIST"


if __name__ == "__main__":
    main()
