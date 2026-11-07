"""Base strategy classes and interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.ib.market_data import MarketDataPipeline


class SignalType(Enum):
    """Trading signal types."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class SignalStrength(Enum):
    """Signal confidence levels."""

    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class TradingSignal:
    """Represents a trading signal."""

    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    price: float
    timestamp: datetime
    strategy_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional signal metadata (stop loss, take profit, reason, etc.)"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "strength": self.strength.value,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "metadata": self.metadata,
        }


@dataclass
class PositionSizing:
    """Position sizing recommendation."""

    symbol: str
    quantity: int
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class StrategyParameters(BaseModel):
    """Base strategy parameters."""

    model_config = {"extra": "allow"}

    name: str
    enabled: bool = True
    symbols: list[str] = Field(default_factory=list)
    """Empty means all available symbols"""

    # Risk parameters
    max_position_size: float = 0.1
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    risk_per_trade: float = 0.01

    # Execution parameters
    order_type: str = "LMT"
    time_in_force: str = "DAY"


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(
        self,
        parameters: StrategyParameters,
        market_data: MarketDataPipeline,
    ) -> None:
        self.parameters = parameters
        self.market_data = market_data
        self.signals: list[TradingSignal] = []
        self._last_signal_time: dict[str, datetime] = {}

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return strategy identifier."""
        pass

    @abstractmethod
    async def generate_signals(self, symbol: str) -> list[TradingSignal]:
        """Generate trading signals for a symbol."""
        pass

    @abstractmethod
    def calculate_position_size(
        self,
        symbol: str,
        signal: TradingSignal,
        account_equity: float,
        current_price: float,
    ) -> PositionSizing:
        """Calculate position size for a signal."""
        pass

    def get_symbols(self) -> list[str]:
        """Get symbols this strategy trades."""
        if self.parameters.symbols:
            return self.parameters.symbols
        # Return all available symbols from market data
        return list(self.market_data.symbols.keys())

    def should_generate_signal(self, symbol: str, min_interval_minutes: int = 15) -> bool:
        """Check if enough time has passed since last signal."""
        last_time = self._last_signal_time.get(symbol)
        if last_time is None:
            return True

        elapsed = (datetime.now() - last_time).total_seconds() / 60
        return elapsed >= min_interval_minutes

    def record_signal(self, symbol: str) -> None:
        """Record signal generation time."""
        self._last_signal_time[symbol] = datetime.now()

    async def analyze(self, symbol: str) -> list[TradingSignal]:
        """Main analysis entry point."""
        if not self.parameters.enabled:
            return []

        if not self.should_generate_signal(symbol):
            return []

        try:
            signals = await self.generate_signals(symbol)
            for signal in signals:
                self.record_signal(symbol)
                self.signals.append(signal)
            return signals
        except Exception as e:
            logger.error(f"Error in {self.strategy_name} for {symbol}: {e}")
            return []

    def get_recent_signals(self, symbol: str, hours: int = 24) -> list[TradingSignal]:
        """Get recent signals for a symbol."""
        cutoff = datetime.now() - pd.Timedelta(hours=hours)
        return [
            s for s in self.signals
            if s.symbol == symbol and s.timestamp >= cutoff
        ]


class StrategyRegistry:
    """Registry for managing multiple strategies."""

    def __init__(self) -> None:
        self.strategies: dict[str, BaseStrategy] = {}
        self.active_strategy: str | None = None

    def register(self, strategy: BaseStrategy) -> None:
        """Register a strategy."""
        self.strategies[strategy.strategy_name] = strategy
        logger.info(f"Registered strategy: {strategy.strategy_name}")

    def unregister(self, name: str) -> None:
        """Unregister a strategy."""
        if name in self.strategies:
            del self.strategies[name]
            logger.info(f"Unregistered strategy: {name}")

    def get(self, name: str) -> BaseStrategy | None:
        """Get strategy by name."""
        return self.strategies.get(name)

    def set_active(self, name: str) -> bool:
        """Set active strategy."""
        if name in self.strategies:
            self.active_strategy = name
            logger.info(f"Active strategy set to: {name}")
            return True
        return False

    def get_active(self) -> BaseStrategy | None:
        """Get active strategy."""
        if self.active_strategy:
            return self.strategies.get(self.active_strategy)
        return None

    def get_all_signals(self) -> list[TradingSignal]:
        """Get signals from all strategies."""
        all_signals = []
        for strategy in self.strategies.values():
            all_signals.extend(strategy.signals)
        return sorted(all_signals, key=lambda s: s.timestamp, reverse=True)


# Global registry
strategy_registry = StrategyRegistry()


# Import logger at bottom to avoid circular imports
from loguru import logger