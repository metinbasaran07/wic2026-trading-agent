"""LLM strategy reviewer with periodic reviews."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.config.settings import get_settings
from src.llm.client import get_llm_client
from src.llm.parser import LLMParser, StrategyReviewResponse
from src.llm.prompts import prompt_builder
from src.risk.manager import RiskManager
from src.strategy.base import StrategyRegistry, strategy_registry

if TYPE_CHECKING:
    from src.ib.connection import IBConnectionManager
    from src.ib.market_data import MarketDataPipeline


class LLMStrategyReviewer:
    """Periodic LLM review of strategy performance."""

    def __init__(
        self,
        ib_manager: IBConnectionManager,
        market_data: MarketDataPipeline,
        risk_manager: RiskManager,
        registry: StrategyRegistry = strategy_registry,
    ) -> None:
        self.ib = ib_manager
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.registry = registry
        self.settings = get_settings()
        self.llm = get_llm_client()
        self.parser = LLMParser()

        self.scheduler = AsyncIOScheduler()
        self._running = False
        self.last_review: datetime | None = None
        self.review_history: list[dict] = []

    async def start(self) -> None:
        """Start periodic reviews."""
        if self._running:
            return

        if not self.settings.REVIEW_ENABLED:
            logger.info("LLM reviews disabled in settings")
            return

        interval = self.settings.REVIEW_INTERVAL_MINUTES
        self.scheduler.add_job(
            self._run_review,
            "interval",
            minutes=interval,
            id="strategy_review",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        self._running = True
        logger.info(f"LLM strategy reviewer started (interval: {interval} min)")

    async def stop(self) -> None:
        """Stop periodic reviews."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("LLM strategy reviewer stopped")

    async def _run_review(self) -> None:
        """Execute a strategy review."""
        logger.info("Starting scheduled strategy review")
        try:
            review = await self.conduct_review()
            if review:
                self.last_review = datetime.now()
                self.review_history.append({
                    "timestamp": self.last_review.isoformat(),
                    "review": review.model_dump(),
                })
                # Keep last 100 reviews
                if len(self.review_history) > 100:
                    self.review_history = self.review_history[-100:]

                # Apply recommended changes
                await self._apply_recommendations(review)

                logger.info(f"Strategy review completed: {review.overall_assessment[:100]}")
        except Exception as e:
            logger.error(f"Strategy review failed: {e}")

    async def conduct_review(self) -> StrategyReviewResponse | None:
        """Conduct a comprehensive strategy review."""
        # Gather context
        context = await self._gather_review_context()

        # Build prompt
        prompt = prompt_builder.build_review_prompt(context)

        # Get LLM response
        messages = [
            {"role": "system", "content": "You are an expert quantitative trading analyst. Provide concise, actionable recommendations in valid JSON format only."},
            {"role": "user", "content": prompt},
        ]

        response = await self.llm.chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        # Parse response
        review = self.parser.parse_review_response(response.content)
        return review

    async def _gather_review_context(self) -> dict[str, Any]:
        """Gather all context needed for review."""
        # Get account info
        account_summary = await self.ib.get_account_summary()
        equity = float(account_summary.get("NetLiquidation", 1_000_000))

        # Get positions
        positions_data = await self.ib.get_positions()
        positions = []
        for pos in positions_data:
            if pos.position != 0:
                positions.append({
                    "symbol": pos.contract.symbol,
                    "quantity": pos.position,
                    "entry_price": pos.avgCost,
                    "unrealized_pnl": 0,  # Would need market data
                    "unrealized_pnl_pct": 0,
                })

        # Get recent signals from all strategies
        recent_signals = []
        for strategy in self.registry.strategies.values():
            if strategy.parameters.enabled:
                for symbol in strategy.get_symbols():
                    signals = strategy.get_recent_signals(symbol, hours=24)
                    recent_signals.extend(signals)

        # Sort by time
        recent_signals.sort(key=lambda s: s.timestamp, reverse=True)
        recent_signals = recent_signals[:50]

        # Get risk metrics
        risk_metrics = self.risk_manager.get_risk_metrics()

        # Get SMC state if using SMC strategy
        smc_state = {}
        smc_strategy = self.registry.get("smc")
        if smc_strategy:
            for symbol in smc_strategy.get_symbols():
                smc_state[symbol] = smc_strategy.get_smc_state(symbol)

        return {
            "strategy_name": self.settings.STRATEGY_NAME,
            "mode": self.settings.MODE,
            "review_interval_minutes": self.settings.REVIEW_INTERVAL_MINUTES,
            "positions": positions,
            "account_equity": equity,
            "daily_pnl": risk_metrics.daily_pnl,
            "current_drawdown": risk_metrics.current_drawdown,
            "recent_signals": [
                {
                    "symbol": s.symbol,
                    "signal_type": s.signal_type.value,
                    "strength": s.strength.name,
                    "price": s.price,
                    "timestamp": s.timestamp,
                    "metadata": s.metadata,
                }
                for s in recent_signals
            ],
            "lookback_hours": 24,
            "smc_state": smc_state,
            "win_rate": risk_metrics.win_rate,
            "profit_factor": risk_metrics.profit_factor,
            "sharpe_ratio": risk_metrics.sharpe_ratio,
            "avg_win": risk_metrics.avg_win,
            "avg_loss": risk_metrics.avg_loss,
        }

    async def _apply_recommendations(self, review: StrategyReviewResponse) -> None:
        """Apply recommended parameter changes."""
        # Parameter adjustments
        for param, value in review.parameter_adjustments.items():
            await self._apply_parameter_change(param, value)

        # Risk adjustments
        for param, value in review.risk_adjustments.items():
            await self._apply_risk_change(param, value)

        # Strategy changes (logged for compliance)
        for change in review.strategy_changes:
            logger.info(f"Strategy change recommended: {change['change']} (priority: {change['priority']})")
            # Would need human approval for competition

    async def _apply_parameter_change(self, param: str, value: Any) -> bool:
        """Apply a parameter change to the active strategy."""
        active = self.registry.get_active()
        if not active:
            return False

        # Check if parameter exists
        if hasattr(active.parameters, param):
            old_value = getattr(active.parameters, param)
            setattr(active.parameters, param, value)
            logger.info(f"Parameter changed: {param} = {old_value} -> {value}")
            return True

        logger.warning(f"Parameter not found: {param}")
        return False

    async def _apply_risk_change(self, param: str, value: Any) -> bool:
        """Apply a risk parameter change."""
        if hasattr(self.settings, param.upper()):
            old_value = getattr(self.settings, param.upper())
            setattr(self.settings, param.upper(), value)
            logger.info(f"Risk setting changed: {param} = {old_value} -> {value}")
            return True

        logger.warning(f"Risk setting not found: {param}")
        return False

    async def trigger_review(self) -> StrategyReviewResponse | None:
        """Manually trigger a review."""
        return await self.conduct_review()

    def get_review_history(self, limit: int = 10) -> list[dict]:
        """Get recent review history."""
        return self.review_history[-limit:]

    def get_status(self) -> dict[str, Any]:
        """Get reviewer status."""
        return {
            "running": self._running,
            "interval_minutes": self.settings.REVIEW_INTERVAL_MINUTES,
            "last_review": self.last_review.isoformat() if self.last_review else None,
            "reviews_count": len(self.review_history),
            "next_review": self._get_next_review_time(),
        }

    def _get_next_review_time(self) -> str | None:
        """Get next scheduled review time."""
        jobs = self.scheduler.get_jobs()
        for job in jobs:
            if job.id == "strategy_review":
                return job.next_run_time.isoformat() if job.next_run_time else None
        return None


class LLMReviewScheduler:
    """Alternative simple scheduler for LLM reviews."""

    def __init__(self, reviewer: LLMStrategyReviewer) -> None:
        self.reviewer = reviewer
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the review loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._review_loop())
        logger.info("LLM review scheduler started")

    async def stop(self) -> None:
        """Stop the review loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("LLM review scheduler stopped")

    async def _review_loop(self) -> None:
        """Main review loop."""
        interval = self.settings.REVIEW_INTERVAL_MINUTES * 60

        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                await self.reviewer._run_review()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Review loop error: {e}")
                await asyncio.sleep(60)  # Wait before retry