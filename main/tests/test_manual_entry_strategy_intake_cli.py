import json

import swing_trade_bot.manual_entry_strategy_intake_cli as cli


def test_cli_delegates_valid_json_to_swing_intake(monkeypatch) -> None:
    captured = {}

    class Result:
        status = "SAVED"
        strategy_id = "NFLX_TEST"
        underlying_symbol = "NFLX"
        assignment_mode = "DIRECT"
        created_strategy = True
        created_assignment = True
        registry_path = "configs/manual_entry_strategies.json"
        form_contract_path = "results/manual_entry_strategy_form_contract.json"
        assignment_report_path = "results/strategy_assignment_shadow_report.json"

    def fake_apply(payload):
        captured.update(payload)
        from swing_trade_bot.manual_entry_strategy_intake import ManualStrategyIntakeResult
        return ManualStrategyIntakeResult(
            status=Result.status,
            strategy_id=Result.strategy_id,
            underlying_symbol=Result.underlying_symbol,
            assignment_mode=Result.assignment_mode,
            created_strategy=Result.created_strategy,
            created_assignment=Result.created_assignment,
            registry_path=Result.registry_path,
            form_contract_path=Result.form_contract_path,
            assignment_report_path=Result.assignment_report_path,
        )

    monkeypatch.setattr(cli, "apply_manual_entry_strategy_submission", fake_apply)
    code, response = cli.run_cli(json.dumps({"strategy_id": "NFLX_TEST"}))

    assert code == 0
    assert response["ok"] is True
    assert response["paper_trade_mode"] is True
    assert response["result"]["strategy_id"] == "NFLX_TEST"
    assert response["result"]["assignment_mode"] == "DIRECT"
    assert response["result"]["assignment_report_path"] == "results/strategy_assignment_shadow_report.json"
    assert captured["strategy_id"] == "NFLX_TEST"


def test_cli_rejects_non_object_json() -> None:
    code, response = cli.run_cli("[]")
    assert code == 2
    assert response["ok"] is False
    assert response["paper_trade_mode"] is True


def test_cli_rejects_invalid_json_without_traceback() -> None:
    code, response = cli.run_cli("not-json")
    assert code == 2
    assert response["ok"] is False
    assert response["paper_trade_mode"] is True
    assert "error" in response


def test_cli_wraps_unexpected_intake_error_in_paper_only_json(monkeypatch) -> None:
    def boom(payload):
        raise RuntimeError("unexpected intake failure")

    monkeypatch.setattr(cli, "apply_manual_entry_strategy_submission", boom)
    code, response = cli.run_cli(json.dumps({"strategy_id": "NFLX_TEST"}))

    assert code == 2
    assert response == {
        "ok": False,
        "paper_trade_mode": True,
        "error": "unexpected intake failure",
        "error_type": "RuntimeError",
    }
