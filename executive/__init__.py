"""Executive subpackage — Foundry's reasoning core.

Re-exports the public classes so callers can do
`from foundry.executive import Executive` instead of reaching into
`foundry.executive.executive.Executive`.
"""

from .critic import Critic, CritiqueOutcome
from .economics import (
    Budget,
    BudgetStatus,
    CandidateScore,
    estimate_cost_usd,
    score_candidates,
    select_best,
)
from .executive import Executive
from .model_policy import call_with_fallback, tiers_for
from .opportunity_analyst import OpportunityAnalyst, OpportunityOutcome
from .planner import PlanOutcome, Planner

__all__ = [
    "Executive",
    "Planner",
    "PlanOutcome",
    "Critic",
    "CritiqueOutcome",
    "OpportunityAnalyst",
    "OpportunityOutcome",
    "Budget",
    "BudgetStatus",
    "CandidateScore",
    "estimate_cost_usd",
    "score_candidates",
    "select_best",
    "tiers_for",
    "call_with_fallback",
]
