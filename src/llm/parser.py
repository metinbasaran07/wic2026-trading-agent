"""LLM response parsing and validation."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from loguru import logger


class StrategyReviewResponse(BaseModel):
    """Parsed strategy review response."""

    overall_assessment: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    parameter_adjustments: dict[str, Any] = Field(default_factory=dict)
    risk_adjustments: dict[str, Any] = Field(default_factory=dict)
    strategy_changes: list[dict[str, Any]] = Field(default_factory=list)
    new_signals_to_watch: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class ParameterOptimizationResponse(BaseModel):
    """Parsed parameter optimization response."""

    optimized_parameters: dict[str, Any] = Field(default_factory=dict)
    expected_improvement: dict[str, float] = Field(default_factory=dict)
    reasoning: str = ""


class LLMParser:
    """Parse and validate LLM responses."""

    @staticmethod
    def parse_review_response(content: str) -> StrategyReviewResponse | None:
        """Parse strategy review response."""
        try:
            # Try to extract JSON from content
            data = LLMParser._extract_json(content)
            if data:
                return StrategyReviewResponse(**data)
        except Exception as e:
            logger.error(f"Failed to parse review response: {e}")
            logger.debug(f"Raw content: {content[:500]}")
        return None

    @staticmethod
    def parse_optimization_response(content: str) -> ParameterOptimizationResponse | None:
        """Parse parameter optimization response."""
        try:
            data = LLMParser._extract_json(content)
            if data:
                return ParameterOptimizationResponse(**data)
        except Exception as e:
            logger.error(f"Failed to parse optimization response: {e}")
        return None

    @staticmethod
    def _extract_json(content: str) -> dict | None:
        """Extract JSON object from content."""
        content = content.strip()

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        import re
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(json_pattern, content, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Try to find first JSON object
        start = content.find('{')
        end = content.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end+1])
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def validate_parameter_changes(
        current_params: dict[str, Any],
        proposed_changes: dict[str, Any],
        param_bounds: dict[str, tuple] | None = None,
    ) -> dict[str, Any]:
        """Validate and clamp parameter changes."""
        validated = {}

        for param, value in proposed_changes.items():
            if param not in current_params:
                logger.warning(f"Unknown parameter: {param}")
                continue

            # Apply bounds if provided
            if param_bounds and param in param_bounds:
                min_val, max_val = param_bounds[param]
                if isinstance(value, (int, float)):
                    value = max(min_val, min(max_val, value))

            validated[param] = value

        return validated