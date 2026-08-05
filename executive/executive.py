"""Executive — decides what should happen, delegates it, reports whether
it succeeded. Owns no infrastructure: all LLM access and all tool
execution happen through the two adapters it's given.

Phase 1a: the Executive now enforces a budget before spending on a
Planner call. This is real ROI control (refuse to spend, not analyze
after spending) but deliberately not full Economics yet — no comparison
between alternative plans, because there's only ever one plan per
objective until Phase 2 (multi-step planning) exists. See DECISIONS.md.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from .economics import Budget
from .planner import Planner


class Executive:
    def __init__(
        self,
        llm_adapter: Any,
        tool_adapter: Any,
        budget: Optional[Budget] = None,
    ) -> None:
        self._planner = Planner(llm_adapter)
        self._tools = tool_adapter
        self._budget = budget if budget is not None else Budget()

    def run(self, objective: str) -> Dict[str, Any]:
        """End-to-end execution path: check budget, plan one step,
        delegate it through Hermes, return the outcome. Never raises —
        callers get a structured error result instead."""
        if not self._budget.try_reserve():
            return {
                "status": "budget_exceeded",
                "objective": objective,
                "budget": asdict(self._budget.status()),
            }

        outcome = self._planner.plan(objective)
        self._budget.record(outcome.cost_usd)
        budget_snapshot = asdict(self._budget.status())

        plan = outcome.plan
        if not plan or not plan.get("tool_name"):
            return {
                "status": "no_action",
                "objective": objective,
                "plan": plan,
                "reason": (plan or {}).get(
                    "reasoning", "Planner did not produce a usable plan."
                ),
                "budget": budget_snapshot,
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
                "budget": budget_snapshot,
            }

        return {
            "status": "ok",
            "objective": objective,
            "plan": plan,
            "result": tool_result,
            "budget": budget_snapshot,
        }