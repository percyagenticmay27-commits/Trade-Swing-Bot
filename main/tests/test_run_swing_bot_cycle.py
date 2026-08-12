from unittest.mock import patch

import run_swing_bot_cycle


def test_market_data_failure_blocks_cycle_and_kpi_publication():
    with (
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=2) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle") as cycle,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 2

    refresh.assert_called_once_with()
    cycle.assert_not_called()
    publish.assert_not_called()


def test_cycle_failure_blocks_kpi_publication_after_market_data_succeeds():
    with (
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=0) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle", return_value=1) as cycle,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 1

    refresh.assert_called_once_with()
    cycle.assert_called_once_with()
    publish.assert_not_called()


def test_successful_market_data_and_cycle_publish_enterprise_kpis():
    with (
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=0) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle", return_value=0) as cycle,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 0

    refresh.assert_called_once_with()
    cycle.assert_called_once_with()
    publish.assert_called_once_with()
