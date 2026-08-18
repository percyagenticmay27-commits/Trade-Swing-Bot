from unittest.mock import patch

import run_swing_bot_cycle


def test_market_data_failure_blocks_cycle_state_sync_and_kpi_publication():
    with (
        patch.object(run_swing_bot_cycle, "refresh_enterprise_discovery_inputs", return_value={}) as discovery,
        patch.object(run_swing_bot_cycle, "refresh_enterprise_financial_health_inputs", return_value={}) as health,
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=2) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle") as cycle,
        patch.object(run_swing_bot_cycle, "sync_candidate_state_from_watchlist") as sync,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 2

    discovery.assert_called_once_with()
    health.assert_called_once_with()
    refresh.assert_called_once_with()
    cycle.assert_not_called()
    sync.assert_not_called()
    publish.assert_not_called()


def test_cycle_failure_blocks_state_sync_and_kpi_publication_after_market_data_succeeds():
    with (
        patch.object(run_swing_bot_cycle, "refresh_enterprise_discovery_inputs", return_value={}) as discovery,
        patch.object(run_swing_bot_cycle, "refresh_enterprise_financial_health_inputs", return_value={}) as health,
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=0) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle", return_value=1) as cycle,
        patch.object(run_swing_bot_cycle, "sync_candidate_state_from_watchlist") as sync,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 1

    discovery.assert_called_once_with()
    health.assert_called_once_with()
    refresh.assert_called_once_with()
    cycle.assert_called_once_with()
    sync.assert_not_called()
    publish.assert_not_called()


def test_successful_cycle_persists_swing_state_before_enterprise_kpi_publication():
    order: list[str] = []

    def record(name: str, result=None):
        def action():
            order.append(name)
            return result
        return action

    with (
        patch.object(run_swing_bot_cycle, "refresh_enterprise_discovery_inputs", side_effect=record("discovery", {})),
        patch.object(run_swing_bot_cycle, "refresh_enterprise_financial_health_inputs", side_effect=record("financial_health", {})),
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", side_effect=record("market_data", 0)),
        patch.object(run_swing_bot_cycle, "run_cycle", side_effect=record("cycle", 0)),
        patch.object(run_swing_bot_cycle, "sync_candidate_state_from_watchlist", side_effect=record("state_sync")),
        patch.object(run_swing_bot_cycle, "publish", side_effect=record("publish")),
    ):
        assert run_swing_bot_cycle.main() == 0

    assert order == ["discovery", "financial_health", "market_data", "cycle", "state_sync", "publish"]
