import json

from swing_trade_bot import manual_strategy_assignment_removal_cli as cli


def test_cli_delegates_confirmed_exact_removal(monkeypatch) -> None:
    captured = {}

    class Result:
        status = "REMOVED"
        underlying_symbol = "NFLX"
        strategy_id = "TRANSPORT_DIAGNOSTIC"
        assignment_mode = "SHADOW"
        assignment_removed = True
        strategy_definition_removed = True
        registry_path = "configs/manual_entry_strategies.json"
        form_contract_path = "results/manual_entry_strategy_form_contract.json"
        assignment_report_path = "results/strategy_assignment_shadow_report.json"
        paper_trade_mode = True

    def fake_remove(**kwargs):
        captured.update(kwargs)
        from swing_trade_bot.manual_strategy_assignment_removal import ManualStrategyAssignmentRemovalResult
        return ManualStrategyAssignmentRemovalResult(**Result.__dict__ | {})

    # Construct explicitly because class __dict__ contains implementation keys.
    def fake_remove_clean(**kwargs):
        captured.update(kwargs)
        from swing_trade_bot.manual_strategy_assignment_removal import ManualStrategyAssignmentRemovalResult
        return ManualStrategyAssignmentRemovalResult(
            status="REMOVED", underlying_symbol="NFLX", strategy_id="TRANSPORT_DIAGNOSTIC",
            assignment_mode="SHADOW", assignment_removed=True, strategy_definition_removed=True,
            registry_path="configs/manual_entry_strategies.json",
            form_contract_path="results/manual_entry_strategy_form_contract.json",
            assignment_report_path="results/strategy_assignment_shadow_report.json",
        )

    monkeypatch.setattr(cli, "remove_manual_strategy_assignment", fake_remove_clean)
    code, response = cli.run_cli(json.dumps({
        "underlying_symbol": "NFLX",
        "strategy_id": "TRANSPORT_DIAGNOSTIC",
        "assignment_mode": "SHADOW",
        "confirm": True,
        "prune_unreferenced_strategy": True,
    }))
    assert code == 0
    assert response["paper_trade_mode"] is True
    assert response["status"] == "REMOVED"
    assert captured["confirm"] is True
    assert captured["prune_unreferenced_strategy"] is True


def test_cli_rejects_invalid_request_with_paper_only_envelope() -> None:
    code, response = cli.run_cli("[]")
    assert code == 2
    assert response["status"] == "REJECTED"
    assert response["paper_trade_mode"] is True
