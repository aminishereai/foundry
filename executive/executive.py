"""Executive — decides what should happen, delegates it, reports whether
it succeeded. Owns no infrastructure: all LLM access and all tool
execution happen through the two adapters it's given.

Phase 3: after a successful execution, the Critic reviews the real
results (one more LLM call, budget-gated same as planning) and the
verdict is attached to the result. The Critic never changes what already
happened — it only judges it. If budget is exhausted, critique is
skipped and marked as such, never silently faked.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .critic import Critic
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
        self._critic = Critic(llm_adapter)
        self._tools = tool_adapter
        self._budget = budget if budget is not None else Budget()

    def run(self, objective: str) -> Dict[str, Any]:
        """End-to-end execution path: check budget, get candidate plans,
        select the best by ROI score, execute its steps through Hermes in
        order (stop on first failure), then critique a successful result
        if budget allows. Never raises — callers get a structured error
        result instead."""
        if not self._budget.try_reserve():
            return {
                "status": "budget_exceeded",
                "objective": objective,
                "budget": asdict(self._budget.status()),
            }

        outcome = self._planner.plan(objective)
        self._budget.record(
            outcome.cost_usd,
            model=outcome.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
        )

        best_candidate, best_score, scores = select_best(outcome.candidates)
        considered = [asdict(s) for s in scores]

        if best_candidate is None:
            return {
                "status": "no_action",
                "objective": objective,
                "reason": outcome.overall_reasoning
                or "Planner did not produce any usable candidates.",
                "considered_candidates": considered,
                "budget": asdict(self._budget.status()),
            }

        steps = best_candidate.get("steps") or []
        selected_summary = {
            "approach_summary": getattr(best_score ,"approach_summary" , ""),
            "confidence": getattr(best_score, "confidence" , 0.0),
        }

        if not steps:
            return {
                "status": "no_action",
                "objective": objective,
                "reason": outcome.overall_reasoning
                or "The best-scoring candidate was to take no action.",
                "selected_candidate": selected_summary,
                "considered_candidates": considered,
                "budget": asdict(self._budget.status()),
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
                    "budget": asdict(self._budget.status()),
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
                    "budget": asdict(self._budget.status()),
                }

            executed_steps.append({
                "step_index": index,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "reasoning": reasoning,
                "status": "ok",
                "result": tool_result,
            })

        # All steps succeeded. Critique what actually happened, budget permitting.
        if self._budget.try_reserve():
            critique_outcome = self._critic.review(objective, executed_steps)
            self._budget.record(
                critique_outcome.cost_usd,
                model=critique_outcome.model,
                input_tokens=critique_outcome.input_tokens,
                output_tokens=critique_outcome.output_tokens,
            )
            critique_block: Dict[str, Any] = {
                "verdict": critique_outcome.verdict,
                "critique": critique_outcome.critique,
            }
        else:
            critique_block = {"skipped": "budget_exceeded"}

        return {
            "status": "ok",
            "objective": objective,
            "executed_steps": executed_steps,
            "selected_candidate": selected_summary,
            "considered_candidates": considered,
            "critique": critique_block,
            "budget": asdict(self._budget.status()),
        }