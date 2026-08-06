"""Budget — Phase 1a of Foundry's Economics subsystem.

Scope, deliberately minimal: track real cumulative cost across Planner
calls for this plugin's process lifetime, and refuse a new Planner call
once the configured budget is exhausted.

Explicitly NOT in scope here (see DECISIONS.md):
- ROI comparison between alternative plans — there's only ever one plan
  per objective until Phase 2 (multi-step planning) exists. Nothing to
  compare yet.
- Persistence across Hermes restarts — Foundry doesn't own storage
  infrastructure; Hermes does. A restart resets the budget. If persistent
  budgets are ever needed, they go through Hermes' memory tool, not a
  file Foundry manages itself.
- Cost estimation when the provider doesn't report it. PluginLlmUsage.cost_usd
  is documented as optional ("providers differ on what they return"). We
  never invent a number to fill that gap — an unknown cost is tracked and
  surfaced as unknown, not silently treated as zero or estimated.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass


def _default_budget_usd() -> float:
    raw = os.environ.get("FOUNDRY_SESSION_BUDGET_USD", "0.50")
    try:
        value = float(raw)
    except ValueError:
        return 0.50
    return value if value > 0 else 0.50


@dataclass
class BudgetStatus:
    limit_usd: float
    spent_usd: float
    remaining_usd: float
    cost_unknown_calls: int


class Budget:
    """Thread-safe running spend tracker.

    Hermes may invoke tools from multiple worker threads (delegated tool
    calls, background workers) against the same plugin instance, since
    register() runs once per process, not once per session. All state
    mutation is lock-protected.
    """

    def __init__(self, limit_usd: float | None = None) -> None:
        self._limit_usd = limit_usd if limit_usd is not None else _default_budget_usd()
        self._spent_usd = 0.0
        self._cost_unknown_calls = 0
        self._lock = threading.Lock()

    def try_reserve(self) -> bool:
        """Check whether a new call is affordable. Real cost is only
        known after the call returns — see record(). This is a
        pre-check, not a hold on funds."""
        with self._lock:
            return self._spent_usd < self._limit_usd

    def record(self, cost_usd: float | None) -> None:
        """Record the real cost of a completed call.

        cost_usd of None means the provider didn't report a cost. We
        never fabricate a substitute figure — it's counted separately as
        an unknown-cost call so the budget stays honest about what it
        actually knows.
        """
        with self._lock:
            if cost_usd is None:
                self._cost_unknown_calls += 1
                return
            self._spent_usd += cost_usd

    def status(self) -> BudgetStatus:
        with self._lock:
            return BudgetStatus(
                limit_usd=self._limit_usd,
                spent_usd=self._spent_usd,
                remaining_usd=max(0.0, self._limit_usd - self._spent_usd),
                cost_unknown_calls=self._cost_unknown_calls,
            )


@dataclass
class CandidateScore:
    """Score for one candidate plan. score = confidence / max(1, step_count).

    Deliberately NOT a dollar-cost comparison — Foundry has no way to know
    a tool call's real dollar cost before dispatching it (Hermes owns that
    pipeline, not Foundry), so inventing a cost estimate here would violate
    the same honesty principle Budget already applies via
    cost_unknown_calls. Step count is the real, available proxy for cost
    and risk: more tool calls means more time, more chances to fail, more
    actual future spend. Confidence is the Planner's own honest estimate,
    self-reported per candidate.
    """

    index: int
    approach_summary: str
    confidence: float
    step_count: int
    score: float


def score_candidates(candidates: list) -> list[CandidateScore]:
    """Score every candidate. Confidence values are clamped to [0, 1] —
    a candidate's self-reported confidence is not trusted blindly."""
    scored : list[CandidateScore] = []
    for i, candidate in enumerate(candidates):
        steps = candidate.get("steps") or []
        try:
            confidence = float(candidate.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        step_count = len(steps)
        score = confidence / max(1, step_count)
        scored.append(
            CandidateScore(
                index=i,
                approach_summary=candidate.get("approach_summary", ""),
                confidence=confidence,
                step_count=step_count,
                score=score,
            )
        )
    return scored


def select_best(candidates: list):
    """Return (best_candidate_dict_or_None, best_score_or_None, all_scores).
    Deterministic, no extra LLM call — this is real ROI selection, not
    another round of inference. Ties: fewer steps wins, then first-listed
    wins."""
    if not candidates:
        return None, None, []
    scores = score_candidates(candidates)
    best = max(scores, key=lambda s: (s.score, -s.step_count, -s.index))
    return candidates[best.index], best, scores
