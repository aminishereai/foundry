"""Executive — decides what should happen, delegates it, reports whether
it succeeded. Owns no infrastructure: all LLM access and all tool
execution happen through the two adapters it's given.

Phase 4 (minimal slice):
- Retry: a step whose dispatch call raises (transient failure — network
  blip, momentary tool unavailability) gets ONE retry after a short
  backoff before the run gives up. A step whose dispatch SUCCEEDS but
  whose own result contains a logical error (e.g. "File not found") is
  NOT retried — that's a permanent failure, retrying it wastes budget on
  something a second attempt can't fix. Real recovery/re-planning stays
  out of scope; this is bounded resilience to transient failures only.
- Safety gate: Hermes calls this handler synchronously and expects one
  immediate return — there's no way to pause mid-call and wait for a
  human. So the honest gate is: if the selected plan includes a
  destructive/irreversible tool and confirm_destructive wasn't passed,
  nothing is dispatched at all. The full plan is returned with
  status='confirmation_required' for a human to review before re-calling
  with confirm_destructive=true.

Phase 3: Critic reviews real results after success, budget-gated,
never fakes a critique if budget runs out.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .critic import Critic
from .economics import Budget, select_best
from .planner import Planner

MAX_DISPATCH_ATTEMPTS = 2  # 1 initial attempt + 1 retry
RETRY_BACKOFF_SECONDS = 1.0

# Tools whose effects are hard or impossible to undo. Conservative by
# design — a false positive here just costs one confirmation round trip;
# a false negative means an irreversible action ran unsupervised.
DESTRUCTIVE_TOOLS = {
    "terminal",
    "execute_code",
    "write_file",
    "patch",
    "delegate_task",
    "cronjob",
    "computer_use",
}


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

    def run(self, objective: str, confirm_destructive: bool = False) -> Dict[str, Any]:
        """End-to-end execution path: check budget, get candidate plans,
        select the best by ROI score, gate on destructive tools, execute
        steps through Hermes in order (retry once on transient failure,
        stop on repeated/logical failure), then critique a successful
        result if budget allows. Never raises."""
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
        budget_snapshot = asdict(self._budget.status())

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
            "approach_summary": getattr(best_score ,"approach_summary" , ""),
            "confidence": getattr(best_score ,"confidence" , 0.0),
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

        destructive_steps = [
            s.get("tool_name") for s in steps if s.get("tool_name") in DESTRUCTIVE_TOOLS
        ]
        if destructive_steps and not confirm_destructive:
            return {
                "status": "confirmation_required",
                "objective": objective,
                "reason": (
                    f"Plan includes destructive tool(s) {sorted(set(destructive_steps))}. "
                    "Nothing was executed. Re-call foundry_execute with "
                    "confirm_destructive=true after human review to proceed."
                ),
                "proposed_steps": steps,
                "overall_reasoning": outcome.overall_reasoning,
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

            last_exc: Optional[Exception] = None
            tool_result = None
            attempts = 0
            while attempts < MAX_DISPATCH_ATTEMPTS:
                attempts += 1
                try:
                    tool_result = self._tools.dispatch(tool_name, tool_args)
                    last_exc = None
                    break
                except Exception as exc:  # noqa: BLE001 — report, don't crash the tool loop
                    last_exc = exc
                    if attempts < MAX_DISPATCH_ATTEMPTS:
                        time.sleep(RETRY_BACKOFF_SECONDS)

            if last_exc is not None:
                executed_steps.append({
                    "step_index": index,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "reasoning": reasoning,
                    "status": "error",
                    "error": str(last_exc),
                    "attempts": attempts,
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
                "attempts": attempts,
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
                "verdict": critique_outcome.verdict or "critique_unavailable",
                "critique": critique_outcome.critique
                or "Critic call did not return a valid structured verdict (empty or malformed response from the model).",
            }

            # Best-effort: log a lesson via Hermes' real memory tool only
            # when the Critic found a genuine gap — not routine successes.
            # Foundry decides WHAT is worth remembering; Hermes owns the
            # actual storage. Never blocks or fails the main result — a
            # memory-write failure is a side-effect failure, not a
            # execution failure.
            memory_logged = False
            if critique_outcome.verdict in ("not_satisfied", "partially_satisfied"):
                try:
                    lesson = (
                        f"Foundry: objective '{objective[:100]}' was "
                        f"{critique_outcome.verdict} — {critique_outcome.critique[:200]}"
                    )
                    self._tools.dispatch("memory", {
                        "target": "memory",
                        "action": "add",
                        "content": lesson,
                    })
                    memory_logged = True
                except Exception:  # noqa: BLE001 — best-effort, never fatal
                    memory_logged = False
            critique_block["memory_logged"] = memory_logged
        else:
            critique_block = {"skipped": "budget_exceeded", "memory_logged": False}

        return {
            "status": "ok",
            "objective": objective,
            "executed_steps": executed_steps,
            "selected_candidate": selected_summary,
            "considered_candidates": considered,
            "critique": critique_block,
            "budget": asdict(self._budget.status()),
        }
        