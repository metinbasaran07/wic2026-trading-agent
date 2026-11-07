"""Main entry point and CLI for the trading workstation."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import click
import uvicorn
from loguru import logger

from src.config.settings import get_settings, settings

if TYPE_CHECKING:
    from src.dashboard.app import app as dashboard_app
    from src.ib.connection import IBConnectionManager
    from src.ib.market_data import MarketDataPipeline
    from src.llm.reviewer import LLMStrategyReviewer
    from src.risk.manager import RiskManager
    from src.strategy.base import StrategyRegistry, strategy_registry
    from src.strategy.mean_reversion import MeanReversionStrategy, MeanReversionParameters
    from src.strategy.momentum import MomentumStrategy, MomentumParameters
    from src.strategy.smc import SMCStrategy, SMCParameters


# Global components
ib_manager: IBConnectionManager | None = None
market_data: MarketDataPipeline | None = None
risk_manager: RiskManager | None = None
llm_reviewer: LLMStrategyReviewer | None = None
dashboard_task: asyncio.Task | None = None
_shutdown = False


@asynccontextmanager
async def lifespan():
    """Application lifespan manager."""
    global ib_manager, market_data, risk_manager, llm_reviewer, dashboard_task

    logger.info(f"Starting WIC 2026 Trading Agent in {settings.MODE} mode")

    # Initialize components
    await initialize_components()

    # Start dashboard if enabled
    if settings.DASHBOARD_ENABLED:
        dashboard_task = asyncio.create_task(run_dashboard())

    try:
        yield
    finally:
        logger.info("Shutting down...")
        await shutdown_components()


async def initialize_components() -> None:
    """Initialize all system components."""
    global ib_manager, market_data, risk_manager, llm_reviewer

    # Import here to avoid circular imports
    from src.compliance.change_tracker import ChangeTracker
    from src.compliance.logger import get_operation_logger
    from src.compliance.report_generator import get_report_generator
    from src.ib.connection import IBConnectionManager
    from src.ib.market_data import MarketDataPipeline
    from src.llm.reviewer import LLMStrategyReviewer
    from src.risk.manager import RiskManager
    from src.strategy.base import strategy_registry
    from src.strategy.mean_reversion import MeanReversionStrategy, MeanReversionParameters
    from src.strategy.momentum import MomentumStrategy, MomentumParameters
    from src.strategy.smc import SMCStrategy, SMCParameters

    # Initialize IB connection
    ib_manager = IBConnectionManager()
    connected = await ib_manager.connect()
    if not connected:
        raise RuntimeError("Failed to connect to IB")

    await ib_manager.start_reconnect_loop()
    await ib_manager.start_health_check()

    # Initialize market data
    market_data = MarketDataPipeline(ib_manager)
    await market_data.initialize()

    # Initialize risk manager
    risk_manager = RiskManager(ib_manager)
    await risk_manager.initialize()

    # Initialize strategies
    await initialize_strategies()

    # Initialize compliance
    operation_logger = get_operation_logger()
    change_tracker = ChangeTracker(operation_logger)
    report_generator = get_report_generator()

    # Initialize LLM reviewer
    llm_reviewer = LLMStrategyReviewer(
        ib_manager=ib_manager,
        market_data=market_data,
        risk_manager=risk_manager,
        registry=strategy_registry,
    )
    await llm_reviewer.start()

    # Set dashboard globals
    import src.dashboard.app as dashboard_app_module
    dashboard_app_module.ib_manager = ib_manager
    dashboard_app_module.market_data = market_data
    dashboard_app_module.risk_manager = risk_manager
    dashboard_app_module.strategy_registry = strategy_registry
    dashboard_app_module.llm_reviewer = llm_reviewer

    logger.info("All components initialized")


async def initialize_strategies() -> None:
    """Initialize and register trading strategies."""
    from src.strategy.base import strategy_registry
    from src.strategy.mean_reversion import MeanReversionStrategy, MeanReversionParameters
    from src.strategy.momentum import MomentumStrategy, MomentumParameters
    from src.strategy.smc import SMCStrategy, SMCParameters

    # SMC Strategy (primary)
    symbols_list = settings.get_symbols_list()
    smc_params = SMCParameters(
        name="smc",
        enabled=settings.STRATEGY_NAME in ("smc", "combined"),
        symbols=symbols_list,
        swing_length=settings.SMC_SWING_LENGTH,
        ob_lookback=settings.SMC_OB_LOOKBACK,
        fvg_min_size=settings.SMC_FVG_MIN_SIZE,
        liquidity_lookback=settings.SMC_LIQUIDITY_LOOKBACK,
        require_bos_confirmation=True,
        trade_premium_discount=True,
        use_breaker_blocks=True,
        min_risk_reward=2.0,
    )
    smc_strategy = SMCStrategy(smc_params, market_data)
    strategy_registry.register(smc_strategy)

    # Mean Reversion Strategy
    mr_params = MeanReversionParameters(
        name="mean_reversion",
        enabled=settings.STRATEGY_NAME in ("mean_reversion", "combined"),
        symbols=symbols_list,
    )
    mr_strategy = MeanReversionStrategy(mr_params, market_data)
    strategy_registry.register(mr_strategy)

    # Momentum Strategy
    mom_params = MomentumParameters(
        name="momentum",
        enabled=settings.STRATEGY_NAME in ("momentum", "combined"),
        symbols=symbols_list,
    )
    mom_strategy = MomentumStrategy(mom_params, market_data)
    strategy_registry.register(mom_strategy)

    # Set active strategy
    strategy_registry.set_active(settings.STRATEGY_NAME)

    logger.info(f"Strategies initialized. Active: {settings.STRATEGY_NAME}")


async def shutdown_components() -> None:
    """Shutdown all components gracefully."""
    global ib_manager, market_data, llm_reviewer, dashboard_task

    if llm_reviewer:
        await llm_reviewer.stop()

    if market_data:
        await market_data.shutdown()

    if ib_manager:
        await ib_manager.disconnect()

    if dashboard_task:
        dashboard_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dashboard_task

    logger.info("Shutdown complete")


async def run_dashboard() -> None:
    """Run the FastAPI dashboard."""
    from src.dashboard.app import app

    config = uvicorn.Config(
        app,
        host=settings.DASHBOARD_HOST,
        port=settings.DASHBOARD_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_trading_loop() -> None:
    """Main trading loop."""
    global _shutdown

    logger.info("Starting trading loop")

    while not _shutdown:
        try:
            # Process signals from all strategies
            from src.strategy.base import strategy_registry
            from src.strategy.portfolio import PortfolioStrategy

            portfolio = PortfolioStrategy(strategy_registry, ib_manager)
            combined_signals = await portfolio.process_signals()

            # Execute signals
            for signal in combined_signals:
                await execute_signal(signal)

            # Check risk
            reduce_risk, reason = risk_manager.should_reduce_risk()
            if reduce_risk:
                logger.warning(f"Risk reduction triggered: {reason}")
                await reduce_positions()

            # Wait for next cycle
            await asyncio.sleep(60)  # 1-minute cycle

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Trading loop error: {e}")
            await asyncio.sleep(10)


async def execute_signal(signal) -> None:
    """Execute a combined signal."""
    from src.compliance.logger import get_operation_logger
    from src.ib.connection import Order

    op_logger = get_operation_logger()

    # Get strategy for position sizing
    from src.strategy.base import strategy_registry
    strategy = strategy_registry.get(signal.strategies[0]) if signal.strategies else None
    if not strategy:
        return

    # Calculate position size
    account_summary = await ib_manager.get_account_summary()
    equity = float(account_summary.get("NetLiquidation", 1_000_000))

    position_sizing = strategy.calculate_position_size(
        symbol=signal.symbol,
        signal=signal,
        account_equity=equity,
        current_price=signal.price,
    )

    # Validate risk
    from src.strategy.base import TradingSignal
    trading_signal = TradingSignal(
        symbol=signal.symbol,
        signal_type=signal.signal_type,
        strength=signal.avg_strength,
        price=signal.price,
        timestamp=signal.timestamp,
        strategy_name="portfolio",
    )
    risk_ok, risk_msg = risk_manager.check_pre_trade_risk(trading_signal, position_sizing)
    if not risk_ok:
        logger.warning(f"Risk check failed: {risk_msg}")
        return

    # Create order
    from ib_insync import Stock
    contract = Stock(signal.symbol, "SMART", "USD")
    await ib_manager.qualify_contracts(contract)

    order = Order()
    order.action = "BUY" if signal.signal_type.value == "buy" else "SELL"
    order.totalQuantity = position_sizing.quantity
    order.orderType = settings.ORDER_TYPE
    order.tif = settings.ORDER_TIF

    if settings.ORDER_TYPE == "LMT":
        order.lmtPrice = round(signal.price, 2)

    # Place order
    trade = await ib_manager.place_order(contract, order)

    # Log trade
    op_logger.log_trade(
        symbol=signal.symbol,
        side=order.action.lower(),
        quantity=position_sizing.quantity,
        price=signal.price,
        order_id=str(trade.order.orderId),
        stop_loss=position_sizing.stop_loss,
        take_profit=position_sizing.take_profit,
        signal_metadata=signal.metadata,
    )

    logger.info(f"Order placed: {order.action} {position_sizing.quantity} {signal.symbol} @ {signal.price}")


async def reduce_positions() -> None:
    """Reduce position sizes due to risk."""
    # Implementation would close or reduce positions
    logger.info("Reducing positions...")


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    global _shutdown

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        _shutdown = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


@click.group()
@click.option("--mode", type=click.Choice(["dev", "trial", "live"]), default="dev", help="Operating mode")
@click.option("--config", type=click.Path(exists=True), help="Config file path")
def cli(mode: str, config: str | None):
    """WIC 2026 Trading Agent CLI."""
    settings.MODE = mode
    if config:
        # Load config from file
        pass


@cli.command()
def run():
    """Run the trading workstation."""
    setup_signal_handlers()

    async def main():
        async with lifespan():
            await run_trading_loop()

    asyncio.run(main())


@cli.command()
def dashboard():
    """Run only the dashboard."""
    setup_signal_handlers()

    async def main():
        global ib_manager, market_data, risk_manager, llm_reviewer
        from src.compliance.logger import get_operation_logger
        from src.compliance.report_generator import get_report_generator
        from src.ib.connection import IBConnectionManager
        from src.ib.market_data import MarketDataPipeline
        from src.llm.reviewer import LLMStrategyReviewer
        from src.risk.manager import RiskManager
        from src.strategy.base import strategy_registry
        from src.strategy.mean_reversion import MeanReversionStrategy, MeanReversionParameters
        from src.strategy.momentum import MomentumStrategy, MomentumParameters
        from src.strategy.smc import SMCStrategy, SMCParameters

        # Minimal initialization for dashboard
        ib_manager = IBConnectionManager()
        await ib_manager.connect()
        await ib_manager.start_reconnect_loop()

        market_data = MarketDataPipeline(ib_manager)
        await market_data.initialize()

        risk_manager = RiskManager(ib_manager)
        await risk_manager.initialize()

        await initialize_strategies()

        llm_reviewer = LLMStrategyReviewer(ib_manager, market_data, risk_manager, strategy_registry)
        await llm_reviewer.start()

        import src.dashboard.app as dashboard_app_module
        dashboard_app_module.ib_manager = ib_manager
        dashboard_app_module.market_data = market_data
        dashboard_app_module.risk_manager = risk_manager
        dashboard_app_module.strategy_registry = strategy_registry
        dashboard_app_module.llm_reviewer = llm_reviewer

        await run_dashboard()

    asyncio.run(main())


@cli.command()
@click.argument("symbol")
@click.option("--days", default=30, help="Days of historical data")
def backtest(symbol: str, days: int):
    """Run backtest for a symbol."""
    from src.strategy.smc import SMCStrategy, SMCParameters
    from src.ib.connection import IBConnectionManager
    from src.ib.market_data import MarketDataPipeline

    async def run_backtest():
        ib = IBConnectionManager()
        await ib.connect()

        md = MarketDataPipeline(ib)
        await md.initialize([symbol])

        params = SMCParameters(symbols=[symbol])
        strategy = SMCStrategy(params, md)

        # Get data
        df = md.get_bars(symbol, count=days * 30)  # Approximate
        print(f"Loaded {len(df)} bars for {symbol}")

        # Run analysis
        await strategy._update_smc_analysis(symbol)
        state = strategy.get_smc_state(symbol)
        print(f"SMC State: {state}")

        await ib.disconnect()

    asyncio.run(run_backtest())


@cli.command()
def generate_pre_report():
    """Generate pre-report template."""
    from src.compliance.report_generator import PreReportData, get_report_generator

    data = PreReportData(
        team_name="Your Team Name",
        team_members=["Member 1", "Member 2"],
        organization="Your University",
        strategy_name="smc",
        strategy_description="Smart Money Concepts strategy with Order Blocks, FVG, and Market Structure analysis",
        hypothesis="Expected 15-20% annual return with max 5% drawdown using SMC strategy with LLM review",
        decision_process="Quantitative SMC strategy generates signals; LLM reviews strategy hourly and adjusts parameters",
        llm_role="LLM reviews strategy performance hourly, suggests parameter adjustments, and validates risk settings",
        order_logic="Limit orders placed at Order Block levels with 2:1 risk:reward, stop loss below/above OB",
        risk_management="1% risk per trade, max 10% per position, 5% daily drawdown limit, sector limits",
        change_policy="All parameter changes logged and require LLM review approval. Code changes require human authorization.",
        symbols=["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
        timeframe="15 mins",
        data_sources=["IB 15-min delayed data"],
        llm_provider="openrouter",
        llm_model="anthropic/claude-3.5-sonnet",
        llm_spending_cap=100.0,
    )

    generator = get_report_generator()
    path = generator.generate_pre_report(data)
    print(f"Pre-report generated: {path}")


if __name__ == "__main__":
    cli()