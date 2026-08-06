"""Planner — produces candidate plans only. Never executes. Never calls
tools directly. Never picks the winner between its own candidates — that
selection is Economics' job (see executive/economics.py::select_best).
All reasoning flows through Hermes via the LLM adapter.

Phase 1b: the Planner now proposes 1-3 candidate approaches per
objective instead of exactly one, so the Executive has something real to
compare. Each candidate still carries the Phase 2 honest-dependency-limit
constraint individually (see prompts/planner_prompt.py).

Optional model/provider pinning: some free-tier models (observed:
openai/gpt-oss-20b:free) reliably fail to produce valid structured JSON
for this schema, while others (observed: nvidia/nemotron-3-super-120b-a12b:free)
handle it fine — same schema, same prompt, different reliability. Rather
than hardcode a specific model permanently, FOUNDRY_PLANNER_MODEL and
FOUNDRY_PLANNER_PROVIDER env vars let it be pinned when needed. Unset by
default — Hermes picks as it normally would.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..prompts.planner_prompt import PLANNER_INSTRUCTIONS
from .schemas import CANDIDATE_PLANS_SCHEMA


@dataclass
class PlanOutcome:
    """What the Planner produces: candidate plans, plus the real cost of
    producing them (one LLM call regardless of candidate count). Cost is
    surfaced, not consumed — Executive owns the budget decision."""

    candidates: List[Dict[str, Any]] = field(default_factory=list)
    overall_reasoning: str = ""
    cost_usd: Optional[float] = None
    total_tokens: int = 0


class Planner:
    """Asks Hermes' LLM for 1-3 candidate tool-call sequences."""

    def __init__(self, llm_adapter: Any) -> None:
        self._llm = llm_adapter

    def plan(self, objective: str) -> PlanOutcome:
        """Return a PlanOutcome. candidates is empty only if the
        structured call failed to parse at all — a deliberate single
        empty-steps candidate (see prompt rule 5) is a valid, non-empty
        candidates list and is handled by Economics.select_best, not here."""
        kwargs: Dict[str, Any] = dict(
            instructions=PLANNER_INSTRUCTIONS,
            input=[{"type": "text", "text": objective}],
            json_schema=CANDIDATE_PLANS_SCHEMA,
            schema_name="foundry.candidate_plans",
            purpose="foundry.planner",
            temperature=0.0,
            max_tokens=4000,
        )
        model = os.environ.get("FOUNDRY_PLANNER_MODEL")
        if model:
            kwargs["model"] = model
        provider = os.environ.get("FOUNDRY_PLANNER_PROVIDER")
        if provider:
            kwargs["provider"] = provider

        result = self._llm.complete_structured(**kwargs)
        usage = getattr(result, "usage", None)
        parsed = result.parsed or {}
        return PlanOutcome(
            candidates=list(parsed.get("candidates") or []),
            overall_reasoning=parsed.get("overall_reasoning", ""),
            cost_usd=getattr(usage, "cost_usd", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
        )