"""Planner — produces structured plans only. Never executes. Never calls
tools directly. All reasoning flows through Hermes via the LLM adapter.

Phase 2: plans are now an ordered sequence of 0-4 steps instead of
exactly one. Honest scope limit: the whole sequence is produced in a
single upfront LLM call, before any step executes — so a step cannot see
a previous step's actual output value. This handles multi-action
objectives whose steps are independent of each other's results (e.g.
"read config.yaml and write a summary to notes.md"), not dependent
chains ("find the file, then read whatever you found"). True dependent
chaining needs re-planning between steps, which is out of scope until a
later phase. This constraint is stated directly in the prompt so the
Planner doesn't attempt something it can't actually do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..prompts.planner_prompt import PLANNER_INSTRUCTIONS
from .schemas import PLAN_SCHEMA


@dataclass
class PlanOutcome:
    """What the Planner produces: an ordered step sequence, plus the real
    cost of producing it. Cost is surfaced (not consumed) here — Executive
    owns the budget decision, Planner just reports what its call cost."""

    steps: List[Dict[str, Any]] = field(default_factory=list)
    overall_reasoning: str = ""
    cost_usd: Optional[float] = None
    total_tokens: int = 0


class Planner:
    """Asks Hermes' LLM for an ordered sequence of tool-call decisions."""

    def __init__(self, llm_adapter: Any) -> None:
        self._llm = llm_adapter

    def plan(self, objective: str) -> PlanOutcome:
        """Return a PlanOutcome. steps is empty if the LLM declined to
        produce any (a valid outcome — see prompt rule 4) or if the
        structured call failed to parse at all."""
        result = self._llm.complete_structured(
            instructions=PLANNER_INSTRUCTIONS,
            input=[{"type": "text", "text": objective}],
            json_schema=PLAN_SCHEMA,
            schema_name="foundry.plan",
            purpose="foundry.planner",
            temperature=0.0,
            max_tokens=1500,
        )
        usage = getattr(result, "usage", None)
        parsed = result.parsed or {}
        return PlanOutcome(
            steps=list(parsed.get("steps") or []),
            overall_reasoning=parsed.get("overall_reasoning", ""),
            cost_usd=getattr(usage, "cost_usd", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
        )
