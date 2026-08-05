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