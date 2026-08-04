"""Foundry — Executive Operating System. Hermes plugin entry point.

Phase 0 scope only: register one tool (foundry_execute) that runs the
Executive end-to-end for a single objective. Everything not required for
that path (Critic, Economics, Memory, multi-step planning) deliberately
does not exist yet — see ROADMAP.md.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from . import schemas, tools
from .adapters.hermes_llm import HermesLLMAdapter
from .adapters.hermes_tool import HermesToolAdapter
from .executive.executive import Executive


def register(ctx: Any) -> None:
    """Called exactly once by Hermes at startup. If this raises, Hermes
    disables the plugin and continues running — so construction here must
    be fast and side-effect-free (no I/O, no network calls)."""
    llm_adapter = HermesLLMAdapter(ctx)
    tool_adapter = HermesToolAdapter(ctx)
    executive = Executive(llm_adapter, tool_adapter)

    ctx.register_tool(
        name="foundry_execute",
        toolset="foundry",
        schema=schemas.FOUNDRY_EXECUTE,
        handler=partial(tools.foundry_execute, executive=executive),
    )
