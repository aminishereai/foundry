"""Executive — decides what should happen, delegates it, reports whether
it succeeded. Owns no infrastructure: all LLM access and all tool
execution happen through the two adapters it's given.

Phase 2: executes a Planner-produced sequence of 1-4 steps in order,
stopping immediately on the first failure. No retry, no recovery, no
skipping ahead — that's Phase 4 (Executive Runtime). This is
intentionally the simplest correct thing: run each step, record what
happened, stop the moment something breaks.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

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
        """End-to-end execution path: check budget, plan a step sequence
        (one Planner LLM call regardless of sequence length), execute
        each step through Hermes in order, stop on first failure. Never
        raises — callers get a structured error result instead."""
        if not self._budget.try_reserve():
            return {
                "status": "budget_exceeded",
                "objective": objective,
                "budget": asdict(self._budget.status()),
            }

        outcome = self._planner.plan(objective)
        self._budget.record(outcome.cost_usd)
        budget_snapshot = asdict(self._budget.status())

        if not outcome.steps:
            return {
                "status": "no_action",
                "objective": objective,
                "reason": outcome.overall_reasoning
                or "Planner did not produce a usable plan.",
                "budget": budget_snapshot,
            }

        executed_steps: List[Dict[str, Any]] = []
        for index, step in enumerate(outcome.steps):
            tool_name = step.get("tool_name")
            tool_args = step.get("tool_args", {})
            reasoning = step.get("reasoning", "")

            if not tool_name:
                return {
                    "status": "error",
                    "stage": "planning",
                    "objective": objective,
                    "overall_reasoning": outcome.overall_reasoning,
                    "error": f"Step {index} has no tool_name.",
                    "executed_steps": executed_steps,
                    "budget": budget_snapshot,
                }

            try:
                tool_result = self._tools.dispatch(tool_name, tool_args)
            except Exception as exc:  # noqa: BLE001 — report, don't crash the tool loop
                executed_steps.append({
                    "step_index": index,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "reasoning": reasoning,
                    "status": "error",
                    "error": str(exc),
                })
                return {
                    "status": "error",
                    "stage": "execution",
                    "objective": objective,
                    "overall_reasoning": outcome.overall_reasoning,
                    "executed_steps": executed_steps,
                    "failed_at_step": index,
                    "budget": budget_snapshot,
                }

            executed_steps.append({
                "step_index": index,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "reasoning": reasoning,
                "status": "ok",
                "result": tool_result,
            })

        return {
            "status": "ok",
            "objective": objective,
            "overall_reasoning": outcome.overall_reasoning,
            "executed_steps": executed_steps,
            "budget": budget_snapshot,
        }
