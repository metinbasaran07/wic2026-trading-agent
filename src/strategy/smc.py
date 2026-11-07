"""Smart Money Concepts (SMC) Strategy Implementation.

Implements:
- Market Structure (BOS/CHoCH)
- Order Blocks (OB)
- Fair Value Gaps (FVG)
- Breaker Blocks
- Liquidity Pools
- Premium/Discount zones
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from loguru import logger

from src.config.settings import get_settings
from src.ib.market_data import MarketDataPipeline
from src.strategy.base import (
    BaseStrategy,
    PositionSizing,
    SignalStrength,
    SignalType,
    StrategyParameters,
    TradingSignal,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class MarketStructureType(Enum):
    """Market structure types."""

    BULLISH_BOS = "bullish_bos"  # Break of Structure - bullish
    BEARISH_BOS = "bearish_bos"  # Break of Structure - bearish
    BULLISH_CHoCH = "bullish_choch"  # Change of Character - bullish
    BEARISH_CHoCH = "bearish_choch"  # Change of Character - bearish


class OrderBlockType(Enum):
    """Order block types."""

    BULLISH_OB = "bullish_ob"
    BEARISH_OB = "bearish_ob"


@dataclass
class SwingPoint:
    """Represents a swing high/low."""

    index: int
    price: float
    timestamp: datetime
    is_high: bool
    strength: int = 1  # Number of bars on each side


@dataclass
class MarketStructure:
    """Market structure event."""

    type: MarketStructureType
    timestamp: datetime
    price: float
    swing_index: int
    confirmed: bool = False


@dataclass
class OrderBlock:
    """Order block representation."""

    type: OrderBlockType
    timestamp: datetime
    top: float
    bottom: float
    entry_price: float
    swing_index: int
    mitigated: bool = False
    mitigation_time: datetime | None = None
    strength: float = 1.0


@dataclass
class FairValueGap:
    """Fair Value Gap representation."""

    timestamp: datetime
    top: float
    bottom: float
    midpoint: float
    direction: str  # "bullish" or "bearish"
    filled: bool = False
    fill_time: datetime | None = None
    index: int = 0


@dataclass
class LiquidityPool:
    """Liquidity pool (buy/sell side liquidity)."""

    timestamp: datetime
    price: float
    type: str  # "buy_side" or "sell_side"
    sweeped: bool = False
    sweep_time: datetime | None = None
    strength: int = 1


@dataclass
class BreakerBlock:
    """Breaker block (failed order block that becomes S/R)."""

    timestamp: datetime
    top: float
    bottom: float
    direction: str  # "bullish" or "bearish"
    tested: bool = False


class SMCParameters(StrategyParameters):
    """SMC-specific parameters."""

    name: str = "smc"

    # Structure detection
    swing_length: int = 10
    """Bars on each side for swing detection"""

    ob_lookback: int = 50
    """Lookback for order block detection"""

    fvg_min_size: float = 0.0001
    """Minimum FVG size as fraction of price"""

    liquidity_lookback: int = 20
    """Lookback for liquidity pools"""

    # Trading rules
    require_bos_confirmation: bool = True
    """Require BOS before trading OB"""

    trade_premium_discount: bool = True
    """Only buy in discount, sell in premium"""

    use_breaker_blocks: bool = True
    """Use breaker blocks as additional confluence"""

    min_risk_reward: float = 2.0
    """Minimum risk:reward ratio"""

    max_ob_age_bars: int = 100
    """Maximum age of order block to trade"""

    # Session filters
    trade_ny_session_only: bool = True
    """Only trade during NY session"""

    avoid_news_times: bool = True
    """Avoid high-impact news times"""


class SMCStrategy(BaseStrategy):
    """Smart Money Concepts trading strategy."""

    def __init__(
        self,
        parameters: SMCParameters,
        market_data: MarketDataPipeline,
    ) -> None:
        super().__init__(parameters, market_data)
        self.params: SMCParameters = parameters
        self.settings = get_settings()

        # SMC data storage per symbol
        self.swing_points: dict[str, list[SwingPoint]] = {}
        self.market_structure: dict[str, list[MarketStructure]] = {}
        self.order_blocks: dict[str, list[OrderBlock]] = {}
        self.fair_value_gaps: dict[str, list[FairValueGap]] = {}
        self.liquidity_pools: dict[str, list[LiquidityPool]] = {}
        self.breaker_blocks: dict[str, list[BreakerBlock]] = {}

        # Subscribe to market data updates
        for symbol in self.get_symbols():
            self.market_data.subscribe(symbol, self._on_bar_update)

    @property
    def strategy_name(self) -> str:
        return "smc"

    async def generate_signals(self, symbol: str) -> list[TradingSignal]:
        """Generate SMC-based trading signals."""
        # Update SMC analysis for this symbol
        await self._update_smc_analysis(symbol)

        # Get current price
        current_price = self.market_data.get_latest_price(symbol)
        if not current_price:
            return []

        # Get latest completed bar
        latest_bar = self.market_data.get_latest_bar(symbol)
        if latest_bar is None:
            return []

        signals = []

        # Check for bullish setup
        bullish_signal = self._check_bullish_setup(symbol, current_price, latest_bar)
        if bullish_signal:
            signals.append(bullish_signal)

        # Check for bearish setup
        bearish_signal = self._check_bearish_setup(symbol, current_price, latest_bar)
        if bearish_signal:
            signals.append(bearish_signal)

        return signals

    async def _update_smc_analysis(self, symbol: str) -> None:
        """Update all SMC components for a symbol."""
        df = self.market_data.get_bars(symbol, count=self.params.ob_lookback + 50)
        if df.empty or len(df) < self.params.swing_length * 2:
            return

        # Update swing points
        self._detect_swings(symbol, df)

        # Update market structure (BOS/CHoCH)
        self._detect_market_structure(symbol)

        # Update order blocks
        self._detect_order_blocks(symbol, df)

        # Update fair value gaps
        self._detect_fvg(symbol, df)

        # Update liquidity pools
        self._detect_liquidity(symbol, df)

        # Update breaker blocks
        if self.params.use_breaker_blocks:
            self._detect_breaker_blocks(symbol)

        # Clean old data
        self._cleanup_old_data(symbol, df.index[-1])

    def _detect_swings(self, symbol: str, df: pd.DataFrame) -> None:
        """Detect swing highs and lows."""
        length = self.params.swing_length
        highs = df["high"].values
        lows = df["low"].values
        timestamps = df.index

        swings = []

        # Swing highs
        for i in range(length, len(highs) - length):
            if all(highs[i] >= highs[i - j] for j in range(1, length + 1)) and \
               all(highs[i] >= highs[i + j] for j in range(1, length + 1)):
                swings.append(SwingPoint(
                    index=i,
                    price=highs[i],
                    timestamp=timestamps[i],
                    is_high=True,
                    strength=length,
                ))

        # Swing lows
        for i in range(length, len(lows) - length):
            if all(lows[i] <= lows[i - j] for j in range(1, length + 1)) and \
               all(lows[i] <= lows[i + j] for j in range(1, length + 1)):
                swings.append(SwingPoint(
                    index=i,
                    price=lows[i],
                    timestamp=timestamps[i],
                    is_high=False,
                    strength=length,
                ))

        # Sort by timestamp
        swings.sort(key=lambda s: s.timestamp)
        self.swing_points[symbol] = swings

    def _detect_market_structure(self, symbol: str) -> None:
        """Detect BOS and CHoCH."""
        swings = self.swing_points.get(symbol, [])
        if len(swings) < 4:
            return

        structure_events = []

        # Analyze last several swings for structure breaks
        for i in range(2, len(swings) - 1):
            current = swings[i]
            prev = swings[i - 1]
            prev2 = swings[i - 2]

            # Bullish BOS: Higher high after higher low
            if current.is_high and prev2.is_high and not prev.is_high:
                if current.price > prev2.price and prev.price > prev2.price:
                    structure_events.append(MarketStructure(
                        type=MarketStructureType.BULLISH_BOS,
                        timestamp=current.timestamp,
                        price=current.price,
                        swing_index=current.index,
                    ))

            # Bearish BOS: Lower low after lower high
            if not current.is_high and not prev2.is_high and prev.is_high:
                if current.price < prev2.price and prev.price < prev2.price:
                    structure_events.append(MarketStructure(
                        type=MarketStructureType.BEARISH_BOS,
                        timestamp=current.timestamp,
                        price=current.price,
                        swing_index=current.index,
                    ))

            # Bullish CHoCH: Break of bearish structure
            if current.is_high and not prev.is_high and not prev2.is_high:
                if current.price > prev.price:
                    structure_events.append(MarketStructure(
                        type=MarketStructureType.BULLISH_CHoCH,
                        timestamp=current.timestamp,
                        price=current.price,
                        swing_index=current.index,
                    ))

            # Bearish CHoCH: Break of bullish structure
            if not current.is_high and prev.is_high and prev2.is_high:
                if current.price < prev.price:
                    structure_events.append(MarketStructure(
                        type=MarketStructureType.BEARISH_CHoCH,
                        timestamp=current.timestamp,
                        price=current.price,
                        swing_index=current.index,
                    ))

        self.market_structure[symbol] = structure_events

    def _detect_order_blocks(self, symbol: str, df: pd.DataFrame) -> None:
        """Detect order blocks (last up/down candle before impulsive move)."""
        swings = self.swing_points.get(symbol, [])
        structure = self.market_structure.get(symbol, [])

        if not swings or len(df) < 10:
            return

        obs = []

        # Find impulsive moves (strong candles after structure)
        for struct in structure[-5:]:  # Check recent structure events
            swing_idx = struct.swing_index
            if swing_idx >= len(df):
                continue

            # Look for order block before the structure break
            lookback = min(self.params.ob_lookback, swing_idx)

            if struct.type in (MarketStructureType.BULLISH_BOS, MarketStructureType.BULLISH_CHoCH):
                # Bullish OB: Last down candle before up move
                for i in range(swing_idx - 1, max(swing_idx - lookback, 0), -1):
                    if df.iloc[i]["close"] < df.iloc[i]["open"]:  # Down candle
                        ob = OrderBlock(
                            type=OrderBlockType.BULLISH_OB,
                            timestamp=df.index[i],
                            top=df.iloc[i]["high"],
                            bottom=df.iloc[i]["low"],
                            entry_price=df.iloc[i]["close"],
                            swing_index=i,
                        )
                        obs.append(ob)
                        break

            elif struct.type in (MarketStructureType.BEARISH_BOS, MarketStructureType.BEARISH_CHoCH):
                # Bearish OB: Last up candle before down move
                for i in range(swing_idx - 1, max(swing_idx - lookback, 0), -1):
                    if df.iloc[i]["close"] > df.iloc[i]["open"]:  # Up candle
                        ob = OrderBlock(
                            type=OrderBlockType.BEARISH_OB,
                            timestamp=df.index[i],
                            top=df.iloc[i]["high"],
                            bottom=df.iloc[i]["low"],
                            entry_price=df.iloc[i]["open"],
                            swing_index=i,
                        )
                        obs.append(ob)
                        break

        # Merge with existing, avoid duplicates
        existing_times = {ob.timestamp for ob in self.order_blocks.get(symbol, [])}
        for ob in obs:
            if ob.timestamp not in existing_times:
                self.order_blocks.setdefault(symbol, []).append(ob)

    def _detect_fvg(self, symbol: str, df: pd.DataFrame) -> None:
        """Detect Fair Value Gaps (3-candle pattern)."""
        fvgs = []

        for i in range(2, len(df)):
            c1 = df.iloc[i - 2]  # First candle
            c2 = df.iloc[i - 1]  # Middle candle (gap)
            c3 = df.iloc[i]      # Third candle

            # Bullish FVG: Gap between c1 high and c3 low
            if c1["high"] < c3["low"]:
                gap_size = (c3["low"] - c1["high"]) / c3["low"]
                if gap_size >= self.params.fvg_min_size:
                    fvg = FairValueGap(
                        timestamp=df.index[i],
                        top=c3["low"],
                        bottom=c1["high"],
                        midpoint=(c3["low"] + c1["high"]) / 2,
                        direction="bullish",
                        index=i,
                    )
                    fvgs.append(fvg)

            # Bearish FVG: Gap between c1 low and c3 high
            elif c1["low"] > c3["high"]:
                gap_size = (c1["low"] - c3["high"]) / c1["low"]
                if gap_size >= self.params.fvg_min_size:
                    fvg = FairValueGap(
                        timestamp=df.index[i],
                        top=c1["low"],
                        bottom=c3["high"],
                        midpoint=(c1["low"] + c3["high"]) / 2,
                        direction="bearish",
                        index=i,
                    )
                    fvgs.append(fvg)

        # Merge with existing
        existing_times = {fvg.timestamp for fvg in self.fair_value_gaps.get(symbol, [])}
        for fvg in fvgs:
            if fvg.timestamp not in existing_times:
                self.fair_value_gaps.setdefault(symbol, []).append(fvg)

    def _detect_liquidity(self, symbol: str, df: pd.DataFrame) -> None:
        """Detect buy-side and sell-side liquidity pools."""
        swings = self.swing_points.get(symbol, [])
        if len(swings) < 2:
            return

        pools = []
        lookback = self.params.liquidity_lookback

        # Recent swing highs = sell-side liquidity (stops above)
        # Recent swing lows = buy-side liquidity (stops below)
        recent_swings = [s for s in swings if s.index >= len(df) - lookback]

        for swing in recent_swings:
            if swing.is_high:
                pools.append(LiquidityPool(
                    timestamp=swing.timestamp,
                    price=swing.price,
                    type="sell_side",
                    strength=swing.strength,
                ))
            else:
                pools.append(LiquidityPool(
                    timestamp=swing.timestamp,
                    price=swing.price,
                    type="buy_side",
                    strength=swing.strength,
                ))

        self.liquidity_pools[symbol] = pools

    def _detect_breaker_blocks(self, symbol: str) -> None:
        """Detect breaker blocks (mitigated order blocks that flip)."""
        obs = self.order_blocks.get(symbol, [])
        breakers = []

        for ob in obs:
            if ob.mitigated and not any(b.timestamp == ob.timestamp for b in self.breaker_blocks.get(symbol, [])):
                # Mitigated OB becomes breaker block
                if ob.type == OrderBlockType.BULLISH_OB:
                    breaker = BreakerBlock(
                        timestamp=ob.mitigation_time or ob.timestamp,
                        top=ob.top,
                        bottom=ob.bottom,
                        direction="bullish",  # Now acts as support
                    )
                else:
                    breaker = BreakerBlock(
                        timestamp=ob.mitigation_time or ob.timestamp,
                        top=ob.top,
                        bottom=ob.bottom,
                        direction="bearish",  # Now acts as resistance
                    )
                breakers.append(breaker)

        self.breaker_blocks[symbol] = breakers

    def _cleanup_old_data(self, symbol: str, current_time: datetime) -> None:
        """Remove old/mitigated data."""
        max_age = pd.Timedelta(bars=self.params.max_ob_age_bars * 15, unit="min")

        # Clean order blocks
        obs = self.order_blocks.get(symbol, [])
        self.order_blocks[symbol] = [
            ob for ob in obs
            if not ob.mitigated or (current_time - ob.timestamp) < max_age
        ]

        # Clean FVGs
        fvgs = self.fair_value_gaps.get(symbol, [])
        self.fair_value_gaps[symbol] = [
            fvg for fvg in fvgs
            if not fvg.filled or (current_time - fvg.timestamp) < max_age
        ]

        # Clean liquidity
        pools = self.liquidity_pools.get(symbol, [])
        self.liquidity_pools[symbol] = [
            p for p in pools
            if not p.sweeped or (current_time - p.timestamp) < max_age
        ]

    def _check_bullish_setup(
        self,
        symbol: str,
        current_price: float,
        latest_bar: Any,
    ) -> TradingSignal | None:
        """Check for bullish entry setup."""
        # Need bullish structure (BOS or CHoCH)
        structure = self.market_structure.get(symbol, [])
        recent_structure = [
            s for s in structure
            if s.type in (MarketStructureType.BULLISH_BOS, MarketStructureType.BULLISH_CHoCH)
            and s.timestamp >= latest_bar.timestamp - pd.Timedelta(hours=24)
        ]

        if not recent_structure:
            return None

        # Find valid bullish order block
        obs = self.order_blocks.get(symbol, [])
        valid_obs = [
            ob for ob in obs
            if ob.type == OrderBlockType.BULLISH_OB
            and not ob.mitigated
            and ob.bottom <= current_price <= ob.top * 1.002  # Price at or near OB
        ]

        if not valid_obs:
            return None

        # Select best OB (closest to current price, strongest)
        best_ob = min(valid_obs, key=lambda ob: abs(ob.entry_price - current_price))

        # Check FVG confluence
        fvgs = self.fair_value_gaps.get(symbol, [])
        fvg_confluence = any(
            fvg.direction == "bullish" and not fvg.filled
            and fvg.bottom <= current_price <= fvg.top * 1.005
            for fvg in fvgs
        )

        # Check premium/discount
        if self.params.trade_premium_discount:
            # Simple: price should be in lower 50% of recent range
            df = self.market_data.get_bars(symbol, count=50)
            if not df.empty:
                recent_high = df["high"].max()
                recent_low = df["low"].min()
                midpoint = (recent_high + recent_low) / 2
                if current_price > midpoint:
                    return None  # In premium, don't buy

        # Calculate strength
        strength_factors = 0
        if fvg_confluence:
            strength_factors += 1
        if len(recent_structure) > 1:
            strength_factors += 1
        if any(bb.direction == "bullish" for bb in self.breaker_blocks.get(symbol, [])):
            strength_factors += 1

        strength = SignalStrength(strength_factors + 1)

        # Calculate stop loss and take profit
        stop_loss = best_ob.bottom * 0.998  # Just below OB
        risk = best_ob.entry_price - stop_loss
        take_profit = best_ob.entry_price + (risk * self.params.min_risk_reward)

        return TradingSignal(
            symbol=symbol,
            signal_type=SignalType.BUY,
            strength=strength,
            price=current_price,
            timestamp=datetime.now(),
            strategy_name=self.strategy_name,
            metadata={
                "order_block": {
                    "top": best_ob.top,
                    "bottom": best_ob.bottom,
                    "entry": best_ob.entry_price,
                },
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": self.params.min_risk_reward,
                "structure_type": recent_structure[-1].type.value,
                "fvg_confluence": fvg_confluence,
            },
        )

    def _check_bearish_setup(
        self,
        symbol: str,
        current_price: float,
        latest_bar: Any,
    ) -> TradingSignal | None:
        """Check for bearish entry setup."""
        # Need bearish structure
        structure = self.market_structure.get(symbol, [])
        recent_structure = [
            s for s in structure
            if s.type in (MarketStructureType.BEARISH_BOS, MarketStructureType.BEARISH_CHoCH)
            and s.timestamp >= latest_bar.timestamp - pd.Timedelta(hours=24)
        ]

        if not recent_structure:
            return None

        # Find valid bearish order block
        obs = self.order_blocks.get(symbol, [])
        valid_obs = [
            ob for ob in obs
            if ob.type == OrderBlockType.BEARISH_OB
            and not ob.mitigated
            and ob.bottom * 0.998 <= current_price <= ob.top  # Price at or near OB
        ]

        if not valid_obs:
            return None

        best_ob = min(valid_obs, key=lambda ob: abs(ob.entry_price - current_price))

        # Check FVG confluence
        fvgs = self.fair_value_gaps.get(symbol, [])
        fvg_confluence = any(
            fvg.direction == "bearish" and not fvg.filled
            and fvg.bottom * 0.995 <= current_price <= fvg.top
            for fvg in fvgs
        )

        # Check premium/discount
        if self.params.trade_premium_discount:
            df = self.market_data.get_bars(symbol, count=50)
            if not df.empty:
                recent_high = df["high"].max()
                recent_low = df["low"].min()
                midpoint = (recent_high + recent_low) / 2
                if current_price < midpoint:
                    return None  # In discount, don't sell

        strength_factors = 0
        if fvg_confluence:
            strength_factors += 1
        if len(recent_structure) > 1:
            strength_factors += 1
        if any(bb.direction == "bearish" for bb in self.breaker_blocks.get(symbol, [])):
            strength_factors += 1

        strength = SignalStrength(strength_factors + 1)

        stop_loss = best_ob.top * 1.002
        risk = stop_loss - best_ob.entry_price
        take_profit = best_ob.entry_price - (risk * self.params.min_risk_reward)

        return TradingSignal(
            symbol=symbol,
            signal_type=SignalType.SELL,
            strength=strength,
            price=current_price,
            timestamp=datetime.now(),
            strategy_name=self.strategy_name,
            metadata={
                "order_block": {
                    "top": best_ob.top,
                    "bottom": best_ob.bottom,
                    "entry": best_ob.entry_price,
                },
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": self.params.min_risk_reward,
                "structure_type": recent_structure[-1].type.value,
                "fvg_confluence": fvg_confluence,
            },
        )

    def calculate_position_size(
        self,
        symbol: str,
        signal: TradingSignal,
        account_equity: float,
        current_price: float,
    ) -> PositionSizing:
        """Calculate position size based on risk parameters."""
        risk_per_trade = self.params.risk_per_trade
        max_position = self.params.max_position_size

        # Get stop loss from signal metadata
        stop_loss = signal.metadata.get("stop_loss", current_price * 0.98)
        risk_per_share = abs(current_price - stop_loss)

        if risk_per_share <= 0:
            risk_per_share = current_price * 0.01

        # Risk-based sizing
        risk_amount = account_equity * risk_per_trade
        qty_by_risk = int(risk_amount / risk_per_share)

        # Max position sizing
        max_qty = int((account_equity * max_position) / current_price)

        # Use smaller of the two
        quantity = min(qty_by_risk, max_qty)
        quantity = max(1, quantity)  # At least 1 share

        return PositionSizing(
            symbol=symbol,
            quantity=quantity,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=signal.metadata.get("take_profit"),
            risk_amount=risk_amount,
            risk_pct=risk_per_trade,
            metadata={
                "method": "risk_based",
                "qty_by_risk": qty_by_risk,
                "max_qty": max_qty,
            },
        )

    def _on_bar_update(self, symbol: str, bar: Any) -> None:
        """Handle real-time bar updates - check for OB/FVG mitigation."""
        current_price = bar.close

        # Check order block mitigation
        for ob in self.order_blocks.get(symbol, []):
            if not ob.mitigated:
                if ob.type == OrderBlockType.BULLISH_OB and current_price <= ob.bottom:
                    ob.mitigated = True
                    ob.mitigation_time = bar.date
                    logger.info(f"Bullish OB mitigated for {symbol} at {current_price}")
                elif ob.type == OrderBlockType.BEARISH_OB and current_price >= ob.top:
                    ob.mitigated = True
                    ob.mitigation_time = bar.date
                    logger.info(f"Bearish OB mitigated for {symbol} at {current_price}")

        # Check FVG fill
        for fvg in self.fair_value_gaps.get(symbol, []):
            if not fvg.filled:
                if fvg.direction == "bullish" and current_price <= fvg.bottom:
                    fvg.filled = True
                    fvg.fill_time = bar.date
                elif fvg.direction == "bearish" and current_price >= fvg.top:
                    fvg.filled = True
                    fvg.fill_time = bar.date

        # Check liquidity sweeps
        for pool in self.liquidity_pools.get(symbol, []):
            if not pool.sweeped:
                if pool.type == "sell_side" and current_price >= pool.price:
                    pool.sweeped = True
                    pool.sweep_time = bar.date
                elif pool.type == "buy_side" and current_price <= pool.price:
                    pool.sweeped = True
                    pool.sweep_time = bar.date

    def get_smc_state(self, symbol: str) -> dict[str, Any]:
        """Get current SMC state for dashboard/logging."""
        return {
            "swings": len(self.swing_points.get(symbol, [])),
            "structure_events": len(self.market_structure.get(symbol, [])),
            "order_blocks": {
                "bullish": len([ob for ob in self.order_blocks.get(symbol, []) if ob.type == OrderBlockType.BULLISH_OB and not ob.mitigated]),
                "bearish": len([ob for ob in self.order_blocks.get(symbol, []) if ob.type == OrderBlockType.BEARISH_OB and not ob.mitigated]),
                "mitigated": len([ob for ob in self.order_blocks.get(symbol, []) if ob.mitigated]),
            },
            "fvg": {
                "bullish_open": len([f for f in self.fair_value_gaps.get(symbol, []) if f.direction == "bullish" and not f.filled]),
                "bearish_open": len([f for f in self.fair_value_gaps.get(symbol, []) if f.direction == "bearish" and not f.filled]),
                "filled": len([f for f in self.fair_value_gaps.get(symbol, []) if f.filled]),
            },
            "liquidity": {
                "buy_side": len([p for p in self.liquidity_pools.get(symbol, []) if p.type == "buy_side" and not p.sweeped]),
                "sell_side": len([p for p in self.liquidity_pools.get(symbol, []) if p.type == "sell_side" and not p.sweeped]),
            },
            "breaker_blocks": len(self.breaker_blocks.get(symbol, [])),
        }