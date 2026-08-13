"""Hermes-facing tool schema.

This is the ONLY schema Hermes' model sees for Foundry in Phase 0. It
describes the single entry point into the Executive. Internal schemas
(e.g. what the Planner's own structured LLM call returns) live in
executive/schemas.py — the model never sees those directly.
"""

FOUNDRY_EXECUTE = {
    "name": "foundry_execute",
    "description": (
        "Hand an objective to Foundry's Executive. The Executive proposes "
        "candidate plans, picks the best by confidence-per-step, executes "
        "it through Hermes, and critiques the real result. Use this when "
        "the caller wants executive-level reasoning about WHAT to do next, "
        "not when the tool to call is already known — call it directly in "
        "that case. If the selected plan includes a destructive/irreversible "
        "tool (terminal, execute_code, write_file, patch, delegate_task, "
        "cronjob, computer_use), it will NOT run automatically — the call "
        "returns status='confirmation_required' with the full plan instead. "
        "Re-call with confirm_destructive=true only after a human has "
        "reviewed and approved that specific plan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "objective": {
                "type": "string",
                "description": (
                    "A single, concrete objective for the Executive to "
                    "act on, e.g. 'list the files in the current project "
                    "directory' or 'find recent news about X'."
                ),
            },
            "confirm_destructive": {
                "type": "boolean",
                "description": (
                    "Set true ONLY after a human has explicitly reviewed and "
                    "approved a plan previously returned with "
                    "status='confirmation_required'. Defaults to false — "
                    "destructive tool calls are refused by default."
                ),
                "default": False,
            },
        },
        "required": ["objective"],
    },
}

FOUNDRY_DISCOVER_OPPORTUNITY = {
    "name": "foundry_discover_opportunity",
    "description": (
        "Internet Graveyard: search for a real failed, shut-down, or "
        "abandoned software business related to a query, research why it "
        "failed using real Hermes web tools, and synthesize ONE grounded "
        "opportunity hypothesis — never fabricated, always grounded in "
        "the real research — including explicit facts/estimates/"
        "assumptions/unknowns and the cheapest real validation "
        "experiment. If the underlying research plan needs a destructive "
        "tool, it is gated the same way foundry_execute is."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "What kind of failed business to look for, e.g. "
                    "'B2B SaaS scheduling tools' or 'consumer meal kit "
                    "startups'."
                ),
            },
            "confirm_destructive": {
                "type": "boolean",
                "default": False,
                "description": "Same semantics as foundry_execute's confirm_destructive.",
            },
        },
        "required": ["query"],
    },
}

FOUNDRY_LIST_OPPORTUNITIES = {
    "name": "foundry_list_opportunities",
    "description": (
        "Read-only query over Foundry's opportunity backlog (its "
        "knowledge base of researched hypotheses). No LLM call, no cost. "
        "Ranked by the hypothesis's own honestly-reported confidence. "
        "Use this to see what's actually in the portfolio before "
        "deciding what to validate or pursue further."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Optional filter: 'new', 'validation_attempted'.",
            },
            "min_confidence": {
                "type": "number",
                "description": "Optional filter: only opportunities at or above this confidence (0.0-1.0).",
            },
            "failure_category": {
                "type": "string",
                "description": "Optional filter, e.g. 'bad_economics', 'bad_timing'.",
            },
        },
    },
}

FOUNDRY_VALIDATE_OPPORTUNITY = {
    "name": "foundry_validate_opportunity",
    "description": (
        "Research-validate a specific opportunity already in the "
        "backlog (from foundry_discover_opportunity) by investigating "
        "its cheapest_validation_experiment through real web research. "
        "This is deeper research, NOT posting to real external services "
        "or spending real money — it reuses foundry_execute's own gated "
        "loop, so any destructive step inside it still requires "
        "confirm_destructive=true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "integer",
                "description": "The id field from foundry_list_opportunities.",
            },
            "confirm_destructive": {
                "type": "boolean",
                "default": False,
            },
        },
        "required": ["opportunity_id"],
    },
}

FOUNDRY_CAPITAL = {
    "name": "foundry_capital",
    "description": (
        "Record a REAL, human-reported cost or revenue figure against "
        "the capital ledger, or get a summary. Foundry has no payment/"
        "bank integration and never estimates or fabricates a figure — "
        "amounts must be reported by a human (you)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["record", "summary"],
                "description": "'record' to log a real cost/revenue entry, 'summary' to get totals.",
            },
            "entry_type": {
                "type": "string",
                "enum": ["cost", "revenue"],
                "description": "Required for action='record'.",
            },
            "amount_usd": {
                "type": "number",
                "description": "Required for action='record'. Must be a real, known figure.",
            },
            "description": {
                "type": "string",
                "description": "Required for action='record'. What this cost/revenue was for.",
            },
            "opportunity_id": {
                "type": "integer",
                "description": "Optional: link this entry to a specific backlog opportunity.",
            },
        },
        "required": ["action"],
    },
}
