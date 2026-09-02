from pathlib import Path


def _source() -> str:
    return Path("run_swing_bot_cycle.py").read_text(encoding="utf-8")


def test_server_launcher_uses_single_governed_frozen_operational_cycle() -> None:
    source = _source()
    assert "from swing_trade_bot.frozen_primary_operational_cycle import run_frozen_primary_operational_cycle" in source
    assert "def _run_frozen_primary_operational_cycle_nonblocking()" in source
    assert "_run_frozen_primary_operational_cycle_nonblocking()" in source


def test_server_launcher_no_longer_runs_separate_frozen_refresh_and_research_paths() -> None:
    source = _source()
    assert "from swing_trade_bot.intraday_market_data_refresh import refresh_intraday_market_data" not in source
    assert "from swing_trade_bot.frozen_strategy_operational_workflow import build_and_write_frozen_strategy_evidence" not in source
    assert "def _refresh_frozen_intraday_nonblocking()" not in source
    assert "def _run_frozen_strategy_research_nonblocking()" not in source


def test_frozen_promotion_review_and_veto_resolution_remain_after_operational_cycle() -> None:
    source = _source()
    cycle = source.index("_run_frozen_primary_operational_cycle_nonblocking()", source.index("def main()"))
    review = source.index("_run_frozen_promotion_review_nonblocking()", source.index("def main()"))
    resolve = source.index("_process_frozen_promotions_nonblocking()", source.index("def main()"))
    publish = source.index("publish()", source.index("def main()"))
    assert cycle < review < resolve < publish


def test_server_launcher_preserves_paper_only_nonblocking_boundary() -> None:
    source = _source()
    assert "WARNING: frozen Primary operational cycle failed" in source
    assert "paper event(s) executed" in source
    assert "broker" not in source[source.index("def _run_frozen_primary_operational_cycle_nonblocking()"):source.index("def _run_shadow_promotion_review_nonblocking()")].lower()
