"""Risk management module for position sizing and portfolio protection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from src.config.settings import get_settings

if TYPE_CHECKING:
    from src.ib.connection import IBConnectionManager
    from src.strategy.base import PositionSizing, TradingSignal


@dataclass
class RiskMetrics:
    """Current risk metrics."""

    total_exposure: float = 0.0
    sector_exposure: dict[str, float] = field(default_factory=dict)
    correlated_exposure: dict[str, float] = field(default_factory=dict)
    daily_pnl: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    open_positions: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PositionRisk:
    """Risk analysis for a single position."""

    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: float | None
    take_profit: float | None
    risk_amount: float
    risk_pct_of_equity: float
    days_held: int


class RiskManager:
    """Manages portfolio risk, position sizing, and drawdown protection."""

    def __init__(self, ib_manager: IBConnectionManager) -> None:
        self.ib = ib_manager
        self.settings = get_settings()

        # Risk state
        self.daily_start_equity: float | None = None
        self.peak_equity: float = 0.0
        self.daily_pnl_history: list[float] = []
        self.trade_history: list[dict] = []

        # Position tracking
        self.positions: dict[str, PositionRisk] = {}

    async def initialize(self) -> None:
        """Initialize risk manager with current account state."""
        await self._update_account_state()
        self.daily_start_equity = await self._get_equity()
        self.peak_equity = self.daily_start_equity

    async def _update_account_state(self) -> None:
        """Update positions and account metrics from IB."""
        positions = await self.ib.get_positions()
        account_summary = await self.ib.get_account_summary()

        # Update equity
        equity = float(account_summary.get("NetLiquidation", 0))
        if equity > 0:
            if self.peak_equity == 0 or equity > self.peak_equity:
                self.peak_equity = equity

        # Update positions
        self.positions = {}
        for pos in positions:
            if pos.position != 0:
                # Get current price (would need market data)
                current_price = pos.avgCost  # Placeholder
                self.positions[pos.contract.symbol] = PositionRisk(
                    symbol=pos.contract.symbol,
                    quantity=pos.position,
                    entry_price=pos.avgCost,
                    current_price=current_price,
                    market_value=abs(pos.position) * current_price,
                    unrealized_pnl=0,  # Would calculate from market data
                    unrealized_pnl_pct=0,
                    stop_loss=None,
                    take_profit=None,
                    risk_amount=0,
                    risk_pct_of_equity=0,
                    days_held=0,
                )

    async def _get_equity(self) -> float:
        """Get current account equity."""
        summary = await self.ib.get_account_summary()
        return float(summary.get("NetLiquidation", 0))

    def check_pre_trade_risk(
        self,
        signal: TradingSignal,
        position_sizing: PositionSizing,
    ) -> tuple[bool, str]:
        """Check if a new trade passes risk checks."""

        # 1. Check daily drawdown limit
        if self.daily_start_equity:
            current_equity = self.peak_equity  # Approximate
            drawdown = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0
            if drawdown >= self.settings.MAX_DRAWDOWN:
                return False, f"Daily drawdown limit exceeded: {drawdown:.2%}"

        # 2. Check max position size
        if position_sizing.risk_pct > self.settings.MAX_POSITION_SIZE:
            return False, f"Position size {position_sizing.risk_pct:.2%} exceeds max {self.settings.MAX_POSITION_SIZE:.2%}"

        # 3. Check sector exposure (would need sector mapping)
        # 4. Check correlated exposure

        # 5. Check max open positions
        if len(self.positions) >= 10:  # Configurable
            return False, "Max open positions reached"

        return True, "OK"

    def calculate_kelly_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        equity: float,
    ) -> float:
        """Calculate Kelly criterion position size."""
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        # Kelly fraction = (bp - q) / b
        # where b = avg_win/avg_loss, p = win_rate, q = 1-win_rate
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - win_rate

        kelly = (b * p - q) / b
        kelly = max(0, min(kelly, 1))  # Clamp to [0, 1]

        # Apply fractional Kelly
        return kelly * self.settings.KELLY_FRACTION * equity

    def calculate_volatility_adjusted_size(
        self,
        symbol: str,
        equity: float,
        atr: float,
        current_price: float,
    ) -> int:
        """Calculate position size adjusted for volatility."""
        # Risk 1% of equity per trade, adjusted for volatility
        risk_per_trade = equity * self.settings.RISK_PER_TRADE

        # ATR-based stop distance
        stop_distance = atr * 2  # 2 ATR stop

        if stop_distance <= 0:
            return 0

        # Position size = Risk / Stop Distance
        shares = risk_per_trade / stop_distance

        # Apply max position limit
        max_shares = (equity * self.settings.MAX_POSITION_SIZE) / current_price

        return int(min(shares, max_shares))

    def update_daily_pnl(self, pnl: float) -> None:
        """Update daily P&L tracking."""
        self.daily_pnl_history.append(pnl)

        # Keep last 30 days
        if len(self.daily_pnl_history) > 30:
            self.daily_pnl_history = self.daily_pnl_history[-30:]

    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: int,
        side: str,  # "long" or "short"
    ) -> None:
        """Record completed trade for statistics."""
        if side == "long":
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity

        self.trade_history.append({
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "side": side,
            "pnl": pnl,
            "timestamp": datetime.now(),
        })

        # Keep last 1000 trades
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]

    def get_risk_metrics(self) -> RiskMetrics:
        """Calculate current risk metrics."""
        if not self.trade_history:
            return RiskMetrics()

        pnls = [t["pnl"] for t in self.trade_history]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0
        profit_factor = sum(wins) / sum(losses) if losses else float('inf')

        # Daily P&L
        today = datetime.now().date()
        daily_pnl = sum(
            t["pnl"] for t in self.trade_history
            if t["timestamp"].date() == today
        )

        # Sharpe ratio (simplified)
        if len(pnls) > 1:
            sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0
        else:
            sharpe = 0

        # Current drawdown
        current_equity = self.peak_equity + sum(pnls[-10:]) if self.trade_history else self.peak_equity
        current_drawdown = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0

        return RiskMetrics(
            total_exposure=sum(p.market_value for p in self.positions.values()),
            sector_exposure={},  # Would need sector data
            correlated_exposure={},
            daily_pnl=daily_pnl,
            max_drawdown=max(current_drawdown, 0),
            current_drawdown=current_drawdown,
            open_positions=len(self.positions),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe,
        )

    def should_reduce_risk(self) -> tuple[bool, str]:
        """Check if risk should be reduced (drawdown protection)."""
        metrics = self.get_risk_metrics()

        # Reduce risk if drawdown > 3%
        if metrics.current_drawdown > 0.03:
            return True, f"Drawdown {metrics.current_drawdown:.2%} exceeds 3%"

        # Reduce risk if daily loss > 2%
        if self.daily_start_equity and metrics.daily_pnl < -self.daily_start_equity * 0.02:
            return True, f"Daily loss {metrics.daily_pnl:.2f} exceeds 2%"

        # Reduce risk if losing streak
        recent_trades = self.trade_history[-5:] if len(self.trade_history) >= 5 else self.trade_history
        if recent_trades and all(t["pnl"] < 0 for t in recent_trades):
            return True, "5 consecutive losing trades"

        return False, "OK"

    def get_position_sizing_recommendation(
        self,
        signal: TradingSignal,
        equity: float,
        atr: float | None = None,
    ) -> PositionSizing:
        """Get comprehensive position sizing recommendation."""
        current_price = signal.price

        # Base risk amount
        risk_amount = equity * self.settings.RISK_PER_TRADE

        # Use signal's stop loss if available
        stop_loss = signal.metadata.get("stop_loss")
        if not stop_loss and atr:
            # ATR-based stop
            if signal.signal_type.value in ("buy",):
                stop_loss = current_price - (atr * 2)
            else:
                stop_loss = current_price + (atr * 2)
        elif not stop_loss:
            # Percentage-based stop
            stop_pct = self.settings.STOP_LOSS_PCT
            if signal.signal_type.value in ("buy",):
                stop_loss = current_price * (1 - stop_pct)
            else:
                stop_loss = current_price * (1 + stop_pct)

        risk_per_share = abs(current_price - stop_loss)
        if risk_per_share <= 0:
            risk_per_share = current_price * 0.01

        # Risk-based quantity
        qty_by_risk = int(risk_amount / risk_per_share)

        # Volatility-adjusted if ATR available
        if atr:
            qty_by_vol = self.calculate_volatility_adjusted_size(
                signal.symbol, equity, atr, current_price
            )
            qty_by_risk = min(qty_by_risk, qty_by_vol)

        # Max position limit
        max_qty = int((equity * self.settings.MAX_POSITION_SIZE) / current_price)

        quantity = max(1, min(qty_by_risk, max_qty))

        # Take profit
        take_profit = signal.metadata.get("take_profit")
        if not take_profit:
            risk = current_price - stop_loss if signal.signal_type.value == "buy" else stop_loss - current_price
            reward = risk * 2  # 2:1 reward:risk
            if signal.signal_type.value == "buy":
                take_profit = current_price + reward
            else:
                take_profit = current_price - reward

        return PositionSizing(
            symbol=signal.symbol,
            quantity=quantity,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_amount=risk_amount,
            risk_pct=self.settings.RISK_PER_TRADE,
            metadata={
                "method": "comprehensive",
                "qty_by_risk": qty_by_risk,
                "max_qty": max_qty,
                "atr": atr,
            },
        )