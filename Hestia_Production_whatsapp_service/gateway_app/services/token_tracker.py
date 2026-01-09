"""
Token tracking utility for LLM API calls.

Provides a simple wrapper to extract and store token usage from OpenAI API responses.
Supports both Chat Completions API and legacy Responses API.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Container for token usage data."""
    input_tokens: int
    output_tokens: int
    total_tokens: int

    def __repr__(self) -> str:
        return f"TokenUsage(in={self.input_tokens}, out={self.output_tokens}, total={self.total_tokens})"


def extract_token_usage(response: Any) -> Optional[TokenUsage]:
    """
    Extract token usage from OpenAI API response.

    Supports multiple response formats:
    1. Chat Completions API (response.usage)
    2. Responses API (response.output[0].usage)

    Args:
        response: OpenAI API response object

    Returns:
        TokenUsage object or None if extraction fails
    """
    try:
        # Check if response has usage
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage

            # Try to get input tokens (try both naming conventions)
            input_tok = getattr(usage, 'input_tokens', None)
            if input_tok is None:
                input_tok = getattr(usage, 'prompt_tokens', 0)

            # Try to get output tokens (try both naming conventions)
            output_tok = getattr(usage, 'output_tokens', None)
            if output_tok is None:
                output_tok = getattr(usage, 'completion_tokens', 0)

            # Get total tokens
            total_tok = getattr(usage, 'total_tokens', 0)
            if total_tok == 0 and input_tok and output_tok:
                total_tok = input_tok + output_tok

            return TokenUsage(
                input_tokens=input_tok or 0,
                output_tokens=output_tok or 0,
                total_tokens=total_tok
            )

        # Try Responses API format (nested in output)
        if hasattr(response, 'output') and len(response.output) > 0:
            output = response.output[0]
            if hasattr(output, 'usage') and output.usage:
                usage = output.usage
                input_tok = getattr(usage, 'input_tokens', 0) or getattr(usage, 'prompt_tokens', 0)
                output_tok = getattr(usage, 'output_tokens', 0) or getattr(usage, 'completion_tokens', 0)
                total_tok = getattr(usage, 'total_tokens', 0) or (input_tok + output_tok)

                return TokenUsage(
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    total_tokens=total_tok
                )

        # Try dict-based access (if response is already parsed)
        if isinstance(response, dict):
            usage = response.get('usage', {})
            if usage:
                return TokenUsage(
                    input_tokens=usage.get('prompt_tokens', usage.get('input_tokens', 0)),
                    output_tokens=usage.get('completion_tokens', usage.get('output_tokens', 0)),
                    total_tokens=usage.get('total_tokens', 0)
                )

        logger.warning(
            "[TOKEN_TRACKER] Could not extract token usage from response",
            extra={
                "response_type": type(response).__name__,
                "has_usage": hasattr(response, 'usage'),
                "has_output": hasattr(response, 'output'),
                "location": "gateway_app/services/token_tracker.py::extract_token_usage"
            }
        )
        return None

    except Exception as e:
        logger.exception(
            "[TOKEN_TRACKER] Error extracting token usage",
            extra={
                "error": str(e),
                "response_type": type(response).__name__,
                "location": "gateway_app/services/token_tracker.py::extract_token_usage"
            }
        )
        return None


def calculate_cost(
    usage: TokenUsage,
    input_price_per_1m: float = 0.15,
    output_price_per_1m: float = 0.60
) -> Dict[str, float]:
    """
    Calculate cost in USD for token usage.

    Default prices are for GPT-4o-mini:
    - Input: $0.15 per 1M tokens
    - Output: $0.60 per 1M tokens

    Args:
        usage: TokenUsage object
        input_price_per_1m: Price per 1M input tokens in USD
        output_price_per_1m: Price per 1M output tokens in USD

    Returns:
        Dict with input_cost, output_cost, and total_cost in USD
    """
    input_cost = (usage.input_tokens * input_price_per_1m) / 1_000_000
    output_cost = (usage.output_tokens * output_price_per_1m) / 1_000_000
    total_cost = input_cost + output_cost

    return {
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6)
    }


# Pricing constants for different models (per 1M tokens)
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


def get_pricing_for_model(model_name: str) -> Dict[str, float]:
    """
    Get pricing for a specific model.

    Args:
        model_name: Name of the model

    Returns:
        Dict with 'input' and 'output' prices per 1M tokens
    """
    # Default to gpt-4o-mini pricing if model not found
    return PRICING.get(model_name, PRICING["gpt-4o-mini"])
