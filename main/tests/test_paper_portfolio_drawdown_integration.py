import json
from datetime import date
from pathlib import Path

from swing_trade_bot.paper_portfolio_manager import build_and_write_paper_portfolio_report


def _write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-08-01,100,100,100,100,100,1000\n"
        "2026-08-02,120,120,120,120,120,1000\n"
        "2026-08-03,90,90,90,90,90,1000\n"
        "2026-08-04,110,110,110,110,110,1000\n",
        encoding="utf-8",
    )


def test_paper_positions_publish_authoritative_drawdown_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "paper_ledger"
    ledger.mkdir(parents=True)
    (ledger / "open_positions.json").write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "symbol": "AAA",
                        "entry_date": "2026-08-01",
                        "entry_price": 100.0,
                        "shares": 10.0,
                        "cost_basis": 1000.0,
                        "allocation_percent": 25.0,
                        "active_strategy": "Strategy A",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    data = tmp_path / "data"
    _write_csv(data / "AAA.csv")

    build_and_write_paper_portfolio_report(
        ledger_dir=ledger,
        data_dir=data,
        output_dir=ledger,
        account_capital=4500.0,
        as_of=date(2026, 8, 4),
    )

    payload = json.loads((ledger / "paper_portfolio_positions.json").read_text(encoding="utf-8"))
    row = payload["positions"][0]
    assert payload["schema_version"] == "1.2"
    assert row["max_drawdown_amount"] == 300.0
    assert row["max_drawdown_percent"] == 25.0
    assert row["max_drawdown_peak_date"] == "2026-08-02"
    assert row["max_drawdown_trough_date"] == "2026-08-03"
    assert row["drawdown_observation_count"] == 5
    assert row["drawdown_source"] == "COMPLETED_DAILY_MARK_TO_MARKET_BARS_SINCE_ENTRY"


def test_incomplete_history_publishes_null_drawdown_with_warning(tmp_path: Path) -> None:
    ledger = tmp_path / "paper_ledger"
    ledger.mkdir(parents=True)
    (ledger / "open_positions.json").write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "symbol": "AAA",
                        "entry_date": "2026-08-01",
                        "entry_price": 100.0,
                        "shares": 10.0,
                        "cost_basis": 1000.0,
                        "allocation_percent": 25.0,
                        "active_strategy": "Strategy A",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "AAA.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-08-03,90,90,90,90,90,1000\n"
        "2026-08-04,110,110,110,110,110,1000\n",
        encoding="utf-8",
    )

    report = build_and_write_paper_portfolio_report(
        ledger_dir=ledger,
        data_dir=data,
        output_dir=ledger,
        account_capital=4500.0,
        as_of=date(2026, 8, 4),
    )

    payload = json.loads((ledger / "paper_portfolio_positions.json").read_text(encoding="utf-8"))
    row = payload["positions"][0]
    assert row["max_drawdown_amount"] is None
    assert row["max_drawdown_percent"] is None
    assert row["drawdown_source"] is None
    assert any("max drawdown is not reportable" in warning for warning in report.warnings)
