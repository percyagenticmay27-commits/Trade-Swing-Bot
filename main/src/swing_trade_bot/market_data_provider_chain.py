"""Provider-chain orchestration for paper-only daily market data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .market_data_models import DailyMarketBar
from .market_data_provider import MarketDataProvider, MarketDataProviderError


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider: str
    status: str
    error: str | None = None
    classification: str | None = None
    bar_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "status": self.status,
            "error": self.error,
            "classification": self.classification,
            "bar_count": self.bar_count,
        }


@dataclass(frozen=True, slots=True)
class ProviderChainResult:
    bars: tuple[DailyMarketBar, ...]
    selected_provider: str | None
    attempts: tuple[ProviderAttempt, ...]
    adjusted_close_source: str
    corporate_action_adjusted: bool


class MarketDataProviderChain:
    """Try configured read-only providers in order without publication side effects."""

    def __init__(self, providers: Sequence[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("at least one market-data provider is required")
        names = [provider.provider_name for provider in providers]
        if len(names) != len(set(names)):
            raise ValueError("market-data provider names must be unique")
        self._providers = tuple(providers)

    @property
    def provider_name(self) -> str:
        names = [provider.provider_name for provider in self._providers]
        return "->".join((*names, "PRIOR_LOCAL_CSV"))

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(provider.provider_name for provider in self._providers)

    def fetch_daily_bars(
        self,
        symbol: str,
        *,
        target_completed_bars: int,
        as_of_utc: datetime,
    ) -> ProviderChainResult:
        attempts: list[ProviderAttempt] = []
        for provider in self._providers:
            name = provider.provider_name
            try:
                bars = tuple(
                    provider.fetch_daily_bars(
                        symbol,
                        target_completed_bars=target_completed_bars,
                        as_of_utc=as_of_utc,
                    )
                )
            except MarketDataProviderError as exc:
                attempts.append(
                    ProviderAttempt(
                        provider=name,
                        status="FAILED",
                        error=str(exc),
                        classification=getattr(exc, "classification", None),
                    )
                )
                continue
            except Exception as exc:
                attempts.append(
                    ProviderAttempt(
                        provider=name,
                        status="FAILED",
                        error=str(exc),
                        classification="NETWORK_FAILURE",
                    )
                )
                continue

            adjusted_source = str(
                getattr(provider, "adjusted_close_source", "PROVIDER_ADJUSTED_CLOSE")
            )
            corporate_adjusted = bool(
                getattr(provider, "corporate_action_adjusted", True)
            )
            attempts.append(
                ProviderAttempt(provider=name, status="SUCCESS", bar_count=len(bars))
            )
            return ProviderChainResult(
                bars=bars,
                selected_provider=name,
                attempts=tuple(attempts),
                adjusted_close_source=adjusted_source,
                corporate_action_adjusted=corporate_adjusted,
            )

        return ProviderChainResult(
            bars=(),
            selected_provider=None,
            attempts=tuple(attempts),
            adjusted_close_source="UNAVAILABLE",
            corporate_action_adjusted=False,
        )
