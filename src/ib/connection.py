"""Interactive Brokers connection management with auto-reconnection."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ib_insync import IB, ConnectionStats
from loguru import logger

from src.config.settings import get_settings

if TYPE_CHECKING:
    from ib_insync import Contract, Order, Trade


@dataclass
class ConnectionState:
    """Tracks IB connection state."""

    connected: bool = False
    last_connected: datetime | None = None
    last_disconnected: datetime | None = None
    reconnect_attempts: int = 0
    last_error: str | None = None
    stats: ConnectionStats | None = None


class IBConnectionManager:
    """Manages IB connection with automatic reconnection and health monitoring."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.ib = IB()
        self.state = ConnectionState()
        self._reconnect_task: asyncio.Task | None = None
        self._health_check_task: asyncio.Task | None = None
        self._connected_event = asyncio.Event()
        self._shutdown = False
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        """Set up IB event callbacks."""

        def on_connected() -> None:
            self.state.connected = True
            self.state.last_connected = datetime.now()
            self.state.reconnect_attempts = 0
            self.state.last_error = None
            self._connected_event.set()
            logger.info("IB connected successfully")

        def on_disconnected() -> None:
            self.state.connected = False
            self.state.last_disconnected = datetime.now()
            self._connected_event.clear()
            logger.warning("IB disconnected")

        def on_error(req_id: int, error_code: int, error_string: str, contract: Any) -> None:
            self.state.last_error = f"ReqId={req_id}, Code={error_code}: {error_string}"
            logger.error(f"IB Error {error_code}: {error_string}")

        def on_connection_stats(stats: ConnectionStats) -> None:
            self.state.stats = stats

        self.ib.connectedEvent += on_connected
        self.ib.disconnectedEvent += on_disconnected
        self.ib.errorEvent += on_error
        self.ib.connectionStatsEvent += on_connection_stats

    async def connect(self) -> bool:
        """Connect to IB Gateway/TWS with retry logic."""
        if self.state.connected:
            logger.debug("Already connected to IB")
            return True

        self._shutdown = False
        max_attempts = 10
        base_delay = 2

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to IB at {self.settings.IB_HOST}:{self.settings.IB_PORT} (attempt {attempt}/{max_attempts})")

                await asyncio.wait_for(
                    self.ib.connectAsync(
                        host=self.settings.IB_HOST,
                        port=self.settings.IB_PORT,
                        clientId=self.settings.IB_CLIENT_ID,
                        readonly=self.settings.IB_READONLY,
                        timeout=self.settings.IB_TIMEOUT,
                    ),
                    timeout=self.settings.IB_TIMEOUT,
                )

                # Verify connection with a simple request
                await self.ib.reqCurrentTimeAsync()
                logger.info("IB connection verified")
                return True

            except asyncio.TimeoutError:
                self.state.last_error = f"Connection timeout (attempt {attempt})"
                logger.warning(self.state.last_error)

            except Exception as e:
                self.state.last_error = f"Connection failed: {e}"
                logger.warning(self.state.last_error)

            self.state.reconnect_attempts = attempt

            if attempt < max_attempts and not self._shutdown:
                delay = min(base_delay * (2 ** (attempt - 1)), 60)
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

        logger.error("Failed to connect to IB after all attempts")
        return False

    async def disconnect(self) -> None:
        """Disconnect from IB gracefully."""
        self._shutdown = True

        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self._health_check_task:
            self._health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task

        if self.state.connected:
            self.ib.disconnect()
            logger.info("Disconnected from IB")

    async def ensure_connected(self) -> bool:
        """Ensure connection is active, reconnect if needed."""
        if not self.state.connected:
            logger.warning("Connection lost, attempting to reconnect...")
            return await self.connect()
        return True

    async def start_reconnect_loop(self) -> None:
        """Start background reconnection monitoring."""
        if self._reconnect_task and not self._reconnect_task.done():
            return

        async def reconnect_monitor() -> None:
            while not self._shutdown:
                await asyncio.sleep(self.settings.HEALTH_CHECK_INTERVAL)
                if self._shutdown:
                    break

                if not self.state.connected:
                    logger.warning("Connection lost detected, reconnecting...")
                    await self.connect()

        self._reconnect_task = asyncio.create_task(reconnect_monitor())
        logger.debug("Reconnection monitor started")

    async def start_health_check(self) -> None:
        """Start periodic health checks."""
        if self._health_check_task and not self._health_check_task.done():
            return

        async def health_monitor() -> None:
            while not self._shutdown:
                await asyncio.sleep(self.settings.HEALTH_CHECK_INTERVAL)
                if self._shutdown:
                    break

                if self.state.connected:
                    try:
                        await asyncio.wait_for(
                            self.ib.reqCurrentTimeAsync(),
                            timeout=5.0,
                        )
                    except Exception as e:
                        logger.error(f"Health check failed: {e}")
                        self.state.last_error = f"Health check failed: {e}"

        self._health_check_task = asyncio.create_task(health_monitor())
        logger.debug("Health check monitor started")

    async def wait_connected(self, timeout: float = 30.0) -> bool:
        """Wait for connection to be established."""
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # =========================================================================
    # Market Data Methods
    # =========================================================================

    async def qualify_contracts(self, *contracts: Contract) -> list[Contract]:
        """Qualify contracts (resolve conIds, etc.)."""
        await self.ensure_connected()
        return await self.ib.qualifyContractsAsync(*contracts)

    async def get_historical_data(
        self,
        contract: Contract,
        duration: str = "30 D",
        bar_size: str = "15 mins",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        format_date: int = 1,
    ) -> list:
        """Get historical bars."""
        await self.ensure_connected()
        bars = await self.ib.reqHistoricalDataAsync(
            contract=contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=format_date,
            keepUpToDate=False,
        )
        return bars

    async def subscribe_market_data(
        self,
        contract: Contract,
        generic_tick_list: str = "",
        snapshot: bool = False,
        regulatory_snapshot: bool = False,
    ) -> None:
        """Subscribe to real-time market data (with 15-min delay in competition)."""
        await self.ensure_connected()
        self.ib.reqMktData(
            contract=contract,
            genericTickList=generic_tick_list,
            snapshot=snapshot,
            regulatorySnapshot=regulatory_snapshot,
        )

    async def unsubscribe_market_data(self, contract: Contract) -> None:
        """Unsubscribe from market data."""
        self.ib.cancelMktData(contract)

    # =========================================================================
    # Account & Portfolio Methods
    # =========================================================================

    async def get_account_summary(self) -> dict:
        """Get account summary."""
        await self.ensure_connected()
        summary = await self.ib.accountSummaryAsync()
        return {item.tag: item.value for item in summary}

    async def get_positions(self) -> list:
        """Get current positions."""
        await self.ensure_connected()
        return await self.ib.reqPositionsAsync()

    async def get_pnl(self) -> dict:
        """Get P&L for all positions."""
        await self.ensure_connected()
        pnls = await self.ib.reqPnLAsync()
        return {pnl.account: pnl for pnl in pnls}

    # =========================================================================
    # Order Methods
    # =========================================================================

    async def place_order(self, contract: Contract, order: Order) -> Trade:
        """Place an order."""
        await self.ensure_connected()
        trade = self.ib.placeOrder(contract, order)
        return trade

    async def cancel_order(self, trade: Trade) -> None:
        """Cancel an order."""
        await self.ensure_connected()
        self.ib.cancelOrder(trade.order)

    async def get_open_orders(self) -> list[Trade]:
        """Get all open orders."""
        await self.ensure_connected()
        return self.ib.openOrders()

    async def get_executions(self) -> list:
        """Get executions."""
        await self.ensure_connected()
        return await self.ib.reqExecutionsAsync()

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_connection_stats(self) -> dict[str, Any]:
        """Get connection statistics."""
        stats = self.state.stats
        return {
            "connected": self.state.connected,
            "last_connected": self.state.last_connected.isoformat() if self.state.last_connected else None,
            "last_disconnected": self.state.last_disconnected.isoformat() if self.state.last_disconnected else None,
            "reconnect_attempts": self.state.reconnect_attempts,
            "last_error": self.state.last_error,
            "server_version": stats.serverVersion if stats else None,
            "server_time": stats.serverTime.isoformat() if stats and stats.serverTime else None,
            "queue_size": stats.queueSize if stats else None,
            "msg_rate": stats.msgRate if stats else None,
        }

    @property
    def ib_client(self) -> IB:
        """Get raw IB client for advanced usage."""
        return self.ib


class IBConnectionContext:
    """Async context manager for IB connection lifecycle."""

    def __init__(self) -> None:
        self.manager = IBConnectionManager()

    async def __aenter__(self) -> IBConnectionManager:
        connected = await self.manager.connect()
        if not connected:
            raise ConnectionError("Failed to connect to IB")
        await self.manager.start_reconnect_loop()
        await self.manager.start_health_check()
        return self.manager

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.manager.disconnect()


async def get_ib_connection() -> AsyncGenerator[IBConnectionManager, None]:
    """FastAPI dependency for IB connection."""
    manager = IBConnectionManager()
    try:
        connected = await manager.connect()
        if not connected:
            raise ConnectionError("Failed to connect to IB")
        await manager.start_reconnect_loop()
        await manager.start_health_check()
        yield manager
    finally:
        await manager.disconnect()