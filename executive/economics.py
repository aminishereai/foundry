"""Budget — Foundry's Economics subsystem.

Real cost (PluginLlmUsage.cost_usd) is documented as optional and, as of
this Hermes version, is confirmed via source inspection to be
structurally never populated at all (agent/plugin_llm.py::_extract_usage
fills every usage field except cost_usd, for every provider, always).
Waiting on the host to supply it isn't viable right now.

Fallback: token counts (input_tokens/output_tokens) ARE reliably
populated. When real cost is unavailable, Budget estimates cost from
real token counts times a known per-model published price. This is
still honest: estimated cost is tracked SEPARATELY from real cost, never
blended into one number, and a model with no known price is left
genuinely unknown rather than guessed at. See PRICING_USD_PER_MILLION
below — only models with real, published pricing are listed; nothing is
invented.

Explicitly NOT in scope here (see DECISIONS.md):
- ROI comparison between alternative plans — see CandidateScore below,
  scored by confidence-per-step, not dollar cost, since a tool call's
  real dollar cost still isn't knowable before dispatch.
- Persistence across Hermes restarts — Foundry doesn't own storage
  infrastructure; Hermes does.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional


def _default_budget_usd() -> float:
    raw = os.environ.get("FOUNDRY_SESSION_BUDGET_USD", "0.50")
    try:
        value = float(raw)
    except ValueError:
        return 0.50
    return value if value > 0 else 0.50


# (input_price, output_price) in USD per 1,000,000 tokens. Only real,
# published prices go here — an unlisted model stays genuinely unknown,
# never guessed. Sourced from OpenRouter's public pricing (checked
# 2026-08). Free-tier models (":free" suffix) are $0 by definition of
# the tier, not a guess — handled separately in estimate_cost_usd, not
# listed individually here.
PRICING_USD_PER_MILLION = {
    "deepseek/deepseek-v4-flash-0731": (0.09, 0.18),
    "deepseek/deepseek-v4-flash": (0.084, 0.168),
    "deepseek/deepseek-v4-flash-0423": (0.084, 0.168),
    "deepseek/deepseek-v4-pro": (0.435, 0.87),
}


def estimate_cost_usd(
    model: Optional[str], input_tokens: int, output_tokens: int
) -> Optional[float]:
    """Estimate cost from real token counts and known published pricing.
    Returns None (genuinely unknown, not zero) if the model has no
    pricing entry — never invents a number for an unlisted model."""
    if not model:
        return None
    if model.endswith(":free"):
        return 0.0
    pricing = PRICING_USD_PER_MILLION.get(model)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return (input_tokens / 1_000_000) * input_price + (
        output_tokens / 1_000_000
    ) * output_price


@dataclass
class BudgetStatus:
    limit_usd: float
    spent_usd: float  # sum of REAL host-reported costs only
    estimated_usd: float  # sum of token-based ESTIMATED costs, tracked separately
    remaining_usd: float  # limit - (spent_usd + estimated_usd)
    real_cost_calls: int
    estimated_cost_calls: int
    cost_unknown_calls: int  # no real cost AND no pricing entry for the model used


class Budget:
    """Thread-safe running spend tracker.

    Hermes may invoke tools from multiple worker threads against the
    same plugin instance, since register() runs once per process, not
    once per session. All state mutation is lock-protected.
    """

    def __init__(self, limit_usd: float | None = None) -> None:
        self._limit_usd = limit_usd if limit_usd is not None else _default_budget_usd()
        self._spent_usd = 0.0
        self._estimated_usd = 0.0
        self._real_cost_calls = 0
        self._estimated_cost_calls = 0
        self._cost_unknown_calls = 0
        self._lock = threading.Lock()

    def try_reserve(self) -> bool:
        """Check whether a new call is affordable, counting both real and
        estimated spend against the limit. Pre-check only, not a hold."""
        with self._lock:
            return (self._spent_usd + self._estimated_usd) < self._limit_usd

    def record(
        self,
        cost_usd: Optional[float],
        *,
        model: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record the cost of a completed call.

        Priority: real cost_usd if the host ever provides it (future-
        proof, in case a later Hermes version populates it) > token-based
        estimate from known pricing > genuinely unknown. Real and
        estimated are tallied separately — never blended into one figure
        that would misrepresent how certain the number is.
        """
        with self._lock:
            if cost_usd is not None:
                self._spent_usd += cost_usd
                self._real_cost_calls += 1
                return
            estimate = estimate_cost_usd(model, input_tokens, output_tokens)
            if estimate is not None:
                self._estimated_usd += estimate
                self._estimated_cost_calls += 1
                return
            self._cost_unknown_calls += 1

    def status(self) -> BudgetStatus:
        with self._lock:
            total = self._spent_usd + self._estimated_usd
            return BudgetStatus(
                limit_usd=self._limit_usd,
                spent_usd=self._spent_usd,
                estimated_usd=self._estimated_usd,
                remaining_usd=max(0.0, self._limit_usd - total),
                real_cost_calls=self._real_cost_calls,
                estimated_cost_calls=self._estimated_cost_calls,
                cost_unknown_calls=self._cost_unknown_calls,
            )


@dataclass
class CandidateScore:
    """Score for one candidate plan. score = confidence / max(1, step_count).

    Still not a dollar-cost comparison — a candidate's real dollar cost
    isn't knowable before its tool calls actually dispatch. Step count
    remains the real, available proxy for cost/risk at selection time.
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
    Deterministic, no extra LLM call. Ties: fewer steps wins, then
    first-listed wins."""
    if not candidates:
        return None, None, []
    scores = score_candidates(candidates)
    best = max(scores, key=lambda s: (s.score, -s.step_count, -s.index))
    return candidates[best.index], best, scores