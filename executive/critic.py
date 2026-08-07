"""Critic — evaluates completed execution only. Never executes, never
retries, never re-plans. All reasoning flows through Hermes via the LLM
adapter, same as Planner.

Phase 3 scope: only called on successful (status="ok") executions with
at least one executed step. There's nothing meaningful to critique in a
no_action or error result — no completed work exists yet to judge.

Optional model/provider pinning: same mechanism as Planner
(FOUNDRY_PLANNER_MODEL/PROVIDER), via FOUNDRY_CRITIC_MODEL/PROVIDER.
This is how Foundry moves off free-tier dev models to a capable model in
production without any code change — Hermes still owns the actual
provider connection and credentials; Foundry only ever states a
preference via the real model=/provider= kwargs plugin_llm.py exposes.
"""

from __future__ import annotations

import os
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
    input_tokens: int = 0
    output_tokens: int = 0
    model: Optional[str] = None


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
        kwargs: Dict[str, Any] = dict(
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
        model = os.environ.get("FOUNDRY_CRITIC_MODEL")
        if model:
            kwargs["model"] = model
        provider = os.environ.get("FOUNDRY_CRITIC_PROVIDER")
        if provider:
            kwargs["provider"] = provider

        result = self._llm.complete_structured(**kwargs)
        usage = getattr(result, "usage", None)
        parsed = result.parsed or {}
        return CritiqueOutcome(
            verdict=parsed.get("verdict"),
            critique=parsed.get("critique", ""),
            cost_usd=getattr(usage, "cost_usd", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            model=getattr(result, "model", None),
        )