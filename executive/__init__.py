"""Executive subpackage — Foundry's reasoning core.

Re-exports the public classes so callers can do
`from foundry.executive import Executive` instead of reaching into
`foundry.executive.executive.Executive`.
"""

from .critic import Critic, CritiqueOutcome
from .capital_ledger import CapitalLedger
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
from .opportunity_backlog import OpportunityBacklog, filter_entries, rank_by_confidence
from .planner import PlanOutcome, Planner
from .scorecard import Scorecard

__all__ = [
    "Executive",
    "Planner",
    "PlanOutcome",
    "Critic",
    "CritiqueOutcome",
    "OpportunityAnalyst",
    "OpportunityOutcome",
    "OpportunityBacklog",
    "filter_entries",
    "rank_by_confidence",
    "CapitalLedger",
    "Scorecard",
    "Budget",
    "BudgetStatus",
    "CandidateScore",
    "estimate_cost_usd",
    "score_candidates",
    "select_best",
    "tiers_for",
    "call_with_fallback",
]