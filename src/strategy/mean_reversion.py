"""Mean Reversion Strategy using Bollinger Bands and RSI."""

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


class MeanReversionParameters(StrategyParameters):
    """Mean reversion strategy parameters."""

    name: str = "mean_reversion"

    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0

    # RSI
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

    # Trend filter
    trend_period: int = 200
    use_trend_filter: bool = True

    # Exit
    exit_at_middle: bool = True
    middle_band_exit: bool = True


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands + RSI."""

    def __init__(
        self,
        parameters: MeanReversionParameters,
        market_data: MarketDataPipeline,
    ) -> None:
        super().__init__(parameters, market_data)
        self.params: MeanReversionParameters = parameters
        self.settings = get_settings()

    @property
    def strategy_name(self) -> str:
        return "mean_reversion"

    async def generate_signals(self, symbol: str) -> list[TradingSignal]:
        """Generate mean reversion signals."""
        df = self.market_data.get_bars(symbol, count=max(self.params.bb_period, self.params.rsi_period) + 50)
        if df.empty or len(df) < self.params.bb_period + 10:
            return []

        # Calculate indicators
        df = self._calculate_indicators(df)

        current_price = self.market_data.get_latest_price(symbol)
        if not current_price:
            return []

        latest = df.iloc[-1]
        signals = []

        # Trend filter
        in_uptrend = True
        if self.params.use_trend_filter:
            sma_col = f"SMA_{self.params.trend_period}"
            in_uptrend = latest["close"] > latest.get(sma_col, latest["close"])

        # Long signal: Price at lower band + RSI oversold + (uptrend or no filter)
        if (latest["close"] <= latest["BBL"] and
            latest["RSI"] <= self.params.rsi_oversold and
            (in_uptrend or not self.params.use_trend_filter)):

            strength = SignalStrength.MODERATE
            if latest["RSI"] < 25:
                strength = SignalStrength.STRONG

            signals.append(TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=strength,
                price=current_price,
                timestamp=datetime.now(),
                strategy_name=self.strategy_name,
                metadata={
                    "bb_lower": latest["BBL"],
                    "bb_middle": latest["BBM"],
                    "bb_upper": latest["BBU"],
                    "rsi": latest["RSI"],
                    "stop_loss": latest["BBL"] * 0.995,
                    "take_profit": latest["BBM"] if self.params.exit_at_middle else latest["BBU"],
                },
            ))

        # Short signal: Price at upper band + RSI overbought + (downtrend or no filter)
        elif (latest["close"] >= latest["BBU"] and
              latest["RSI"] >= self.params.rsi_overbought and
              (not in_uptrend or not self.params.use_trend_filter)):

            strength = SignalStrength.MODERATE
            if latest["RSI"] > 75:
                strength = SignalStrength.STRONG

            signals.append(TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=strength,
                price=current_price,
                timestamp=datetime.now(),
                strategy_name=self.strategy_name,
                metadata={
                    "bb_lower": latest["BBL"],
                    "bb_middle": latest["BBM"],
                    "bb_upper": latest["BBU"],
                    "rsi": latest["RSI"],
                    "stop_loss": latest["BBU"] * 1.005,
                    "take_profit": latest["BBM"] if self.params.exit_at_middle else latest["BBL"],
                },
            ))

        return signals

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators using pandas built-in functions."""
        df = df.copy()

        # Bollinger Bands
        period = self.params.bb_period
        std = self.params.bb_std
        df["SMA"] = df["close"].rolling(window=period).mean()
        df["STD"] = df["close"].rolling(window=period).std()
        df["BBL"] = df["SMA"] - (df["STD"] * std)  # Lower band
        df["BBM"] = df["SMA"]                      # Middle band
        df["BBU"] = df["SMA"] + (df["STD"] * std)  # Upper band

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.params.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params.rsi_period).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))

        # Trend filter
        if self.params.use_trend_filter:
            df[f"SMA_{self.params.trend_period}"] = df["close"].rolling(window=self.params.trend_period).mean()

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