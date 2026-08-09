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

import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .critic import Critic
from .economics import Budget, select_best
from .opportunity_analyst import OpportunityAnalyst
from .planner import Planner

MAX_DISPATCH_ATTEMPTS = 2  # 1 initial attempt + 1 retry
RETRY_BACKOFF_SECONDS = 1.0

# Hermes' real persistent memory file — confirmed via source inspection,
# not an invented path. Computed dynamically (not hardcoded to a
# specific home directory) so this works regardless of which OS user
# Hermes runs as.
MEMORY_FILE_PATH = os.path.expanduser("~/.hermes/memories/MEMORY.md")
MEMORY_CONTEXT_CHAR_LIMIT = 2000  # bounded, same order of magnitude as
# Hermes' own memory_char_limit config (2200) — not arbitrary

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
        self._opportunity_analyst = OpportunityAnalyst(llm_adapter)
        self._tools = tool_adapter
        self._budget = budget if budget is not None else Budget()

    def _read_memory_context(self) -> str:
        """Best-effort read of Hermes' real persistent memory file, so
        the Planner can be aware of past lessons (e.g. objectives that
        previously came back not_satisfied). Never blocks or fails
        planning — returns empty string on any error, since memory
        context is an enhancement, not a dependency."""
        try:
            raw = self._tools.dispatch("read_file", {"path": MEMORY_FILE_PATH})
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            content = parsed.get("content", "") if isinstance(parsed, dict) else ""
            return content[:MEMORY_CONTEXT_CHAR_LIMIT] if content else ""
        except Exception:  # noqa: BLE001 — best-effort, never fatal
            return ""

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

        outcome = self._planner.plan(objective, memory_context=self._read_memory_context())
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

    def research_opportunity(self, query: str, confirm_destructive: bool = False) -> Dict[str, Any]:
        """Internet Graveyard vertical slice. Reuses run() UNMODIFIED for
        the real research phase (web_search/web_extract via the normal
        Planner/dispatch loop — no new execution logic exists here). Only
        after real research results exist does OpportunityAnalyst
        synthesize a grounded hypothesis from them — never before, so
        nothing is fabricated ahead of the actual search happening.
        Persists via Hermes' real memory tool, best-effort."""
        research_objective = (
            f"Search the web for a real failed, shut-down, or abandoned "
            f"software business related to: {query}. Then fetch/extract "
            f"enough real detail to understand why it failed."
        )
        exec_result = self.run(research_objective, confirm_destructive=confirm_destructive)

        if exec_result.get("status") != "ok" or not exec_result.get("executed_steps"):
            return {
                "status": "research_failed",
                "query": query,
                "reason": (
                    exec_result.get("reason")
                    or exec_result.get("error")
                    or f"Research did not complete (status={exec_result.get('status')})."
                ),
                "research_result": exec_result,
            }

        if not self._budget.try_reserve():
            return {
                "status": "budget_exceeded",
                "query": query,
                "research_result": exec_result,
                "budget": exec_result.get("budget"),
            }

        outcome = self._opportunity_analyst.analyze(query, exec_result["executed_steps"])
        self._budget.record(
            outcome.cost_usd,
            model=outcome.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
        )
        budget_snapshot = asdict(self._budget.status())

        if not outcome.hypothesis:
            return {
                "status": "synthesis_failed",
                "query": query,
                "reason": "Opportunity Analyst did not return a valid structured hypothesis.",
                "research_steps": exec_result["executed_steps"],
                "budget": budget_snapshot,
            }

        persisted = False
        try:
            h = outcome.hypothesis
            lesson = (
                f"Opportunity hypothesis (query: '{query[:80]}'): "
                f"{h.get('problem', '')[:150]} | "
                f"failure_category={h.get('failure_category')} | "
                f"confidence={h.get('confidence')} | "
                f"resurrection: {h.get('resurrection_hypothesis', '')[:200]}"
            )
            self._tools.dispatch("memory", {"target": "memory", "action": "add", "content": lesson})
            persisted = True
        except Exception:  # noqa: BLE001 — best-effort, never fatal
            persisted = False

        return {
            "status": "ok",
            "query": query,
            "hypothesis": outcome.hypothesis,
            "persisted": persisted,
            "research_steps": exec_result["executed_steps"],
            "budget": budget_snapshot,
        }
