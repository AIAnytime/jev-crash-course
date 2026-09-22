"""Cost model.

Jev's published price is $0.042 per 1M input tokens with output free. OpenAI
prices move, so they are exposed in the sidebar -- edit them there rather than
trusting these defaults blindly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Price:
    input_per_mtok: float
    output_per_mtok: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_mtok
            + output_tokens / 1_000_000 * self.output_per_mtok
        )


JEV_PRICE = Price(input_per_mtok=0.042, output_per_mtok=0.0)

# Defaults for the GPT baseline; confirm against current OpenAI pricing.
OPENAI_PRICES: dict[str, Price] = {
    "gpt-4o-mini": Price(0.15, 0.60),
    "gpt-4o": Price(2.50, 10.00),
    "gpt-4.1-mini": Price(0.40, 1.60),
    "gpt-4.1": Price(2.00, 8.00),
}
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
