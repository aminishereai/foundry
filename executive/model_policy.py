"""Model selection policy — an ordered, capability-first list of
model/provider pairs per role. Selection is EVIDENCE-BASED, not
predictive: each tier is actually tried; only a real failure (exception
from complete_structured) advances to the next tier. This is
deliberately not a fake "AI learning" router — no forecasting, no
scoring model, just try-then-fallback on real outcomes, per the explicit
instruction to only use measurable runtime evidence.

Tier 0 (most capable): 9Router/Kiro via Hermes' custom-provider —
genuinely frontier-tier models (Claude Opus 5, Sonnet 5, GPT-5.6) at
zero cost, but OPPORTUNISTIC: this rides a third-party proxy of someone
else's provider quota and can become unavailable or get rate-limited
without warning. Treated as "best if available," never as the only path.

Tier 1 (durable baseline): DeepSeek V4 Flash via OpenRouter — real,
accountable, paid-when-needed, has been reliable in every live test so
far.

Tier 2 (last resort): Hermes' own configured default — whatever that is,
it's guaranteed to exist.

Explicit FOUNDRY_*_MODEL/PROVIDER env vars still take priority when set:
they become tier 0, with this module's default tiers as fallback behind
them — so a manual pin still benefits from automatic fallback instead of
hard-failing if that one pinned model has a bad moment.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Inferred from the consistent {name}-provider plugin id -> {name}
# provider string pattern confirmed across every provider actually used
# so far (openrouter-provider -> "openrouter", deepseek-provider ->
# "deepseek"). Not yet directly confirmed for custom-provider — override
# via FOUNDRY_CUSTOM_PROVIDER_NAME if `hermes auth` reports a different
# string.
CUSTOM_PROVIDER_NAME = os.environ.get("FOUNDRY_CUSTOM_PROVIDER_NAME", "custom")

DEFAULT_TIERS: Dict[str, List[Dict[str, Optional[str]]]] = {
    "planner": [
        {"model": "kr/claude-opus-5", "provider": CUSTOM_PROVIDER_NAME},
        {"model": "deepseek/deepseek-v4-flash-0731", "provider": "openrouter"},
        {"model": None, "provider": None},
    ],
    "critic": [
        {"model": "kr/claude-sonnet-5", "provider": CUSTOM_PROVIDER_NAME},
        {"model": "deepseek/deepseek-v4-flash-0731", "provider": "openrouter"},
        {"model": None, "provider": None},
    ],
    "opportunity_analyst": [
        {"model": "kr/claude-opus-5", "provider": CUSTOM_PROVIDER_NAME},
        {"model": "deepseek/deepseek-v4-flash-0731", "provider": "openrouter"},
        {"model": None, "provider": None},
    ],
}


def tiers_for(role: str, env_model_var: str, env_provider_var: str) -> List[Dict[str, Optional[str]]]:
    """Ordered list of {model, provider} to try for this role. An
    explicit env var override (if set) becomes tier 0; the role's
    default tiers follow as fallback behind it."""
    tiers = list(DEFAULT_TIERS.get(role, [{"model": None, "provider": None}]))
    env_model = os.environ.get(env_model_var)
    env_provider = os.environ.get(env_provider_var)
    if env_model or env_provider:
        override = {"model": env_model, "provider": env_provider}
        tiers = [override] + [t for t in tiers if t != override]
    return tiers


def call_with_fallback(llm_adapter: Any, tiers: List[Dict[str, Optional[str]]], **kwargs: Any):
    """Try each tier's model/provider in order against
    llm_adapter.complete_structured(**kwargs, model=..., provider=...).
    Returns the first successful result. Raises the LAST tier's real
    exception if every tier genuinely fails — never fabricates a result."""
    last_exc: Optional[Exception] = None
    for tier in tiers:
        call_kwargs = dict(kwargs)
        if tier.get("model"):
            call_kwargs["model"] = tier["model"]
        if tier.get("provider"):
            call_kwargs["provider"] = tier["provider"]
        try:
            return llm_adapter.complete_structured(**call_kwargs)
        except Exception as exc:  # noqa: BLE001 — real evidence, try next tier
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No tiers available to try — this should never happen.")
