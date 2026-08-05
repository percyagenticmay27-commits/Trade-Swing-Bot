from pathlib import Path

import pytest

from sync_enterprise_market_data import _export_source
from swing_trade_bot.enterprise_market_data_client import MarketDataUnavailable


def test_history_exports_without_legacy_enabled_flag_are_accepted(tmp_path: Path) -> None:
    contract_path = tmp_path / "results" / "enterprise_market_data_contract.json"
    contract_path.parent.mkdir(parents=True)
    contract = {
        "contract_version": "1.0",
        "history_exports": {
            "atomic_write": True,
            "directory": "enterprise_market_data_history",
            "csv_pattern": "{symbol}.csv",
        },
    }

    source = _export_source(contract_path, contract, "SOXL")

    assert source == (
        contract_path.parent / "enterprise_market_data_history" / "SOXL.csv"
    ).resolve()


def test_explicitly_disabled_history_exports_are_rejected(tmp_path: Path) -> None:
    contract_path = tmp_path / "results" / "enterprise_market_data_contract.json"
    contract_path.parent.mkdir(parents=True)
    contract = {
        "contract_version": "1.0",
        "history_exports": {
            "enabled": False,
            "directory": "enterprise_market_data_history",
            "csv_pattern": "{symbol}.csv",
        },
    }

    with pytest.raises(MarketDataUnavailable, match="not enabled"):
        _export_source(contract_path, contract, "SOXL")
