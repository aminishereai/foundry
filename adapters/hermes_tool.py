"""Adapter: Foundry -> Hermes tool dispatch.

Rule (Foundry Constitution): Foundry never owns tool execution or a
parallel tool registry. It only ever asks Hermes to run a tool that
Hermes already knows about.

Pure pass-through, same rationale as hermes_llm.py.
"""

from __future__ import annotations

from typing import Any, Dict


class HermesToolAdapter:
    """Translates Foundry's delegation requests into Hermes' dispatch_tool."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def dispatch(self, name: str, tool_args: Dict[str, Any]):
        """Pass-through to ctx.dispatch_tool. Runs through Hermes' normal
        approval, redaction, and budget pipelines — this is a real tool
        invocation, not a shortcut around them."""
        return self._ctx.dispatch_tool(name, tool_args)
