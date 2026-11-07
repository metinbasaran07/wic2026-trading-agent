"""Operation logger for competition compliance."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from loguru import logger

from src.config.settings import get_settings

if TYPE_CHECKING:
    from src.strategy.base import TradingSignal


@dataclass
class OperationLogEntry:
    """Single operation log entry."""

    timestamp: datetime
    event_type: str
    """Type: trade, signal, review, change, error, recovery, stop"""

    # Common fields
    symbol: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    # Trade-specific
    side: str | None = None  # buy/sell
    quantity: int | None = None
    price: float | None = None
    order_id: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    # LLM-specific
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_cost_usd: float | None = None
    llm_tokens: int | None = None
    prompt: str | None = None
    response: str | None = None

    # Change-specific
    change_type: str | None = None  # parameter, strategy, code, risk
    old_value: Any = None
    new_value: Any = None
    reason: str | None = None

    # Risk/Recovery
    drawdown_pct: float | None = None
    action_taken: str | None = None

    def to_jsonl(self) -> str:
        """Convert to JSONL format."""
        data = {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
        }

        # Add non-None fields
        for key, value in self.__dict__.items():
            if key != "timestamp" and value is not None:
                data[key] = value

        return json.dumps(data, default=str)


class OperationLogger:
    """Competition-compliant operation logger."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.log_dir = self.settings.LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Separate log files for different event types
        self.log_files = {
            "trade": self.log_dir / "trades.jsonl",
            "signal": self.log_dir / "signals.jsonl",
            "review": self.log_dir / "llm_reviews.jsonl",
            "change": self.log_dir / "changes.jsonl",
            "error": self.log_dir / "errors.jsonl",
            "recovery": self.log_dir / "recoveries.jsonl",
            "stop": self.log_dir / "stops.jsonl",
            "all": self.log_dir / "operations.jsonl",
        }

        # Initialize structlog for structured logging
        self._setup_structlog()

        logger.info(f"Operation logger initialized at {self.log_dir}")

    def _setup_structlog(self) -> None:
        """Configure structlog for JSONL output."""
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    def _write_entry(self, entry: OperationLogEntry) -> None:
        """Write entry to appropriate log files."""
        jsonl = entry.to_jsonl()

        # Write to all events log
        with open(self.log_files["all"], "a") as f:
            f.write(jsonl + "\n")

        # Write to specific event type log
        if entry.event_type in self.log_files:
            with open(self.log_files[entry.event_type], "a") as f:
                f.write(jsonl + "\n")

    # =========================================================================
    # Trade Logging
    # =========================================================================

    def log_trade(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        order_id: str | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        signal_metadata: dict | None = None,
    ) -> None:
        """Log a trade execution."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="trade",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
            details=signal_metadata or {},
        )
        self._write_entry(entry)

    def log_signal(self, signal: TradingSignal) -> None:
        """Log a trading signal."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="signal",
            symbol=signal.symbol,
            details={
                "signal_type": signal.signal_type.value,
                "strength": signal.strength.name,
                "price": signal.price,
                "strategy": signal.strategy_name,
                "metadata": signal.metadata,
            },
        )
        self._write_entry(entry)

    # =========================================================================
    # LLM Logging
    # =========================================================================

    def log_llm_review(
        self,
        provider: str,
        model: str,
        prompt: str,
        response: str,
        cost_usd: float,
        tokens: int,
        parsed_recommendations: dict | None = None,
    ) -> None:
        """Log an LLM strategy review."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="review",
            llm_provider=provider,
            llm_model=model,
            llm_cost_usd=cost_usd,
            llm_tokens=tokens,
            prompt=prompt[:5000],  # Truncate long prompts
            response=response[:5000],
            details=parsed_recommendations or {},
        )
        self._write_entry(entry)

    # =========================================================================
    # Change Logging
    # =========================================================================

    def log_change(
        self,
        change_type: str,
        description: str,
        old_value: Any = None,
        new_value: Any = None,
        reason: str = "",
        auto: bool = False,
    ) -> None:
        """Log a strategy/parameter/code change."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="change",
            change_type=change_type,
            details={"description": description, "auto": auto},
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
        self._write_entry(entry)

    # =========================================================================
    # Error/Recovery Logging
    # =========================================================================

    def log_error(
        self,
        error: Exception,
        context: str = "",
        recovery_action: str | None = None,
    ) -> None:
        """Log an error and recovery action."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="error",
            details={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
                "recovery_action": recovery_action,
            },
            action_taken=recovery_action,
        )
        self._write_entry(entry)

    def log_recovery(
        self,
        action: str,
        reason: str,
        code_changed: bool = False,
        details: dict | None = None,
    ) -> None:
        """Log a recovery action (restart, reconnect, parameter reset)."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="recovery",
            details=details or {},
            action_taken=action,
            reason=reason,
        )
        self._write_entry(entry)

    def log_stop(self, reason: str, triggered_by: str = "system") -> None:
        """Log an emergency stop."""
        entry = OperationLogEntry(
            timestamp=datetime.now(),
            event_type="stop",
            details={"reason": reason, "triggered_by": triggered_by},
            action_taken="emergency_stop",
            reason=reason,
        )
        self._write_entry(entry)

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_logs(
        self,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        symbol: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Query operation logs."""
        logs = []
        file_path = self.log_files.get(event_type, self.log_files["all"])

        if not file_path.exists():
            return logs

        with open(file_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    # Filter
                    if start_time and datetime.fromisoformat(entry["timestamp"]) < start_time:
                        continue
                    if end_time and datetime.fromisoformat(entry["timestamp"]) > end_time:
                        continue
                    if symbol and entry.get("symbol") != symbol:
                        continue
                    logs.append(entry)
                except json.JSONDecodeError:
                    continue

        return logs[-limit:]

    def get_daily_summary(self, date: datetime | None = None) -> dict:
        """Get daily summary for reporting."""
        date = date or datetime.now()
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        trades = self.get_logs("trade", start, end)
        reviews = self.get_logs("review", start, end)
        changes = self.get_logs("change", start, end)
        errors = self.get_logs("error", start, end)

        total_llm_cost = sum(r.get("llm_cost_usd", 0) for r in reviews)
        total_llm_tokens = sum(r.get("llm_tokens", 0) for r in reviews)

        return {
            "date": date.date().isoformat(),
            "trades_count": len(trades),
            "reviews_count": len(reviews),
            "changes_count": len(changes),
            "errors_count": len(errors),
            "llm_cost_usd": total_llm_cost,
            "llm_tokens": total_llm_tokens,
            "symbols_traded": list(set(t.get("symbol") for t in trades if t.get("symbol"))),
        }

    def rotate_logs(self) -> None:
        """Rotate log files (called daily)."""
        # Could implement log rotation here
        pass


# Global logger instance
_operation_logger: OperationLogger | None = None


def get_operation_logger() -> OperationLogger:
    """Get or create global operation logger."""
    global _operation_logger
    if _operation_logger is None:
        _operation_logger = OperationLogger()
    return _operation_logger