"""Monthly contribution allocation from optimizer score outputs."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIDENCE_MULTIPLIERS = {
    "HIGH": 1.0,
    "MEDIUM": 0.75,
    "LOW": 0.50,
}
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.35
CONFIDENCE_MAX_WEIGHTS = {
    "HIGH": MAX_WEIGHT,
    "MEDIUM": 0.10,
    "LOW": 0.05,
}
STARTER_SCORE = 0.25
CORE_SYMBOLS = ("SOXL", "TQQQ")
EMERGING_SYMBOLS = ("IONL", "BEX", "IRE", "DRAM", "NEBX")
ALLOCATION_UNIVERSE = (*CORE_SYMBOLS, *EMERGING_SYMBOLS)
FORCED_CONFIDENCE = {
    "SOXL": "HIGH",
    "TQQQ": "HIGH",
    "IONL": "LOW",
    "BEX": "LOW",
    "IRE": "LOW",
    "DRAM": "LOW",
    "NEBX": "LOW",
}


@dataclass(frozen=True, slots=True)
class ScoreInput:
    """Optimizer score plus optional confidence metadata."""

    symbol: str
    score: float
    confidence: str = "HIGH"
    bucket: str = "CORE"

    @property
    def adjusted_score(self) -> float:
        return self.score * CONFIDENCE_MULTIPLIERS[self.confidence]


@dataclass(frozen=True, slots=True)
class AllocationRow:
    """One monthly allocation row."""

    symbol: str
    score: float
    confidence: str
    bucket: str
    adjusted_score: float
    weight: float
    allocation_amount: float


def build_allocation_report(
    scores_path: Path,
    *,
    monthly_contribution: float,
    output_dir: Path | None = None,
    confidence_overrides: dict[str, str] | None = None,
    include_dca_universe: bool = False,
    paper_trade_mode: bool = True,
) -> list[AllocationRow]:
    """Read optimizer scores, calculate allocations, and write report files."""
    if not paper_trade_mode:
        raise ValueError("Allocation engine requires paper_trade_mode=True")
    if monthly_contribution <= 0:
        raise ValueError("monthly_contribution must be positive")
    scores = read_scores(
        scores_path,
        confidence_overrides=confidence_overrides,
        include_dca_universe=include_dca_universe,
    )
    weights = allocate_weights_with_caps(
        [score.adjusted_score for score in scores],
        maximums=[CONFIDENCE_MAX_WEIGHTS[score.confidence] for score in scores],
    )
    rows = [
        AllocationRow(
            symbol=score.symbol,
            score=score.score,
            confidence=score.confidence,
            bucket=score.bucket,
            adjusted_score=score.adjusted_score,
            weight=weight,
            allocation_amount=round(monthly_contribution * weight, 2),
        )
        for score, weight in zip(scores, weights)
    ]
    write_reports(output_dir or scores_path.parent, rows, monthly_contribution)
    return rows


def read_scores(
    path: Path,
    *,
    confidence_overrides: dict[str, str] | None = None,
    include_dca_universe: bool = False,
) -> list[ScoreInput]:
    """Read symbol scores from best_by_score.csv."""
    confidence_overrides = {
        symbol.upper(): confidence.upper()
        for symbol, confidence in (confidence_overrides or {}).items()
    }
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is empty")
        required = {"symbol", "score"}
        missing = required - {field.lower() for field in reader.fieldnames}
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
        scores_by_symbol: dict[str, ScoreInput] = {}
        for row_number, row in enumerate(reader, start=2):
            normalized = {key.lower(): value for key, value in row.items()}
            symbol = normalized["symbol"].strip().upper()
            confidence = confidence_overrides.get(
                symbol,
                FORCED_CONFIDENCE.get(symbol, normalized.get("confidence", "HIGH").strip().upper()),
            )
            if confidence not in CONFIDENCE_MULTIPLIERS:
                raise ValueError(f"row {row_number}: unsupported confidence {confidence}")
            scores_by_symbol[symbol] = ScoreInput(
                symbol=symbol,
                score=float(normalized["score"]),
                confidence=confidence,
                bucket=_bucket_for_symbol(symbol),
            )
    if not scores_by_symbol:
        raise ValueError(f"{path} contains no score rows")
    if include_dca_universe:
        for symbol in ALLOCATION_UNIVERSE:
            if symbol not in scores_by_symbol:
                confidence = confidence_overrides.get(symbol, FORCED_CONFIDENCE[symbol])
                scores_by_symbol[symbol] = ScoreInput(
                    symbol=symbol,
                    score=STARTER_SCORE,
                    confidence=confidence,
                    bucket=_bucket_for_symbol(symbol),
                )
        return [scores_by_symbol[symbol] for symbol in ALLOCATION_UNIVERSE]
    return list(scores_by_symbol.values())


def allocate_weights(
    adjusted_scores: list[float],
    *,
    minimum: float = MIN_WEIGHT,
    maximum: float = MAX_WEIGHT,
) -> list[float]:
    """Normalize scores into capped/floored weights that sum to 1.0."""
    return allocate_weights_with_caps(
        adjusted_scores,
        minimum=minimum,
        maximums=[maximum for _ in adjusted_scores],
        require_full_allocation=True,
    )


def allocate_weights_with_caps(
    adjusted_scores: list[float],
    *,
    minimum: float = MIN_WEIGHT,
    maximums: list[float],
    require_full_allocation: bool = False,
) -> list[float]:
    """Normalize scores using per-symbol maximums.

    If caps make 100% allocation impossible, weights are allocated up to the
    available caps and the caller can treat the remainder as unallocated cash.
    """
    if not adjusted_scores:
        raise ValueError("at least one score is required")
    if len(adjusted_scores) != len(maximums):
        raise ValueError("maximums must match the number of scores")
    if any(score < 0 for score in adjusted_scores):
        raise ValueError("scores must be non-negative")
    if any(maximum < minimum for maximum in maximums):
        raise ValueError("maximum allocation cap cannot be below the minimum floor")
    count = len(adjusted_scores)
    if minimum * count > 1.0:
        raise ValueError("minimum allocation floor is infeasible for the number of symbols")
    total_maximum = sum(maximums)
    if require_full_allocation and total_maximum < 1.0:
        raise ValueError("maximum allocation cap is infeasible for the number of symbols")
    target_total = min(1.0, total_maximum)

    total = sum(adjusted_scores)
    if total == 0:
        weights = [target_total / count for _ in adjusted_scores]
    else:
        weights = [score / total * target_total for score in adjusted_scores]
    return _apply_floor_and_cap(
        weights,
        minimum=minimum,
        maximums=maximums,
        target_total=target_total,
    )


def write_reports(output_dir: Path, rows: list[AllocationRow], monthly_contribution: float) -> tuple[Path, Path]:
    """Write allocation_report.csv and allocation_report.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "allocation_report.csv"
    json_path = output_dir / "allocation_report.json"
    allocated_weight = sum(row.weight for row in rows)
    unallocated_weight = max(0.0, 1.0 - allocated_weight)
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "symbol",
                "score",
                "confidence",
                "bucket",
                "adjusted_score",
                "weight",
                "allocation_amount",
            ],
        )
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    json_path.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "monthly_contribution": monthly_contribution,
                "minimum_allocation_floor": MIN_WEIGHT,
                "maximum_allocation_cap": MAX_WEIGHT,
                "confidence_max_allocation_caps": CONFIDENCE_MAX_WEIGHTS,
                "allocated_weight": allocated_weight,
                "unallocated_weight": unallocated_weight,
                "unallocated_amount": round(monthly_contribution * unallocated_weight, 2),
                "starter_score": STARTER_SCORE,
                "core_symbols": list(CORE_SYMBOLS),
                "emerging_symbols": list(EMERGING_SYMBOLS),
                "allocations": [asdict(row) for row in rows],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return csv_path, json_path


def format_allocation_table(rows: list[AllocationRow]) -> str:
    """Render the allocation report as a readable table."""
    headers = ("Symbol", "Score", "Weight", "Allocation Amount")
    table_rows = [
        (
            row.symbol,
            f"{row.score:.4f}",
            f"{row.weight:.2%}",
            f"${row.allocation_amount:.2f}",
        )
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows))
        for index in range(len(headers))
    ]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in table_rows
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Allocate monthly contributions from optimizer scores")
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--monthly-contribution", type=float, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--raw-scores-only",
        action="store_true",
        help="Only allocate symbols present in the scores CSV; otherwise use the Core/Emerging DCA universe.",
    )
    parser.add_argument(
        "--confidence",
        action="append",
        default=[],
        help="Optional SYMBOL=HIGH|MEDIUM|LOW override. Can be provided multiple times.",
    )
    args = parser.parse_args()

    confidence_overrides = _parse_confidence_overrides(args.confidence)
    rows = build_allocation_report(
        args.scores,
        monthly_contribution=args.monthly_contribution,
        output_dir=args.output_dir,
        confidence_overrides=confidence_overrides,
        include_dca_universe=not args.raw_scores_only,
        paper_trade_mode=True,
    )
    print(format_allocation_table(rows))


def _apply_floor_and_cap(
    weights: list[float],
    *,
    minimum: float,
    maximums: list[float],
    target_total: float,
) -> list[float]:
    fixed: dict[int, float] = {}
    remaining = set(range(len(weights)))
    final = [0.0 for _ in weights]

    while remaining:
        remaining_total = target_total - sum(fixed.values())
        raw_total = sum(weights[index] for index in remaining)
        if raw_total == 0:
            proposed = {index: remaining_total / len(remaining) for index in remaining}
        else:
            proposed = {
                index: weights[index] / raw_total * remaining_total
                for index in remaining
            }
        changed = False
        capped = [
            index for index, weight in proposed.items() if weight > maximums[index]
        ]
        if capped:
            for index in capped:
                fixed[index] = maximums[index]
                remaining.remove(index)
                changed = True
        else:
            floored = [
                index for index, weight in proposed.items() if weight < minimum
            ]
            for index in floored:
                fixed[index] = minimum
                remaining.remove(index)
                changed = True
        if not changed:
            for index, weight in proposed.items():
                final[index] = weight
            break

    for index, weight in fixed.items():
        final[index] = weight
    drift = target_total - sum(final)
    if abs(drift) > 1e-12:
        adjustable = [
            index
            for index, weight in enumerate(final)
            if minimum <= weight + drift <= maximums[index]
        ]
        if adjustable:
            final[adjustable[0]] += drift
    return final


def _parse_confidence_overrides(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"confidence override must be SYMBOL=LEVEL: {value}")
        symbol, confidence = value.split("=", 1)
        overrides[symbol.strip().upper()] = confidence.strip().upper()
    return overrides


def _bucket_for_symbol(symbol: str) -> str:
    return "CORE" if symbol in CORE_SYMBOLS else "EMERGING"


if __name__ == "__main__":
    main()
