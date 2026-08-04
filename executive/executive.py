"""Executive — decides what should happen, delegates it, reports whether
it succeeded. Owns no infrastructure: all LLM access and all tool
execution happen through the two adapters it's given.
"""

from __future__ import annotations

from typing import Any, Dict

from .planner import Planner


class Executive:
    def __init__(self, llm_adapter: Any, tool_adapter: Any) -> None:
        self._planner = Planner(llm_adapter)
        self._tools = tool_adapter

    def run(self, objective: str) -> Dict[str, Any]:
        """End-to-end Phase 0 execution path: plan one step, delegate it
        through Hermes, return the outcome. Never raises — callers get a
        structured error result instead."""
        plan = self._planner.plan(objective)

        if not plan or not plan.get("tool_name"):
            return {
                "status": "no_action",
                "objective": objective,
                "plan": plan,
                "reason": (plan or {}).get(
                    "reasoning", "Planner did not produce a usable plan."
                ),
            }

        try:
            tool_result = self._tools.dispatch(
                plan["tool_name"], plan.get("tool_args", {})
            )
        except Exception as exc:  # noqa: BLE001 — report, don't crash the tool loop
            return {
                "status": "error",
                "stage": "execution",
                "objective": objective,
                "plan": plan,
                "error": str(exc),
            }

        return {
            "status": "ok",
            "objective": objective,
            "plan": plan,
            "result": tool_result,
        }
