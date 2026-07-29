from pathlib import Path

from swing_trade_bot.paper_runner import load_csv


def test_reads_stable_title_case_schema(tmp_path: Path):
    path = tmp_path / "SPY.csv"
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-07-28,100,102,99,101,100.5,123456\n",
        encoding="utf-8",
    )
    bars = load_csv(path)
    assert len(bars) == 1
    assert bars[0].close == 101.0
    assert bars[0].open == 100.0


def test_reads_legacy_lowercase_schema(tmp_path: Path):
    path = tmp_path / "SPY.csv"
    path.write_text(
        "date,open,high,low,close,volume\n"
        "2026-07-28,100,102,99,101,123456\n",
        encoding="utf-8",
    )
    bars = load_csv(path)
    assert len(bars) == 1
    assert bars[0].close == 101.0


def test_adjusted_close_does_not_replace_close(tmp_path: Path):
    path = tmp_path / "SPY.csv"
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-07-28,100,102,99,101,77,123456\n",
        encoding="utf-8",
    )
    assert load_csv(path)[0].close == 101.0
