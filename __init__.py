"""Foundry — Executive Operating System. Hermes plugin entry point.

Registers two tools sharing one Executive/Budget instance (unified
spend tracking across both capabilities):
- foundry_execute: general objective execution (Planner/ROI/retry/
  safety-gate/Critic).
- foundry_discover_opportunity: Internet Graveyard vertical slice —
  reuses foundry_execute's entire loop for real research, then
  synthesizes a grounded opportunity hypothesis via OpportunityAnalyst.
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

    ctx.register_tool(
        name="foundry_discover_opportunity",
        toolset="foundry",
        schema=schemas.FOUNDRY_DISCOVER_OPPORTUNITY,
        handler=partial(tools.foundry_discover_opportunity, executive=executive),
    )

    ctx.register_tool(
        name="foundry_list_opportunities",
        toolset="foundry",
        schema=schemas.FOUNDRY_LIST_OPPORTUNITIES,
        handler=partial(tools.foundry_list_opportunities, executive=executive),
    )

    ctx.register_tool(
        name="foundry_validate_opportunity",
        toolset="foundry",
        schema=schemas.FOUNDRY_VALIDATE_OPPORTUNITY,
        handler=partial(tools.foundry_validate_opportunity, executive=executive),
    )

    ctx.register_tool(
        name="foundry_capital",
        toolset="foundry",
        schema=schemas.FOUNDRY_CAPITAL,
        handler=partial(tools.foundry_capital, executive=executive),
    )

    ctx.register_tool(
        name="foundry_scorecard",
        toolset="foundry",
        schema=schemas.FOUNDRY_SCORECARD,
        handler=partial(tools.foundry_scorecard, executive=executive),
    )