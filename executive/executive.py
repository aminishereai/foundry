"""Executive — decides what should happen, delegates it, reports whether
it succeeded. Owns no infrastructure: all LLM access and all tool
execution happen through the two adapters it's given.

Phase 1b: the Planner now proposes candidates; the Executive picks the
winner via Economics.select_best (confidence-per-step scoring, no extra
LLM call) before executing anything. Every result includes
considered_candidates so the decision is auditable, not a black box.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .economics import Budget, select_best
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
        """End-to-end execution path: check budget, get candidate plans
        (one Planner LLM call), select the best by ROI score, execute its
        steps through Hermes in order, stop on first failure. Never
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

        best_candidate, best_score, scores = select_best(outcome.candidates)
        considered = [asdict(s) for s in scores]

        if best_candidate is None:
            return {
                "status": "no_action",
                "objective": objective,
                "reason": outcome.overall_reasoning
                or "Planner did not produce any usable candidates.",
                "considered_candidates": considered,
                "budget": budget_snapshot,
            }

        steps = best_candidate.get("steps") or []
        selected_summary = {
            "approach_summary": getattr(best_score, "approach_summary", ""),
            "confidence": getattr(best_score, "confidence", 0.0),
        }

        if not steps:
            return {
                "status": "no_action",
                "objective": objective,
                "reason": outcome.overall_reasoning
                or "The best-scoring candidate was to take no action.",
                "selected_candidate": selected_summary,
                "considered_candidates": considered,
                "budget": budget_snapshot,
            }

        executed_steps: List[Dict[str, Any]] = []
        for index, step in enumerate(steps):
            tool_name = step.get("tool_name")
            tool_args = step.get("tool_args", {})
            reasoning = step.get("reasoning", "")

            if not tool_name:
                return {
                    "status": "error",
                    "stage": "planning",
                    "objective": objective,
                    "error": f"Step {index} has no tool_name.",
                    "executed_steps": executed_steps,
                    "selected_candidate": selected_summary,
                    "considered_candidates": considered,
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
                    "executed_steps": executed_steps,
                    "failed_at_step": index,
                    "selected_candidate": selected_summary,
                    "considered_candidates": considered,
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
            "executed_steps": executed_steps,
            "selected_candidate": selected_summary,
            "considered_candidates": considered,
            "budget": budget_snapshot,
        }
