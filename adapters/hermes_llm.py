"""Adapter: Foundry -> Hermes LLM access.

Rule (Foundry Constitution): Foundry never owns an LLM, never talks to a
provider SDK directly, and never instantiates its own credentials. Every
reasoning call flows through Hermes' ctx.llm.

This adapter is deliberately a pass-through. It carries no prompts, no
schemas, no decision logic — that belongs to the Executive/Planner layer.
If you find yourself adding a prompt or a policy decision here, it
belongs one layer up instead.
"""

from __future__ import annotations

from typing import Any, Dict


class HermesLLMAdapter:
    """Translates Foundry's LLM requests into Hermes' ctx.llm calls."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def complete_structured(self, **kwargs: Dict[str, Any]):
        """Pass-through to ctx.llm.complete_structured. See Hermes docs
        for the full kwarg surface (instructions, input, json_schema,
        purpose, temperature, max_tokens, ...)."""
        return self._ctx.llm.complete_structured(**kwargs)

    # NOTE: ctx.llm.complete() (plain chat, non-structured) is not wired
    # here. Nothing in Phase 0's execution path uses it. Add it when a
    # real caller needs it (e.g. Critic in Phase 3) — not before.
