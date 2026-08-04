"""Planner — produces structured plans only. Never executes. Never calls
tools directly. All reasoning flows through Hermes via the LLM adapter.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..prompts.planner_prompt import PLANNER_INSTRUCTIONS
from .schemas import PLAN_STEP_SCHEMA


class Planner:
    """Asks Hermes' LLM for exactly one tool-call decision per objective."""

    def __init__(self, llm_adapter: Any) -> None:
        self._llm = llm_adapter

    def plan(self, objective: str) -> Optional[Dict[str, Any]]:
        """Return {"tool_name", "tool_args", "reasoning"} or None if the
        LLM failed to produce a valid structured plan at all (as opposed
        to deliberately returning an empty tool_name, which is a valid
        plan meaning 'no single tool call fits')."""
        result = self._llm.complete_structured(
            instructions=PLANNER_INSTRUCTIONS,
            input=[{"type": "text", "text": objective}],
            json_schema=PLAN_STEP_SCHEMA,
            schema_name="foundry.plan_step",
            purpose="foundry.planner",
            temperature=0.0,
            max_tokens=300,
        )
        return result.parsed
