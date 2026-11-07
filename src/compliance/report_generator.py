"""Report generator for competition pre/post reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from src.config.settings import get_settings
from src.compliance.change_tracker import ChangeTracker
from src.compliance.logger import OperationLogger, get_operation_logger

if TYPE_CHECKING:
    from src.risk.manager import RiskManager
    from src.strategy.base import StrategyRegistry


@dataclass
class PreReportData:
    """Data for pre-report."""

    # Team info
    team_name: str = ""
    team_members: list[str] = field(default_factory=list)
    organization: str = ""

    # Strategy
    strategy_name: str = "smc"
    strategy_description: str = ""
    hypothesis: str = ""
    """Expected return hypothesis"""

    # Decision process
    decision_process: str = ""
    """How decisions are made (LLM role, rules, etc.)"""

    llm_role: str = ""
    """Role of LLM in decision making"""

    order_logic: str = ""
    """How orders are placed"""

    risk_management: str = ""
    """Risk management approach"""

    change_policy: str = ""
    """Policy for strategy changes"""

    # Technical
    symbols: list[str] = field(default_factory=list)
    timeframe: str = "15 mins"
    data_sources: list[str] = field(default_factory=list)

    # LLM
    llm_provider: str = "openrouter"
    llm_model: str = ""
    llm_spending_cap: float = 100.0


@dataclass
class PostReportData:
    """Data for post-report."""

    # Results
    final_equity: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0

    # Comparison
    hypothesis_met: bool = False
    hypothesis_vs_actual: str = ""

    # Behavior
    actual_behavior: str = ""
    """How the agent actually behaved vs plan"""

    key_decisions: list[dict] = field(default_factory=list)
    """Record of key decisions from judgement to execution"""

    # Changes
    changes_made: list[dict] = field(default_factory=list)

    # Issues
    issues_encountered: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)


class ReportGenerator:
    """Generates competition pre/post reports."""

    def __init__(
        self,
        operation_logger: OperationLogger | None = None,
        change_tracker: ChangeTracker | None = None,
        risk_manager: RiskManager | None = None,
        strategy_registry: StrategyRegistry | None = None,
    ) -> None:
        self.settings = get_settings()
        self.report_dir = self.settings.REPORT_DIR
        self.report_dir.mkdir(parents=True, exist_ok=True)

        self.operation_logger = operation_logger or get_operation_logger()
        self.change_tracker = change_tracker
        self.risk_manager = risk_manager
        self.strategy_registry = strategy_registry

        # Jinja2 for templates
        self.templates_dir = Path(__file__).parent / "templates"
        self.templates_dir.mkdir(exist_ok=True)
        self._create_default_templates()

        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _create_default_templates(self) -> None:
        """Create default report templates."""

        # Pre-report template
        pre_template = """# Pre-Report: World Investment Competition 2026 - AI Agent Division

## Team Information
- **Team Name**: {{ data.team_name }}
- **Members**: {% for m in data.team_members %}{{ m }}{% if not loop.last %}, {% endif %}{% endfor %}
- **Organization**: {{ data.organization }}

## Strategy Overview
- **Strategy**: {{ data.strategy_name }}
- **Description**: {{ data.strategy_description }}
- **Return Hypothesis**: {{ data.hypothesis }}

## Decision Making Process
{{ data.decision_process }}

### LLM Role
{{ data.llm_role }}

### Order Placement Logic
{{ data.order_logic }}

## Risk Management
{{ data.risk_management }}

## Change Policy
{{ data.change_policy }}

## Technical Configuration
- **Symbols**: {{ data.symbols | join(", ") }}
- **Timeframe**: {{ data.timeframe }}
- **Data Sources**: {{ data.data_sources | join(", ") }}

## LLM Configuration
- **Provider**: {{ data.llm_provider }}
- **Model**: {{ data.llm_model }}
- **Spending Cap**: ${{ "%.2f"|format(data.llm_spending_cap) }}

---
*Generated: {{ timestamp }}*
"""

        # Post-report template
        post_template = """# Post-Report: World Investment Competition 2026 - AI Agent Division

## Team Information
- **Team Name**: {{ data.team_name }}
- **Competition Period**: {{ start_date }} to {{ end_date }}

## Performance Summary
- **Starting Equity**: $1,000,000
- **Final Equity**: ${{ "%.2f"|format(data.final_equity) }}
- **Total Return**: {{ "%.2f"|format(data.total_return * 100) }}%
- **Max Drawdown**: {{ "%.2f"|format(data.max_drawdown * 100) }}%
- **Sharpe Ratio**: {{ "%.2f"|format(data.sharpe_ratio) }}
- **Win Rate**: {{ "%.1f"|format(data.win_rate * 100) }}%
- **Profit Factor**: {{ "%.2f"|format(data.profit_factor) }}
- **Total Trades**: {{ data.total_trades }}

## Hypothesis Evaluation
- **Hypothesis Met**: {{ "Yes" if data.hypothesis_met else "No" }}
- **Comparison**: {{ data.hypothesis_vs_actual }}

## Actual Behavior
{{ data.actual_behavior }}

## Key Decisions (Judgement to Execution)
{% for decision in data.key_decisions %}
### {{ decision.timestamp }} - {{ decision.symbol }}
- **Decision**: {{ decision.decision }}
- **Reasoning**: {{ decision.reasoning }}
- **Outcome**: {{ decision.outcome }}
{% endfor %}

## Changes Made During Competition
{% for change in data.changes_made %}
- **{{ change.timestamp }}**: {{ change.description }} ({{ change.change_type }}) - {{ change.reason }}
{% endfor %}

## Issues Encountered
{% for issue in data.issues_encountered %}
- {{ issue }}
{% endfor %}

## Lessons Learned
{% for lesson in data.lessons_learned %}
- {{ lesson }}
{% endfor %}

---
*Generated: {{ timestamp }}*
"""

        (self.templates_dir / "pre_report.j2").write_text(pre_template)
        (self.templates_dir / "post_report.j2").write_text(post_template)

    def generate_pre_report(self, data: PreReportData) -> Path:
        """Generate pre-report."""
        template = self.env.get_template("pre_report.j2")
        content = template.render(data=data, timestamp=datetime.now().isoformat())

        filename = f"pre_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.report_dir / filename
        filepath.write_text(content)

        # Also save as JSON for programmatic access
        json_path = self.report_dir / f"pre_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        json_path.write_text(json.dumps(data.__dict__, default=str, indent=2))

        logger.info(f"Pre-report generated: {filepath}")
        return filepath

    def generate_post_report(
        self,
        data: PostReportData,
        start_date: datetime,
        end_date: datetime,
    ) -> Path:
        """Generate post-report."""
        template = self.env.get_template("post_report.j2")
        content = template.render(
            data=data,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            timestamp=datetime.now().isoformat(),
        )

        filename = f"post_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.report_dir / filename
        filepath.write_text(content)

        json_path = self.report_dir / f"post_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        json_path.write_text(json.dumps(data.__dict__, default=str, indent=2))

        logger.info(f"Post-report generated: {filepath}")
        return filepath

    def auto_generate_post_report(
        self,
        team_name: str,
        start_date: datetime,
        end_date: datetime,
    ) -> PostReportData:
        """Auto-generate post-report from logged data."""
        # Get daily summary
        daily_summaries = []
        current = start_date
        while current <= end_date:
            daily_summaries.append(self.operation_logger.get_daily_summary(current))
            current += timedelta(days=1)

        # Aggregate
        total_trades = sum(d["trades_count"] for d in daily_summaries)
        total_llm_cost = sum(d["llm_cost_usd"] for d in daily_summaries)

        # Get risk metrics
        risk_metrics = self.risk_manager.get_risk_metrics() if self.risk_manager else None

        # Get changes
        changes = self.change_tracker.export_for_report(start_date, end_date) if self.change_tracker else []

        # Build post report data
        data = PostReportData(
            final_equity=1_000_000,  # Would get from IB
            total_return=0.0,
            max_drawdown=risk_metrics.max_drawdown if risk_metrics else 0.0,
            sharpe_ratio=risk_metrics.sharpe_ratio if risk_metrics else 0.0,
            win_rate=risk_metrics.win_rate if risk_metrics else 0.0,
            profit_factor=risk_metrics.profit_factor if risk_metrics else 0.0,
            total_trades=total_trades,
            hypothesis_met=False,  # Manual
            hypothesis_vs_actual="",  # Manual
            actual_behavior="Auto-generated from logs. Manual review needed.",
            key_decisions=[],  # Would extract from logs
            changes_made=changes,
            issues_encountered=[],
            lessons_learned=[],
        )

        return data


# Global report generator
_report_generator: ReportGenerator | None = None


def get_report_generator() -> ReportGenerator:
    """Get or create global report generator."""
    global _report_generator
    if _report_generator is None:
        _report_generator = ReportGenerator()
    return _report_generator