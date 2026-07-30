"""Enterprise V1 compatibility adapter for the existing Swing Trader.

No strategy calculations live here. One existing paper cycle is delegated and
the four public Enterprise contracts are maintained for Registry and AI CIO.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from enterprise_core.plugin_sdk import (
    EnterpriseStrategyPlugin,
    PluginContext,
    PluginRunResult,
    ServiceRegistry,
)

from .swing_daily_cycle import run_swing_daily_cycle

SWING_STRATEGY_ID = "STRATEGY-SWING-001"
SWING_STRATEGY_NAME = "Trade Swing Bot"
SWING_STRATEGY_VERSION = "1.4.0"
ENTERPRISE_MARKET_DATA_SERVICE = "enterprise_market_data"
CycleRunner = Callable[[PluginContext], Mapping[str, Any] | None]


@dataclass(frozen=True, slots=True)
class SwingContractPaths:
    manifest: str = "manifest.json"
    status: str = "status.json"
    health: str = "health.json"
    outputs: str = "outputs.json"

    def to_dict(self) -> dict[str, str]:
        return {
            "manifest": self.manifest,
            "status": self.status,
            "health": self.health,
            "outputs": self.outputs,
        }


class SwingTraderEnterprisePlugin(EnterpriseStrategyPlugin):
    """Expose the unchanged Swing paper cycle through Plugin SDK V1."""

    paper_trade_mode = True
    live_trading_enabled = False
    broker_execution_enabled = False

    def __init__(
        self,
        services: ServiceRegistry,
        cycle_runner: CycleRunner | None = None,
        *,
        contract_paths: SwingContractPaths | None = None,
    ) -> None:
        if not isinstance(services, ServiceRegistry):
            raise TypeError("services must be a ServiceRegistry")
        if cycle_runner is not None and not callable(cycle_runner):
            raise TypeError("cycle_runner must be callable")
        self._services = services
        self._cycle_runner = cycle_runner or _run_existing_swing_cycle
        self._contract_paths = contract_paths or SwingContractPaths()
        self._context: PluginContext | None = None
        self._last_successful_run: str | None = None
        self._last_failure: dict[str, str] | None = None

    @property
    def strategy_id(self) -> str:
        return SWING_STRATEGY_ID

    def initialize(self, context: PluginContext) -> None:
        context.validate()
        if context.strategy_id != self.strategy_id:
            raise ValueError("PluginContext strategy_id does not match Swing Trader")
        required = tuple(str(name) for name in context.required_services)
        if ENTERPRISE_MARKET_DATA_SERVICE not in {
            name.strip().lower() for name in required
        }:
            raise ValueError("Swing Trader requires enterprise_market_data")
        self._services.require(required)
        self._context = context
        now = _utc_now()
        self._write_contract("manifest", self._manifest())
        self._write_contract(
            "status",
            self._status("INITIALIZED", now, None, (), None),
        )
        self._write_contract("health", self._health("OK", now, (), ()))
        self._write_contract("outputs", self._outputs({}, now, ()))
        self._publish("strategy.plugin.initialized", {"status": "INITIALIZED"})

    def run(self) -> PluginRunResult:
        context = self._require_context()
        started_at = _utc_now()
        self._publish("strategy.plugin.run.started", {"started_at": started_at})
        try:
            payload = dict(self._cycle_runner(context) or {})
            result = self._build_result(payload)
            completed_at = _utc_now()
            if result.status in {"SUCCESS", "WARNING"}:
                self._last_successful_run = completed_at
                self._last_failure = None
            elif result.status == "FAILED":
                self._last_failure = {
                    "timestamp": completed_at,
                    "error": "; ".join(result.warnings) or "Swing paper cycle failed",
                }
            failed = result.status == "FAILED"
            self._write_contract(
                "status",
                self._status(
                    "ERROR" if failed else "ONLINE",
                    completed_at,
                    result.status,
                    result.warnings,
                    self._last_failure["error"] if failed and self._last_failure else None,
                ),
            )
            health = {"SUCCESS": "OK", "FAILED": "ERROR"}.get(
                result.status, "WARNING"
            )
            self._write_contract(
                "health", self._health(health, completed_at, result.warnings, ())
            )
            self._write_contract(
                "outputs",
                self._outputs(result.output_paths, completed_at, result.warnings),
            )
            severity = (
                "ERROR"
                if result.status == "FAILED"
                else "WARNING"
                if result.status == "WARNING"
                else "INFO"
            )
            self._publish(
                "strategy.plugin.run.completed",
                {
                    "status": result.status,
                    "output_paths": dict(result.output_paths),
                    "warnings": list(result.warnings),
                },
                severity=severity,
            )
            return result
        except Exception as exc:
            failed_at = _utc_now()
            self._last_failure = {"timestamp": failed_at, "error": str(exc)}
            self._write_contract(
                "status",
                self._status("ERROR", failed_at, "FAILED", (), str(exc)),
            )
            self._write_contract(
                "health", self._health("ERROR", failed_at, (), (str(exc),))
            )
            self._publish(
                "strategy.plugin.run.failed", {"error": str(exc)}, severity="ERROR"
            )
            raise

    def shutdown(self) -> None:
        if self._context is None:
            return
        stopped_at = _utc_now()
        self._write_contract(
            "status", self._status("OFFLINE", stopped_at, None, (), None)
        )
        self._publish("strategy.plugin.shutdown", {"status": "STOPPED"})
        self._context = None

    def _build_result(self, payload: Mapping[str, Any]) -> PluginRunResult:
        cycle_status = str(
            payload.get("cycle_status") or payload.get("status") or ""
        ).upper()
        if cycle_status in {"COMPLETE", "SUCCESS"}:
            status = "SUCCESS"
        elif cycle_status in {"WARNING", "PARTIAL", "DEGRADED"}:
            status = "WARNING"
        elif cycle_status == "SKIPPED":
            status = "SKIPPED"
        else:
            status = "FAILED"
        warnings = tuple(str(item) for item in payload.get("warnings") or ())
        warnings += tuple(str(item) for item in payload.get("errors") or ())
        result = PluginRunResult(
            strategy_id=self.strategy_id,
            status=status,
            output_paths=self._contained_outputs(payload),
            warnings=warnings,
            metadata={
                "delegated_cycle": "swing_daily_cycle",
                "cycle_status": cycle_status or "UNKNOWN",
                "registration_published": payload.get("registration_published"),
                "paper_trade_mode": True,
                "live_trading_enabled": False,
                "broker_execution_enabled": False,
            },
        )
        result.validate()
        return result

    def _contained_outputs(self, payload: Mapping[str, Any]) -> dict[str, str]:
        root = Path(self._require_context().strategy_root).resolve()
        candidates = [
            str(item) for item in payload.get("published_artifacts") or ()
        ]
        raw_outputs = payload.get("output_paths") or {}
        if isinstance(raw_outputs, Mapping):
            candidates.extend(str(item) for item in raw_outputs.values())
        for configured in (
            "results/swing_daily_cycle_report.json",
            "results/swing_daily_cycle_report.md",
        ):
            if (root / configured).exists():
                candidates.append(configured)
        outputs: dict[str, str] = {}
        for candidate in candidates:
            path = Path(candidate)
            resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError(
                    f"output path escapes strategy root: {candidate}"
                ) from exc
            key = relative.as_posix()
            outputs[key] = key
        return dict(sorted(outputs.items()))

    def _manifest(self) -> dict[str, Any]:
        paths = self._contract_paths.to_dict()
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": SWING_STRATEGY_NAME,
            "strategy_type": "SWING_TRADING",
            "version": SWING_STRATEGY_VERSION,
            "schema_version": "1.0",
            "contract_version": "1.0",
            "lifecycle_status": "PAPER_CERTIFIED",
            "certification_level": "PAPER_CERTIFIED",
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "entrypoint": "src/swing_trade_bot/swing_trader_enterprise_plugin.py",
            "capabilities": [
                "opportunity_discovery",
                "opportunity_quality",
                "momentum_scoring",
                "market_regime",
                "paper_portfolio_reporting",
            ],
            "required_enterprise_services": [ENTERPRISE_MARKET_DATA_SERVICE],
            "required_services": [ENTERPRISE_MARKET_DATA_SERVICE],
            "permissions": [
                "market_data.read",
                "reports.write",
                "state.paper.write",
            ],
            "contracts": paths,
            "output_paths": paths,
            "outputs": {
                "existing_reports_preserved": True,
                "registry_contract": paths["outputs"],
            },
            "state_ownership": {
                "owner": self.strategy_id,
                "scope": "strategy_specific_paper_state",
            },
            "state_owner": self.strategy_id,
        }

    def _status(
        self,
        runtime_state: str,
        updated_at: str,
        latest_cycle: str | None,
        warnings: tuple[str, ...] | list[str],
        error_summary: str | None,
    ) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "schema_version": "1.0",
            "contract_version": "1.0",
            "runtime_state": runtime_state,
            "latest_cycle": latest_cycle,
            "latest_successful_run": self._last_successful_run,
            "latest_failure": self._last_failure,
            "updated_at": updated_at,
            "warnings": list(warnings),
            "error_summary": error_summary,
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
        }

    def _health(
        self,
        overall_status: str,
        timestamp: str,
        warnings: tuple[str, ...] | list[str],
        errors: tuple[str, ...] | list[str],
    ) -> dict[str, Any]:
        required = tuple(self._require_context().required_services)
        return {
            "strategy_id": self.strategy_id,
            "schema_version": "1.0",
            "contract_version": "1.0",
            "overall_status": overall_status,
            "checks": {
                "paper_only": "OK",
                "required_services": "OK",
                "strategy_root": "OK",
            },
            "dependencies": list(required),
            "missing_required_files": [],
            "warnings": list(warnings),
            "errors": list(errors),
            "last_heartbeat": timestamp,
            "ready": overall_status in {"OK", "WARNING"},
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
        }

    def _outputs(
        self,
        output_paths: Mapping[str, str],
        timestamp: str,
        warnings: tuple[str, ...] | list[str],
    ) -> dict[str, Any]:
        paths = sorted(set(str(path) for path in output_paths.values()))
        return {
            "strategy_id": self.strategy_id,
            "schema_version": "1.0",
            "contract_version": "1.0",
            "registered_outputs": [
                {"name": name, "path": path, "format": _output_format(path)}
                for name, path in sorted(output_paths.items())
            ],
            "latest_outputs": dict(sorted(output_paths.items())),
            "output_count": len(paths),
            "missing_outputs": [],
            "warnings": list(warnings),
            "generated_at": timestamp,
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
        }

    def _write_contract(self, name: str, payload: Mapping[str, Any]) -> Path:
        root = Path(self._require_context().strategy_root).resolve()
        target = (root / self._contract_paths.to_dict()[name]).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"contract path escapes strategy root: {name}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return target

    def _publish(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        severity: str = "INFO",
    ) -> None:
        if "event_bus" not in self._services.names():
            return
        event_bus = self._services.resolve("event_bus")
        try:
            from enterprise_core.event_bus import EnterpriseEvent

            event_bus.publish(
                EnterpriseEvent(
                    event_type=event_type,
                    source="swing_trader_enterprise_plugin",
                    payload=dict(payload),
                    strategy_id=self.strategy_id,
                    severity=severity,
                )
            )
        except (ImportError, AttributeError):
            return

    def _require_context(self) -> PluginContext:
        if self._context is None:
            raise RuntimeError("Swing Trader plugin is not initialized")
        return self._context


def _run_existing_swing_cycle(context: PluginContext) -> Mapping[str, Any]:
    configuration = dict(context.configuration)
    return run_swing_daily_cycle(
        context.strategy_root,
        cycle_config_path=str(
            configuration.get(
                "cycle_config_path", "configs/swing_daily_cycle.json"
            )
        ),
    )


def _output_format(path: str) -> str:
    return Path(path).suffix.lower().lstrip(".") or "data"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
