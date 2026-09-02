import run_swing_bot_cycle as cycle


def test_authoritative_cycle_runs_shadow_and_promotion_lifecycle_before_publish(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cycle, "refresh_enterprise_discovery_inputs", lambda: calls.append("discovery"))
    monkeypatch.setattr(cycle, "refresh_enterprise_discovery_leadership_context", lambda: calls.append("leadership"))
    monkeypatch.setattr(cycle, "apply_active_vetoes_to_runtime_candidates", lambda: calls.append("veto"))
    monkeypatch.setattr(cycle, "refresh_swing_market_data", lambda: calls.append("market") or 0)
    monkeypatch.setattr(cycle, "run_cycle", lambda: calls.append("cycle") or 0)
    monkeypatch.setattr(cycle, "sync_candidate_state_from_watchlist", lambda: calls.append("sync"))
    monkeypatch.setattr(cycle, "_run_shadow_research_nonblocking", lambda: calls.append("shadow"))
    monkeypatch.setattr(cycle, "_process_shadow_promotions_nonblocking", lambda: calls.append("promotion"))
    monkeypatch.setattr(cycle, "publish", lambda: calls.append("publish"))

    assert cycle.main() == 0
    assert calls == [
        "discovery",
        "leadership",
        "veto",
        "market",
        "cycle",
        "sync",
        "shadow",
        "promotion",
        "publish",
    ]


def test_shadow_research_failure_does_not_block_normal_paper_cycle(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cycle, "build_and_write_shadow_strategies", lambda: (_ for _ in ()).throw(RuntimeError("research unavailable")))
    cycle._run_shadow_research_nonblocking()

    output = capsys.readouterr().out
    assert "WARNING: shadow strategy research refresh failed" in output
    assert "RuntimeError: research unavailable" in output


def test_shadow_research_reports_assignment_and_evidence_counts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cycle,
        "build_and_write_shadow_strategies",
        lambda: {
            "rows": [
                {"evidence_status": "AVAILABLE"},
                {"evidence_status": "MISSING_MARKET_DATA"},
            ]
        },
    )

    cycle._run_shadow_research_nonblocking()
    output = capsys.readouterr().out
    assert "2 assignment(s); 1 with evidence" in output


def test_promotion_lifecycle_reports_resolved_counts(monkeypatch, capsys) -> None:
    class Event:
        def __init__(self, status: str) -> None:
            self.status = status

    monkeypatch.setattr(cycle, "process_pending_promotions", lambda **_: (Event("PROMOTED"), Event("VETOED")))
    cycle._process_shadow_promotions_nonblocking()
    output = capsys.readouterr().out
    assert "2 resolved; 1 promoted; 1 vetoed" in output


def test_promotion_lifecycle_failure_does_not_block_normal_paper_cycle(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cycle, "process_pending_promotions", lambda **_: (_ for _ in ()).throw(RuntimeError("promotion unavailable")))
    cycle._process_shadow_promotions_nonblocking()
    output = capsys.readouterr().out
    assert "WARNING: shadow promotion lifecycle refresh failed" in output
    assert "RuntimeError: promotion unavailable" in output


def test_shadow_integration_does_not_run_when_core_cycle_fails(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cycle, "refresh_enterprise_discovery_inputs", lambda: None)
    monkeypatch.setattr(cycle, "refresh_enterprise_discovery_leadership_context", lambda: None)
    monkeypatch.setattr(cycle, "apply_active_vetoes_to_runtime_candidates", lambda: None)
    monkeypatch.setattr(cycle, "refresh_swing_market_data", lambda: 0)
    monkeypatch.setattr(cycle, "run_cycle", lambda: 7)
    monkeypatch.setattr(cycle, "_run_shadow_research_nonblocking", lambda: calls.append("shadow"))
    monkeypatch.setattr(cycle, "_process_shadow_promotions_nonblocking", lambda: calls.append("promotion"))
    monkeypatch.setattr(cycle, "publish", lambda: calls.append("publish"))

    assert cycle.main() == 7
    assert calls == []
