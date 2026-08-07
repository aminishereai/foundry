"""Critic — evaluates completed execution only. Never executes, never
retries, never re-plans. All reasoning flows through Hermes via the LLM
adapter, same as Planner.

Phase 3 scope: only called on successful (status="ok") executions with
at least one executed step. There's nothing meaningful to critique in a
no_action or error result — no completed work exists yet to judge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..prompts.critic_prompt import CRITIC_INSTRUCTIONS
from .schemas import CRITIQUE_SCHEMA


@dataclass
class CritiqueOutcome:
    verdict: Optional[str] = None
    critique: str = ""
    cost_usd: Optional[float] = None
    total_tokens: int = 0


class Critic:
    def __init__(self, llm_adapter: Any) -> None:
        self._llm = llm_adapter

    def review(self, objective: str, executed_steps: List[Dict[str, Any]]) -> CritiqueOutcome:
        """Judge real results only — dispatch status plus each step's own
        result content, not the Planner's original intent."""
        evidence = [
            {
                "tool_name": step.get("tool_name"),
                "dispatch_status": step.get("status"),
                "result": step.get("result"),
            }
            for step in executed_steps
        ]
        result = self._llm.complete_structured(
            instructions=CRITIC_INSTRUCTIONS,
            input=[{
                "type": "text",
                "text": f"Objective: {objective}\n\nExecuted steps and their real results: {evidence}",
            }],
            json_schema=CRITIQUE_SCHEMA,
            schema_name="foundry.critique",
            purpose="foundry.critic",
            temperature=0.0,
            max_tokens=1200,
        )
        usage = getattr(result, "usage", None)
        parsed = result.parsed or {}
        return CritiqueOutcome(
            verdict=parsed.get("verdict"),
            critique=parsed.get("critique", ""),
            cost_usd=getattr(usage, "cost_usd", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
        )