"""OpportunityAnalyst — synthesizes ONE structured opportunity hypothesis
from real, already-executed research results. Never searches or fetches
anything itself — that's the Executive/Planner/dispatch loop's job,
reused unmodified. This mirrors Critic's pattern (real post-execution
LLM synthesis, budget-gated, honest about failure) applied to a
different output shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..prompts.opportunity_analyst_prompt import OPPORTUNITY_ANALYST_INSTRUCTIONS
from .model_policy import call_with_fallback, tiers_for
from .schemas import OPPORTUNITY_HYPOTHESIS_SCHEMA


@dataclass
class OpportunityOutcome:
    hypothesis: Optional[Dict[str, Any]] = None
    cost_usd: Optional[float] = None
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model: Optional[str] = None


class OpportunityAnalyst:
    def __init__(self, llm_adapter: Any) -> None:
        self._llm = llm_adapter

    def analyze(self, query: str, research_results: List[Dict[str, Any]]) -> OpportunityOutcome:
        """research_results: the real executed_steps from a completed
        Executive.run() — same shape Critic already consumes."""
        evidence = [
            {
                "tool_name": step.get("tool_name"),
                "result": step.get("result"),
            }
            for step in research_results
        ]
        kwargs: Dict[str, Any] = dict(
            instructions=OPPORTUNITY_ANALYST_INSTRUCTIONS,
            input=[{
                "type": "text",
                "text": f"Research query: {query}\n\nReal research results:\n{evidence}",
            }],
            json_schema=OPPORTUNITY_HYPOTHESIS_SCHEMA,
            schema_name="foundry.opportunity_hypothesis",
            purpose="foundry.opportunity_analyst",
            temperature=0.0,
            max_tokens=3000,
        )
        tiers = tiers_for("opportunity_analyst", "FOUNDRY_ANALYST_MODEL", "FOUNDRY_ANALYST_PROVIDER")
        result = call_with_fallback(self._llm, tiers, **kwargs)
        usage = getattr(result, "usage", None)
        return OpportunityOutcome(
            hypothesis=result.parsed,
            cost_usd=getattr(usage, "cost_usd", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            model=getattr(result, "model", None),
        )
