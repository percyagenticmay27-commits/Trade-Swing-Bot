"""Future broker boundary; no live implementation is included."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from .position_state import MarketBar, PositionState


class BrokerAdapter(ABC):
    """Interface reserved for a future reviewed broker integration."""

    @abstractmethod
    def get_historical_prices(self, symbol: str) -> Sequence[MarketBar]:
        """Return completed historical daily bars for a symbol."""

    @abstractmethod
    def get_current_positions(self) -> Mapping[str, PositionState]:
        """Return positions known to the adapter."""

    @abstractmethod
    def review_order(self, symbol: str, side: str, quantity: float) -> Any:
        """Return a non-executing order review."""

    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: float) -> Any:
        """Reserved signature only; the paper engine never calls this method."""

