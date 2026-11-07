"""Market data pipeline for handling 15-min delayed data."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd
from ib_insync import BarData, Contract
from loguru import logger

from src.config.settings import get_settings
from src.ib.connection import IBConnectionManager

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class MarketDataSnapshot:
    """Snapshot of market data for a symbol."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    wap: float | None = None
    trade_count: int | None = None


@dataclass
class SymbolData:
    """Container for symbol market data."""

    contract: Contract
    bars: list[BarData] = field(default_factory=list)
    realtime_bars: list[BarData] = field(default_factory=list)
    last_update: datetime | None = None
    subscribers: set[Callable] = field(default_factory=set)


class MarketDataPipeline:
    """
    Handles market data ingestion with 15-minute delay compensation.

    Competition uses 15-minute delayed data. This pipeline:
    1. Fetches historical data on startup
    2. Subscribes to real-time (delayed) data
    3. Maintains rolling buffers for strategy consumption
    4. Provides delayed timestamp alignment
    """

    def __init__(self, ib_manager: IBConnectionManager) -> None:
        self.ib = ib_manager
        self.settings = get_settings()
        self.symbols: dict[str, SymbolData] = {}
        self._running = False
        self._update_tasks: dict[str, asyncio.Task] = {}
        self._delay_buffer: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def initialize(self, symbols: list[str] | None = None) -> None:
        """Initialize market data for symbols."""
        symbols = symbols or self.settings.get_symbols_list()[: self.settings.MAX_SYMBOLS]
        logger.info(f"Initializing market data for {len(symbols)} symbols")

        # Create contracts
        contracts = []
        for symbol in symbols:
            from ib_insync import Stock
            contract = Stock(symbol, "SMART", "USD")
            contracts.append(contract)

        # Qualify contracts
        qualified = await self.ib.qualify_contracts(*contracts)

        # Fetch historical data for each
        for contract in qualified:
            symbol = contract.symbol
            self.symbols[symbol] = SymbolData(contract=contract)
            await self._fetch_historical_data(symbol)

        # Start real-time subscriptions
        for symbol in self.symbols:
            await self._subscribe_realtime(symbol)

        self._running = True
        logger.info("Market data pipeline initialized")

    async def _fetch_historical_data(self, symbol: str) -> None:
        """Fetch historical bars for a symbol."""
        symbol_data = self.symbols[symbol]
        contract = symbol_data.contract

        duration = f"{self.settings.LOOKBACK_DAYS} D"
        bar_size = self.settings.DEFAULT_TIMEFRAME

        logger.debug(f"Fetching historical data for {symbol}: {duration} @ {bar_size}")

        try:
            bars = await self.ib.get_historical_data(
                contract=contract,
                duration=duration,
                bar_size=bar_size,
                what_to_show="TRADES",
                use_rth=True,
            )

            if bars:
                symbol_data.bars = bars
                symbol_data.last_update = bars[-1].date
                logger.info(f"Loaded {len(bars)} historical bars for {symbol}")
            else:
                logger.warning(f"No historical data for {symbol}")

        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")

    async def _subscribe_realtime(self, symbol: str) -> None:
        """Subscribe to real-time (delayed) market data."""
        symbol_data = self.symbols[symbol]
        contract = symbol_data.contract

        # Request delayed market data
        await self.ib.subscribe_market_data(contract)

        # Start bar aggregation task
        task = asyncio.create_task(self._aggregate_realtime_bars(symbol))
        self._update_tasks[symbol] = task

        logger.debug(f"Subscribed to real-time data for {symbol}")

    async def _aggregate_realtime_bars(self, symbol: str) -> None:
        """Aggregate real-time ticks into 15-min bars."""
        symbol_data = self.symbols[symbol]
        contract = symbol_data.contract

        # Get the ticker for this contract
        ticker = self.ib.ib.ticker(contract)
        if not ticker:
            logger.warning(f"No ticker found for {symbol}")
            return

        current_bar: BarData | None = None
        bar_start: datetime | None = None
        bar_size_minutes = 15

        while self._running:
            try:
                await asyncio.sleep(1)

                # Get latest price
                if ticker.last and ticker.last > 0:
                    now = datetime.now()
                    price = ticker.last
                    volume = ticker.volume or 0

                    # Determine bar start time (15-min aligned)
                    minute = (now.minute // bar_size_minutes) * bar_size_minutes
                    this_bar_start = now.replace(minute=minute, second=0, microsecond=0)

                    if bar_start is None or this_bar_start != bar_start:
                        # Save previous bar
                        if current_bar is not None:
                            current_bar.volume = volume
                            symbol_data.realtime_bars.append(current_bar)
                            # Keep only recent bars
                            if len(symbol_data.realtime_bars) > 100:
                                symbol_data.realtime_bars = symbol_data.realtime_bars[-100:]
                            symbol_data.last_update = current_bar.date

                            # Notify subscribers
                            await self._notify_subscribers(symbol, current_bar)

                        # Start new bar
                        bar_start = this_bar_start
                        current_bar = BarData(
                            date=bar_start,
                            open=price,
                            high=price,
                            low=price,
                            close=price,
                            volume=0,
                            barCount=0,
                            wap=price,
                        )
                    else:
                        # Update current bar
                        if current_bar:
                            current_bar.high = max(current_bar.high, price)
                            current_bar.low = min(current_bar.low, price)
                            current_bar.close = price
                            current_bar.volume = volume
                            current_bar.wap = (
                                (current_bar.wap * (current_bar.barCount - 1) + price)
                                / current_bar.barCount
                                if current_bar.barCount > 0
                                else price
                            )
                            current_bar.barCount += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error aggregating bars for {symbol}: {e}")
                await asyncio.sleep(5)

    async def _notify_subscribers(self, symbol: str, bar: BarData) -> None:
        """Notify subscribers of new bar."""
        symbol_data = self.symbols[symbol]
        for callback in symbol_data.subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(symbol, bar)
                else:
                    callback(symbol, bar)
            except Exception as e:
                logger.error(f"Subscriber error for {symbol}: {e}")

    def subscribe(self, symbol: str, callback: Callable) -> None:
        """Subscribe to bar updates for a symbol."""
        if symbol in self.symbols:
            self.symbols[symbol].subscribers.add(callback)

    def unsubscribe(self, symbol: str, callback: Callable) -> None:
        """Unsubscribe from bar updates."""
        if symbol in self.symbols:
            self.symbols[symbol].subscribers.discard(callback)

    def get_bars(self, symbol: str, count: int | None = None) -> pd.DataFrame:
        """Get combined historical + realtime bars as DataFrame."""
        if symbol not in self.symbols:
            return pd.DataFrame()

        symbol_data = self.symbols[symbol]
        all_bars = symbol_data.bars + symbol_data.realtime_bars

        if not all_bars:
            return pd.DataFrame()

        df = pd.DataFrame([{
            "timestamp": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "wap": bar.wap,
        } for bar in all_bars])

        df = df.sort_values("timestamp").drop_duplicates(subset="timestamp", keep="last")
        df.set_index("timestamp", inplace=True)

        if count:
            df = df.tail(count)

        return df

    def get_latest_bar(self, symbol: str) -> BarData | None:
        """Get the most recent completed bar."""
        if symbol not in self.symbols:
            return None

        symbol_data = self.symbols[symbol]
        all_bars = symbol_data.bars + symbol_data.realtime_bars

        if not all_bars:
            return None

        return all_bars[-1]

    def get_latest_price(self, symbol: str) -> float | None:
        """Get latest price from ticker."""
        if symbol not in self.symbols:
            return None

        contract = self.symbols[symbol].contract
        ticker = self.ib.ib.ticker(contract)
        if ticker and ticker.last:
            return ticker.last
        return None

    async def shutdown(self) -> None:
        """Shutdown market data pipeline."""
        self._running = False

        # Cancel update tasks
        for task in self._update_tasks.values():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Unsubscribe from market data
        for symbol_data in self.symbols.values():
            await self.ib.unsubscribe_market_data(symbol_data.contract)

        logger.info("Market data pipeline shutdown complete")

    def get_status(self) -> dict[str, Any]:
        """Get pipeline status."""
        return {
            "running": self._running,
            "symbols": {
                symbol: {
                    "historical_bars": len(data.bars),
                    "realtime_bars": len(data.realtime_bars),
                    "last_update": data.last_update.isoformat() if data.last_update else None,
                    "subscribers": len(data.subscribers),
                }
                for symbol, data in self.symbols.items()
            },
        }


# Import contextlib for shutdown
import contextlib