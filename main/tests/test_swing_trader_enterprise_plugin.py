from __future__ import annotations

import json
from pathlib import Path

import pytest

# This suite covers the legacy Enterprise V1 in-process Plugin SDK adapter. The
# current SWING-001 integration is the frozen Registry v2/local-filesystem
# contract and does not install enterprise_core into the standalone Swing
# runtime. Keep these compatibility tests available when that optional SDK is
# installed, but do not make an absent external SDK prevent collection of the
# authoritative standalone Swing test suite.
pytest.importorskip("enterprise_core", reason="optional legacy Enterprise V1 SDK is not installed in standalone Swing runtime")

from enterprise_core.ai_cio import AICIODiscoveryService
from enterprise_core.plugin_sdk import PluginContext, PluginRuntime, ServiceRegistry
from enterprise_core.runtime import EnterpriseRuntime
from enterprise_core.strategy_registry import StrategyManifestLoader, StrategyManifestValidator
from swing_trade_bot.swing_trader_enterprise_plugin import (
    SWING_STRATEGY_ID,
    SwingContractPaths,
    SwingTraderEnterprisePlugin,
)


def _services() -> ServiceRegistry:
    return ServiceRegistry({"enterprise_market_data": object()})


def _context(root: Path) -> PluginContext:
    return PluginContext(
        strategy_id=SWING_STRATEGY_ID,
        strategy_root=str(root),
        required_services=("enterprise_market_data",),
    )


def _success_cycle(root: Path):
    output = root / "results" / "existing_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('{"unchanged": true}\n', encoding="utf-8")

    def run(context: PluginContext) -> dict:
        assert context.strategy_root == str(root)
        return {
            "cycle_status": "COMPLETE",
            "registration_published": True,
            "published_artifacts": [str(output)],
            "warnings": [],
        }

    return run, output


def test_stable_identity_and_permanent_safety() -> None:
    plugin = SwingTraderEnterprisePlugin(_services(), lambda context: {})
    assert plugin.strategy_id == "STRATEGY-SWING-001"
    assert plugin.paper_trade_mode is True
    assert plugin.live_trading_enabled is False
    assert plugin.broker_execution_enabled is False


def test_initialization_generates_four_contracts(tmp_path: Path) -> None:
    plugin = SwingTraderEnterprisePlugin(_services(), lambda context: {})
    plugin.initialize(_context(tmp_path))
    for filename in ("manifest.json", "status.json", "health.json", "outputs.json"):
        payload = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert payload["strategy_id"] == SWING_STRATEGY_ID
        assert payload["paper_trade_mode"] is True
        assert payload["live_trading_enabled"] is False
        assert payload["broker_execution_enabled"] is False


def test_delegates_cycle_and_preserves_existing_report(tmp_path: Path) -> None:
    runner, output = _success_cycle(tmp_path)
    before = output.read_bytes()
    plugin = SwingTraderEnterprisePlugin(_services(), runner)
    plugin.initialize(_context(tmp_path))
    result = plugin.run()
    assert result.status == "SUCCESS"
    assert result.output_paths == {
        "results/existing_report.json": "results/existing_report.json"
    }
    assert output.read_bytes() == before
    assert result.metadata["delegated_cycle"] == "swing_daily_cycle"


def test_failed_cycle_returns_failed_result_and_updates_contracts(tmp_path: Path) -> None:
    plugin = SwingTraderEnterprisePlugin(
        _services(),
        lambda context: {"cycle_status": "BLOCKED", "errors": ["missing evidence"]},
    )
    plugin.initialize(_context(tmp_path))
    result = plugin.run()
    assert result.status == "FAILED"
    assert "missing evidence" in result.warnings
    assert json.loads((tmp_path / "status.json").read_text())["runtime_state"] == "ERROR"
    assert json.loads((tmp_path / "health.json").read_text())["overall_status"] == "ERROR"


def test_exception_propagates_and_updates_failure_contracts(tmp_path: Path) -> None:
    def fail(context: PluginContext) -> dict:
        raise RuntimeError("paper cycle failed")

    plugin = SwingTraderEnterprisePlugin(_services(), fail)
    plugin.initialize(_context(tmp_path))
    with pytest.raises(RuntimeError, match="paper cycle failed"):
        plugin.run()
    health = json.loads((tmp_path / "health.json").read_text())
    assert health["overall_status"] == "ERROR"
    assert health["errors"] == ["paper cycle failed"]


def test_shutdown_is_safe_and_does_not_remove_paper_state(tmp_path: Path) -> None:
    paper_state = tmp_path / "state" / "positions.json"
    paper_state.parent.mkdir()
    paper_state.write_text('{"positions": []}', encoding="utf-8")
    plugin = SwingTraderEnterprisePlugin(_services(), lambda context: {})
    plugin.initialize(_context(tmp_path))
    plugin.shutdown()
    assert paper_state.exists()
    assert json.loads((tmp_path / "status.json").read_text())["runtime_state"] == "OFFLINE"


def test_output_paths_cannot_escape_strategy_root(tmp_path: Path) -> None:
    plugin = SwingTraderEnterprisePlugin(
        _services(),
        lambda context: {
            "cycle_status": "COMPLETE",
            "published_artifacts": [str(tmp_path.parent / "outside.json")],
        },
    )
    plugin.initialize(_context(tmp_path))
    with pytest.raises(ValueError, match="output path escapes strategy root"):
        plugin.run()


def test_contract_paths_cannot_escape_strategy_root(tmp_path: Path) -> None:
    plugin = SwingTraderEnterprisePlugin(
        _services(),
        lambda context: {},
        contract_paths=SwingContractPaths(manifest="../manifest.json"),
    )
    with pytest.raises(ValueError, match="contract path escapes strategy root"):
        plugin.initialize(_context(tmp_path))


def test_required_service_enforced_by_plugin_and_runtime(tmp_path: Path) -> None:
    missing = ServiceRegistry()
    plugin = SwingTraderEnterprisePlugin(missing, lambda context: {})
    with pytest.raises(KeyError, match="enterprise_market_data"):
        plugin.initialize(_context(tmp_path))
    with pytest.raises(KeyError, match="enterprise_market_data"):
        PluginRuntime(plugin, _context(tmp_path), missing)


def test_manifest_validates_and_is_ai_cio_discoverable(tmp_path: Path) -> None:
    entrypoint = tmp_path / "src" / "swing_trade_bot" / "swing_trader_enterprise_plugin.py"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("# discovery fixture\n", encoding="utf-8")
    plugin = SwingTraderEnterprisePlugin(_services(), lambda context: {})
    plugin.initialize(_context(tmp_path))

    manifest = StrategyManifestLoader().load(tmp_path / "manifest.json")
    validation = StrategyManifestValidator().validate(manifest, strategy_root=tmp_path)
    assert validation.valid, validation.errors
    snapshot = AICIODiscoveryService().discover([tmp_path])
    assert snapshot.strategy_count == 1
    assert snapshot.strategies[0].strategy_id == SWING_STRATEGY_ID


def test_enterprise_runtime_executes_one_existing_paper_cycle(tmp_path: Path) -> None:
    runner, _ = _success_cycle(tmp_path)
    services = _services()
    plugin = SwingTraderEnterprisePlugin(services, runner)
    runtime = EnterpriseRuntime(plugin, _context(tmp_path), services)
    initialized = runtime.initialize()
    assert initialized.initialized is True
    result = runtime.run_once()
    assert result.status == "SUCCESS"
    snapshot = runtime.shutdown()
    assert snapshot.initialized is False
    assert snapshot.run_count == 1


def test_manifest_exposes_no_broker_or_live_permission(tmp_path: Path) -> None:
    plugin = SwingTraderEnterprisePlugin(_services(), lambda context: {})
    plugin.initialize(_context(tmp_path))
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["broker_execution_enabled"] is False
    assert manifest["live_trading_enabled"] is False
    assert not {"broker_execution", "live_trading", "account_management"}.intersection(
        manifest["permissions"]
    )
