"""Portfolio-level signal combination and position management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from src.config.settings import get_settings
from src.strategy.base import (
    BaseStrategy,
    PositionSizing,
    SignalType,
    StrategyRegistry,
    TradingSignal,
    strategy_registry,
)

if TYPE_CHECKING:
    from src.ib.connection import IBConnectionManager


@dataclass
class CombinedSignal:
    """Aggregated signal from multiple strategies."""

    symbol: str
    signal_type: SignalType
    strategies: list[str]
    avg_strength: float
    consensus: float  # 0-1, agreement among strategies
    timestamp: datetime
    metadata: dict = field(default_factory=dict)


class PortfolioStrategy:
    """Manages multi-strategy signal combination and portfolio-level decisions."""

    def __init__(
        self,
        registry: StrategyRegistry,
        ib_manager: IBConnectionManager,
    ) -> None:
        self.registry = registry
        self.ib = ib_manager
        self.settings = get_settings()
        self.active_signals: dict[str, CombinedSignal] = {}
        self.pending_signals: dict[str, list[TradingSignal]] = {}

    async def process_signals(self) -> list[CombinedSignal]:
        """Process signals from all strategies and combine them."""
        combined = {}

        # Collect signals from all active strategies
        for strategy in self.registry.strategies.values():
            if not strategy.parameters.enabled:
                continue

            for symbol in strategy.get_symbols():
                signals = await strategy.analyze(symbol)
                if signals:
                    self.pending_signals.setdefault(symbol, []).extend(signals)

        # Combine signals per symbol
        for symbol, signals in self.pending_signals.items():
            if not signals:
                continue

            combined_signal = self._combine_signals(symbol, signals)
            if combined_signal:
                combined[symbol] = combined_signal
                self.active_signals[symbol] = combined_signal

        # Clear pending
        self.pending_signals.clear()

        return list(combined.values())

    def _combine_signals(self, symbol: str, signals: list[TradingSignal]) -> CombinedSignal | None:
        """Combine multiple signals into one consensus signal."""
        if not signals:
            return None

        # Group by signal type
        buy_signals = [s for s in signals if s.signal_type in (SignalType.BUY,)]
        sell_signals = [s for s in signals if s.signal_type in (SignalType.SELL,)]

        # Determine consensus
        total = len(signals)
        buy_count = len(buy_signals)
        sell_count = len(sell_signals)

        if buy_count > sell_count:
            signal_type = SignalType.BUY
            winning_signals = buy_signals
            consensus = buy_count / total
        elif sell_count > buy_count:
            signal_type = SignalType.SELL
            winning_signals = sell_signals
            consensus = sell_count / total
        else:
            # Tie - no clear consensus
            return None

        # Require minimum consensus
        if consensus < 0.5:
            return None

        # Average strength
        avg_strength = sum(s.strength.value for s in winning_signals) / len(winning_signals)

        # Combine metadata
        combined_metadata = {}
        for s in winning_signals:
            for k, v in s.metadata.items():
                if k not in combined_metadata:
                    combined_metadata[k] = []
                combined_metadata[k].append(v)

        # Average numeric metadata
        for k, v in combined_metadata.items():
            if v and isinstance(v[0], (int, float)):
                combined_metadata[k] = sum(v) / len(v)

        return CombinedSignal(
            symbol=symbol,
            signal_type=signal_type,
            strategies=[s.strategy_name for s in winning_signals],
            avg_strength=avg_strength,
            consensus=consensus,
            timestamp=datetime.now(),
            metadata=combined_metadata,
        )

    def get_portfolio_risk(self) -> dict:
        """Calculate current portfolio risk metrics."""
        # This would integrate with IB to get actual positions
        # For now, return structure for dashboard
        return {
            "total_exposure": 0.0,
            "sector_exposure": {},
            "correlated_exposure": {},
            "daily_pnl": 0.0,
            "max_drawdown": 0.0,
            "open_positions": 0,
        }

    def validate_signal(self, signal: CombinedSignal) -> tuple[bool, str]:
        """Validate signal against portfolio risk limits."""
        # Check max positions
        # Check sector exposure
        # Check correlation
        # Check daily loss limit
        return True, "OK"

    def get_position_targets(self) -> dict[str, dict]:
        """Get target positions for each symbol."""
        targets = {}
        for symbol, signal in self.active_signals.items():
            # Get strategy to calculate position size
            strategy = self.registry.get(signal.strategies[0]) if signal.strategies else None
            if strategy:
                # This would need account equity from IB
                pass
        return targets