"""Momentum Strategy using MACD and ADX."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

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


class MomentumParameters(StrategyParameters):
    """Momentum strategy parameters."""

    name: str = "momentum"

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # ADX
    adx_period: int = 14
    adx_threshold: float = 25.0

    # Trend confirmation
    ema_period: int = 50
    use_ema_filter: bool = True

    # Exit
    use_trailing_stop: bool = True
    trail_percent: float = 0.02


class MomentumStrategy(BaseStrategy):
    """Momentum strategy using MACD + ADX."""

    def __init__(
        self,
        parameters: MomentumParameters,
        market_data: MarketDataPipeline,
    ) -> None:
        super().__init__(parameters, market_data)
        self.params: MomentumParameters = parameters
        self.settings = get_settings()

    @property
    def strategy_name(self) -> str:
        return "momentum"

    async def generate_signals(self, symbol: str) -> list[TradingSignal]:
        """Generate momentum signals."""
        max_period = max(self.params.macd_slow, self.params.adx_period, self.params.ema_period)
        df = self.market_data.get_bars(symbol, count=max_period + 50)
        if df.empty or len(df) < max_period + 10:
            return []

        df = self._calculate_indicators(df)

        current_price = self.market_data.get_latest_price(symbol)
        if not current_price:
            return []

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        signals = []

        # MACD crossover
        macd_cross_up = prev["MACD"] <= prev["MACDs"] and latest["MACD"] > latest["MACDs"]
        macd_cross_down = prev["MACD"] >= prev["MACDs"] and latest["MACD"] < latest["MACDs"]

        # ADX trend strength
        strong_trend = latest["ADX"] >= self.params.adx_threshold

        # EMA filter
        in_uptrend = latest["close"] > latest.get(f"EMA_{self.params.ema_period}", latest["close"])
        in_downtrend = latest["close"] < latest.get(f"EMA_{self.params.ema_period}", latest["close"])

        # Long: MACD bullish cross + strong trend + uptrend
        if macd_cross_up and strong_trend and (in_uptrend or not self.params.use_ema_filter):
            strength = SignalStrength.STRONG if latest["ADX"] > 40 else SignalStrength.MODERATE

            # Trailing stop based on recent low
            recent_low = df["low"].tail(10).min()
            stop_loss = recent_low * 0.995

            signals.append(TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=strength,
                price=current_price,
                timestamp=datetime.now(),
                strategy_name=self.strategy_name,
                metadata={
                    "macd": latest["MACD"],
                    "macd_signal": latest["MACDs"],
                    "adx": latest["ADX"],
                    "stop_loss": stop_loss,
                    "trailing": self.params.use_trailing_stop,
                    "trail_percent": self.params.trail_percent,
                },
            ))

        # Short: MACD bearish cross + strong trend + downtrend
        elif macd_cross_down and strong_trend and (in_downtrend or not self.params.use_ema_filter):
            strength = SignalStrength.STRONG if latest["ADX"] > 40 else SignalStrength.MODERATE

            recent_high = df["high"].tail(10).max()
            stop_loss = recent_high * 1.005

            signals.append(TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=strength,
                price=current_price,
                timestamp=datetime.now(),
                strategy_name=self.strategy_name,
                metadata={
                    "macd": latest["MACD"],
                    "macd_signal": latest["MACDs"],
                    "adx": latest["ADX"],
                    "stop_loss": stop_loss,
                    "trailing": self.params.use_trailing_stop,
                    "trail_percent": self.params.trail_percent,
                },
            ))

        return signals

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators using pandas built-in functions."""
        df = df.copy()

        # MACD
        fast = self.params.macd_fast
        slow = self.params.macd_slow
        signal = self.params.macd_signal

        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        df["MACD"] = ema_fast - ema_slow
        df["MACDs"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACDh"] = df["MACD"] - df["MACDs"]

        # ADX (Average Directional Index)
        period = self.params.adx_period

        # True Range
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        # Directional Movement
        up_move = df["high"] - df["high"].shift()
        down_move = df["low"].shift() - df["low"]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        # Smoothed TR, +DM, -DM using Wilder's smoothing (EMA with alpha=1/period)
        alpha = 1 / period
        atr = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr

        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        df["ADX"] = dx.ewm(alpha=alpha, adjust=False).mean()
        df["DMP"] = plus_di
        df["DMN"] = minus_di

        # EMA filter
        if self.params.use_ema_filter:
            df[f"EMA_{self.params.ema_period}"] = df["close"].ewm(span=self.params.ema_period, adjust=False).mean()

        return df

    def calculate_position_size(
        self,
        symbol: str,
        signal: TradingSignal,
        account_equity: float,
        current_price: float,
    ) -> PositionSizing:
        """Calculate position size."""
        stop_loss = signal.metadata.get("stop_loss", current_price * 0.98)
        risk_per_share = abs(current_price - stop_loss)

        if risk_per_share <= 0:
            risk_per_share = current_price * 0.01

        risk_amount = account_equity * self.params.risk_per_trade
        qty_by_risk = int(risk_amount / risk_per_share)
        max_qty = int((account_equity * self.params.max_position_size) / current_price)

        quantity = max(1, min(qty_by_risk, max_qty))

        return PositionSizing(
            symbol=symbol,
            quantity=quantity,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=signal.metadata.get("take_profit"),
            risk_amount=risk_amount,
            risk_pct=self.params.risk_per_trade,
        )