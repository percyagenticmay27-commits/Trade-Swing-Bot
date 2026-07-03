"""Paper-only portfolio manager for rebalance action generation."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


ActionType = Literal["BUY", "SELL", "HOLD", "MOVE_TO_SGOV"]
ACTION_COLUMNS = (
    "symbol",
    "current_allocation",
    "target_allocation",
    "difference",
    "action",
    "estimated_cash_change",
)
REPORT_COLUMNS = (
    "symbol",
    "allocation_before",
    "allocation_after",
    "action",
)
RESERVE_SYMBOL = "SGOV"


@dataclass(frozen=True, slots=True)
class CurrentPosition:
    """Current paper portfolio position."""

    symbol: str
    shares: float
    market_value: float
    cost_basis: float


@dataclass(frozen=True, slots=True)
class TargetAllocation:
    """Target allocation percent for one symbol."""

    symbol: str
    allocation_percent: float
    cash_equivalent: str = ""


@dataclass(frozen=True, slots=True)
class RebalanceAction:
    """One paper rebalance recommendation."""

    symbol: str
    current_allocation: float
    target_allocation: float
    difference: float
    action: ActionType
    estimated_cash_change: float


@dataclass(frozen=True, slots=True)
class PortfolioManagerReportRow:
    """Monthly portfolio manager report row."""

    symbol: str
    allocation_before: float
    allocation_after: float
    action: ActionType


@dataclass(frozen=True, slots=True)
class PortfolioManagerResult:
    """Complete paper rebalance output."""

    actions: tuple[RebalanceAction, ...]
    report_rows: tuple[PortfolioManagerReportRow, ...]
    cash_reserve: float
    sgov_reserve: float
    total_market_value: float
    paper_trade_mode: bool = True


class PortfolioManager:
    """Compare current portfolio against target allocations."""

    def __init__(self, *, paper_trade_mode: bool = True, tolerance_percent: float = 0.01) -> None:
        if not paper_trade_mode:
            raise ValueError("Portfolio manager requires paper_trade_mode=True")
        if tolerance_percent < 0:
            raise ValueError("tolerance_percent cannot be negative")
        self.paper_trade_mode = paper_trade_mode
        self.tolerance_percent = tolerance_percent

    def rebalance(
        self,
        current_positions: Sequence[CurrentPosition],
        target_allocations: Sequence[TargetAllocation],
    ) -> PortfolioManagerResult:
        """Generate BUY/SELL/HOLD/MOVE_TO_SGOV actions without execution."""
        total_value = sum(position.market_value for position in current_positions)
        if total_value <= 0:
            raise ValueError("current portfolio market value must be positive")

        current_by_symbol = {position.symbol.upper(): position for position in current_positions}
        target_by_symbol = {target.symbol.upper(): target for target in target_allocations}
        symbols = sorted(set(current_by_symbol) | set(target_by_symbol))

        actions: list[RebalanceAction] = []
        report_rows: list[PortfolioManagerReportRow] = []
        for symbol in symbols:
            current = current_by_symbol.get(symbol)
            target = target_by_symbol.get(symbol, TargetAllocation(symbol, 0.0))
            current_allocation = 0.0 if current is None else (current.market_value / total_value) * 100.0
            target_allocation = target.allocation_percent
            difference = target_allocation - current_allocation
            action = _action_for(symbol, difference, target_allocation, self.tolerance_percent)
            estimated_cash_change = (difference / 100.0) * total_value
            if action in {"SELL", "MOVE_TO_SGOV"}:
                estimated_cash_change = -abs(estimated_cash_change)
            elif action == "BUY":
                estimated_cash_change = abs(estimated_cash_change)
            else:
                estimated_cash_change = 0.0
            actions.append(
                RebalanceAction(
                    symbol=symbol,
                    current_allocation=round(current_allocation, 6),
                    target_allocation=round(target_allocation, 6),
                    difference=round(difference, 6),
                    action=action,
                    estimated_cash_change=round(estimated_cash_change, 2),
                )
            )
            report_rows.append(
                PortfolioManagerReportRow(
                    symbol=symbol,
                    allocation_before=round(current_allocation, 6),
                    allocation_after=round(target_allocation, 6),
                    action=action,
                )
            )

        reserve_percent = target_by_symbol.get(RESERVE_SYMBOL, TargetAllocation(RESERVE_SYMBOL, 0.0)).allocation_percent
        reserve_value = total_value * reserve_percent / 100.0
        return PortfolioManagerResult(
            actions=tuple(actions),
            report_rows=tuple(report_rows),
            cash_reserve=round(reserve_value, 2),
            sgov_reserve=round(reserve_value, 2),
            total_market_value=round(total_value, 2),
        )


def build_portfolio_manager_report(
    *,
    current_portfolio_path: Path,
    target_portfolio_path: Path,
    output_dir: Path,
    paper_trade_mode: bool = True,
) -> PortfolioManagerResult:
    """Read input CSVs, generate actions, and write outputs."""
    result = PortfolioManager(paper_trade_mode=paper_trade_mode).rebalance(
        read_current_positions(current_portfolio_path),
        read_target_allocations(target_portfolio_path),
    )
    write_manager_outputs(output_dir, result)
    return result


def read_current_positions(path: Path) -> list[CurrentPosition]:
    """Read current portfolio CSV rows."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        rows: list[CurrentPosition] = []
        for row in csv.DictReader(input_file):
            rows.append(
                CurrentPosition(
                    symbol=row["symbol"].strip().upper(),
                    shares=float(row["shares"]),
                    market_value=float(row["market_value"]),
                    cost_basis=float(row["cost_basis"]),
                )
            )
        return rows


def read_target_allocations(path: Path) -> list[TargetAllocation]:
    """Read target portfolio allocation CSV rows."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        rows: list[TargetAllocation] = []
        for row in csv.DictReader(input_file):
            rows.append(
                TargetAllocation(
                    symbol=row["symbol"].strip().upper(),
                    allocation_percent=float(row["allocation_percent"]),
                    cash_equivalent=row.get("cash_equivalent", ""),
                )
            )
        return rows


def write_manager_outputs(output_dir: Path, result: PortfolioManagerResult) -> tuple[Path, Path, Path]:
    """Write rebalance_actions.csv/json and portfolio_manager_report.csv."""
    output_dir.mkdir(parents=True, exist_ok=True)
    actions_csv = output_dir / "rebalance_actions.csv"
    actions_json = output_dir / "rebalance_actions.json"
    manager_csv = output_dir / "portfolio_manager_report.csv"

    with actions_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(ACTION_COLUMNS))
        writer.writeheader()
        writer.writerows(asdict(action) for action in result.actions)

    actions_json.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "total_market_value": result.total_market_value,
                "cash_reserve": result.cash_reserve,
                "sgov_reserve": result.sgov_reserve,
                "actions": [asdict(action) for action in result.actions],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with manager_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(REPORT_COLUMNS))
        writer.writeheader()
        writer.writerows(asdict(row) for row in result.report_rows)
    return actions_csv, actions_json, manager_csv


def format_rebalance_actions(actions: Sequence[RebalanceAction]) -> str:
    """Render a readable action table."""
    headers = ("Symbol", "Current", "Target", "Diff", "Action", "Cash Change")
    rows = [
        (
            action.symbol,
            f"{action.current_allocation:.2f}%",
            f"{action.target_allocation:.2f}%",
            f"{action.difference:.2f}%",
            action.action,
            f"${action.estimated_cash_change:.2f}",
        )
        for action in actions
    ]
    widths = [max(len(headers[index]), *(len(row[index]) for row in rows)) for index in range(len(headers))]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper-only portfolio rebalance actions")
    parser.add_argument("--current-portfolio", type=Path, required=True)
    parser.add_argument("--target-portfolio", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()

    result = build_portfolio_manager_report(
        current_portfolio_path=args.current_portfolio,
        target_portfolio_path=args.target_portfolio,
        output_dir=args.output_dir,
        paper_trade_mode=True,
    )
    print(format_rebalance_actions(result.actions))
    print(f"cash_reserve: ${result.cash_reserve:.2f}")
    print(f"sgov_reserve: ${result.sgov_reserve:.2f}")


def _action_for(symbol: str, difference: float, target_allocation: float, tolerance: float) -> ActionType:
    if abs(difference) <= tolerance:
        return "HOLD"
    if symbol == RESERVE_SYMBOL:
        return "MOVE_TO_SGOV"
    if target_allocation <= tolerance and difference < 0:
        return "SELL"
    return "BUY" if difference > 0 else "SELL"


if __name__ == "__main__":
    main()
