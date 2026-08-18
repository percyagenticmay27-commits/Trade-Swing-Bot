from unittest.mock import patch

import run_swing_bot_cycle


def test_market_data_failure_blocks_cycle_and_kpi_publication():
    with (
        patch.object(run_swing_bot_cycle, "refresh_enterprise_discovery_inputs", return_value={}) as discovery,
        patch.object(run_swing_bot_cycle, "refresh_enterprise_financial_health_inputs", return_value={}) as health,
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=2) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle") as cycle,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 2

    discovery.assert_called_once_with()
    health.assert_called_once_with()
    refresh.assert_called_once_with()
    cycle.assert_not_called()
    publish.assert_not_called()


def test_cycle_failure_blocks_kpi_publication_after_market_data_succeeds():
    with (
        patch.object(run_swing_bot_cycle, "refresh_enterprise_discovery_inputs", return_value={}) as discovery,
        patch.object(run_swing_bot_cycle, "refresh_enterprise_financial_health_inputs", return_value={}) as health,
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", return_value=0) as refresh,
        patch.object(run_swing_bot_cycle, "run_cycle", return_value=1) as cycle,
        patch.object(run_swing_bot_cycle, "publish") as publish,
    ):
        assert run_swing_bot_cycle.main() == 1

    discovery.assert_called_once_with()
    health.assert_called_once_with()
    refresh.assert_called_once_with()
    cycle.assert_called_once_with()
    publish.assert_not_called()


def test_successful_discovery_financial_health_market_data_and_cycle_publish_enterprise_kpis():
    order: list[str] = []

    def discovery():
        order.append("discovery")
        return {}

    def health():
        order.append("financial_health")
        return {}

    def refresh():
        order.append("market_data")
        return 0

    def cycle():
        order.append("cycle")
        return 0

    def publish():
        order.append("publish")

    with (
        patch.object(run_swing_bot_cycle, "refresh_enterprise_discovery_inputs", side_effect=discovery),
        patch.object(run_swing_bot_cycle, "refresh_enterprise_financial_health_inputs", side_effect=health),
        patch.object(run_swing_bot_cycle, "refresh_swing_market_data", side_effect=refresh),
        patch.object(run_swing_bot_cycle, "run_cycle", side_effect=cycle),
        patch.object(run_swing_bot_cycle, "publish", side_effect=publish),
    ):
        assert run_swing_bot_cycle.main() == 0

    assert order == ["discovery", "financial_health", "market_data", "cycle", "publish"]
