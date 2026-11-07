"""LLM prompts for strategy review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


# Get prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPTS_DIR.mkdir(exist_ok=True)

# Jinja2 environment
env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
)


def get_prompt_template(name: str) -> str:
    """Get prompt template by name, creating default if not exists."""
    template_path = PROMPTS_DIR / f"{name}.j2"

    if not template_path.exists():
        # Create default templates
        _create_default_templates()
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {name}")

    return env.get_template(f"{name}.j2")


def _create_default_templates() -> None:
    """Create default prompt templates."""

    # Strategy Review Prompt
    review_template = """# Strategy Review Request

You are an expert quantitative trading analyst reviewing an AI trading agent's strategy for the World Investment Competition 2026.

## Current Strategy State

**Strategy**: {{ strategy_name }}
**Mode**: {{ mode }} (dev/trial/live)
**Review Interval**: {{ review_interval_minutes }} minutes

## Market Context

**Current Positions**:
{% for pos in positions %}
- {{ pos.symbol }}: {{ pos.quantity }} shares @ ${% if pos.entry_price %}{{ "%.2f"|format(pos.entry_price) }}{% else %}N/A{% endif %} | P&L: ${{ "%.2f"|format(pos.unrealized_pnl) }} ({{ "%.2f"|format(pos.unrealized_pnl_pct) }}%)
{% endfor %}

**Account Equity**: ${{ "%.2f"|format(account_equity) }}
**Daily P&L**: ${{ "%.2f"|format(daily_pnl) }}
**Current Drawdown**: {{ "%.2f"|format(current_drawdown * 100) }}%

## Recent Signals (Last {{ lookback_hours }} hours)

{% for signal in recent_signals %}
- **{{ signal.symbol }}**: {{ signal.signal_type.value.upper() }} | Strength: {{ signal.strength.name }} | Price: ${{ "%.2f"|format(signal.price) }} | Time: {{ signal.timestamp.strftime('%H:%M') }}
  - Reason: {{ signal.metadata.get('reason', 'N/A') }}
{% endfor %}

## SMC Analysis (for SMC Strategy)

{% if smc_state %}
**{{ symbol }} SMC State**:
- Market Structure: {{ smc_state.structure_events }} events (recent: {{ smc_state.recent_structure }})
- Order Blocks: {{ smc_state.order_blocks.bullish }} bullish, {{ smc_state.order_blocks.bearish }} bearish active
- FVGs: {{ smc_state.fvg.bullish_open }} bullish open, {{ smc_state.fvg.bearish_open }} bearish open
- Liquidity: {{ smc_state.liquidity.buy_side }} buy-side, {{ smc_state.liquidity.sell_side }} sell-side pools
- Breaker Blocks: {{ smc_state.breaker_blocks }}
{% endif %}

## Risk Metrics

- Win Rate: {{ "%.1f"|format(win_rate * 100) }}%
- Profit Factor: {{ "%.2f"|format(profit_factor) }}
- Sharpe Ratio: {{ "%.2f"|format(sharpe_ratio) }}
- Avg Win: ${{ "%.2f"|format(avg_win) }}
- Avg Loss: ${{ "%.2f"|format(avg_loss) }}

## Review Instructions

Analyze the current strategy performance and provide recommendations in the following JSON format:

```json
{
  "overall_assessment": "Brief assessment of strategy performance",
  "strengths": ["List of what's working well"],
  "weaknesses": ["List of issues or concerns"],
  "parameter_adjustments": {
    "parameter_name": "new_value",
    "reason": "Why this change is recommended"
  },
  "risk_adjustments": {
    "max_position_size": 0.1,
    "stop_loss_pct": 0.02,
    "reason": "Risk adjustment reasoning"
  },
  "strategy_changes": [
    {
      "change": "Description of strategic change",
      "reason": "Reasoning",
      "priority": "high|medium|low"
    }
  ],
  "new_signals_to_watch": ["Symbol1", "Symbol2"],
  "confidence": 0.85
}
```

Focus on:
1. Are the current strategies performing as expected?
2. Should any parameters be adjusted based on recent market conditions?
3. Are risk limits appropriate?
4. Any new opportunities or threats?
5. Specific actionable recommendations

Return ONLY the JSON object, no additional text.
"""

    # Parameter Optimization Prompt
    param_template = """# Parameter Optimization Request

Optimize strategy parameters based on recent performance.

## Current Parameters
{{ current_params | tojson(indent=2) }}

## Performance Data (Last {{ lookback_days }} days)
- Total Trades: {{ total_trades }}
- Win Rate: {{ "%.1f"|format(win_rate * 100) }}%
- Avg Win: ${{ "%.2f"|format(avg_win) }}
- Avg Loss: ${{ "%.2f"|format(avg_loss) }}
- Profit Factor: {{ "%.2f"|format(profit_factor) }}
- Max Drawdown: {{ "%.2f"|format(max_drawdown * 100) }}%
- Sharpe: {{ "%.2f"|format(sharpe) }}

## Parameter Bounds
{{ param_bounds | tojson(indent=2) }}

## Optimization Goal
Maximize risk-adjusted returns while keeping max drawdown under {{ max_dd_limit * 100 }}%.

Return optimized parameters as JSON:
```json
{
  "optimized_parameters": {
    "param_name": "value"
  },
  "expected_improvement": {
    "win_rate": 0.55,
    "profit_factor": 1.5,
    "max_drawdown": 0.04
  },
  "reasoning": "Explanation of changes"
}
```"""

    # Write templates
    (PROMPTS_DIR / "strategy_review.j2").write_text(review_template)
    (PROMPTS_DIR / "parameter_optimization.j2").write_text(param_template)


# Initialize templates on import
_create_default_templates()


class PromptBuilder:
    """Builds prompts for LLM review."""

    def __init__(self) -> None:
        self.review_template = env.get_template("strategy_review.j2")
        self.param_template = env.get_template("parameter_optimization.j2")

    def build_review_prompt(self, context: dict[str, Any]) -> str:
        """Build strategy review prompt."""
        return self.review_template.render(**context)

    def build_optimization_prompt(self, context: dict[str, Any]) -> str:
        """Build parameter optimization prompt."""
        return self.param_template.render(**context)


# Global prompt builder
prompt_builder = PromptBuilder()