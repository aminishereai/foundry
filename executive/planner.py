"""Planner — produces structured plans only. Never executes. Never calls
tools directly. All reasoning flows through Hermes via the LLM adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..prompts.planner_prompt import PLANNER_INSTRUCTIONS
from .schemas import PLAN_STEP_SCHEMA


@dataclass
class PlanOutcome:
    """What the Planner produces: the plan itself, plus the real cost of
    producing it. Cost is surfaced (not consumed) here — Executive owns
    the budget decision, Planner just reports what its call actually cost."""

    plan: Optional[Dict[str, Any]]
    cost_usd: Optional[float]
    total_tokens: int


class Planner:
    """Asks Hermes' LLM for exactly one tool-call decision per objective."""

    def __init__(self, llm_adapter: Any) -> None:
        self._llm = llm_adapter

    def plan(self, objective: str) -> PlanOutcome:
        """Return a PlanOutcome. plan is None only if the LLM failed to
        produce a valid structured response at all (as opposed to
        deliberately returning an empty tool_name, which is a valid plan
        meaning 'no single tool call fits')."""
        result = self._llm.complete_structured(
            instructions=PLANNER_INSTRUCTIONS,
            input=[{"type": "text", "text": objective}],
            json_schema=PLAN_STEP_SCHEMA,
            schema_name="foundry.plan_step",
            purpose="foundry.planner",
            temperature=0.0,
            max_tokens=300,
        )
        usage = getattr(result, "usage", None)
        return PlanOutcome(
            plan=result.parsed,
            cost_usd=getattr(usage, "cost_usd", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
        )