"""Internal schemas used by Foundry's own structured LLM calls.

These are never registered with Hermes and never seen by the user-facing
model — they only shape the JSON Foundry asks its Planner's LLM call to
return via ctx.llm.complete_structured.
"""

CANDIDATE_PLANS_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "description": (
                "1-3 genuinely different candidate approaches. Do not "
                "invent artificial alternatives just to fill slots — one "
                "honest candidate beats three fabricated ones."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "approach_summary": {
                        "type": "string",
                        "description": "A few words naming this approach.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": (
                            "0.0-1.0: honest estimate of how likely this "
                            "exact step sequence, if executed, fully "
                            "satisfies the objective. Do not inflate — "
                            "the Executive picks between candidates using "
                            "this number."
                        ),
                    },
                    "steps": {
                        "type": "array",
                        "description": (
                            "Ordered sequence of 0-4 tool calls for this "
                            "candidate. Empty means this candidate is "
                            "'take no action'."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "description": (
                                        "Must be one of the names confirmed "
                                        "in tools/registry.py (e.g. "
                                        "'read_file', 'search_files', "
                                        "'terminal', 'execute_code', "
                                        "'delegate_task')."
                                    ),
                                },
                                "tool_args": {
                                    "type": "object",
                                    "description": "Arguments for this tool, in the shape that tool expects.",
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "One short sentence on why this step is needed.",
                                },
                            },
                            "required": ["tool_name", "tool_args", "reasoning"],
                        },
                    },
                },
                "required": ["approach_summary", "confidence", "steps"],
            },
        },
        "overall_reasoning": {
            "type": "string",
            "description": "One or two sentences on the tradeoff between candidates, or why only one was proposed.",
        },
    },
    "required": ["candidates", "overall_reasoning"],
}

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["satisfied", "partially_satisfied", "not_satisfied"],
            "description": (
                "Honest judgment of whether the executed steps actually "
                "achieved the objective, based on their real results."
            ),
        },
        "critique": {
            "type": "string",
            "description": (
                "One or two sentences explaining the verdict, referencing "
                "what actually happened, not what the steps intended to do."
            ),
        },
    },
    "required": ["verdict", "critique"],
}

OPPORTUNITY_HYPOTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {
            "type": "string",
            "description": "The real problem the failed business was solving, grounded only in the research provided.",
        },
        "target_customer": {"type": "string"},
        "business_model_summary": {"type": "string"},
        "why_it_failed": {
            "type": "string",
            "description": "Grounded in the research. If the research doesn't clearly say why, state that explicitly rather than guessing.",
        },
        "failure_category": {
            "type": "string",
            "enum": [
                "bad_idea", "bad_execution", "bad_timing", "bad_distribution",
                "bad_economics", "capital_constraint", "technology_limitation",
                "market_change", "unclear_from_research",
            ],
        },
        "assumption_that_may_have_changed": {
            "type": "string",
            "description": "What assumption behind the original failure might no longer hold today. May be empty if none is evident.",
        },
        "resurrection_hypothesis": {
            "type": "string",
            "description": "One or two sentences: could this be viable now, and why. Must be labeled as a hypothesis, not a claim.",
        },
        "cheapest_validation_experiment": {
            "type": "string",
            "description": "The cheapest, fastest real test that would meaningfully reduce uncertainty about this hypothesis.",
        },
        "confidence": {
            "type": "number",
            "description": "0.0-1.0 honest confidence this hypothesis is worth pursuing further, given ONLY the research shown.",
        },
        "facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things directly stated in the research, not inferred.",
        },
        "estimates": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Numeric or qualitative estimates you are making, clearly labeled as estimates.",
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things assumed true but not confirmed by the research.",
        },
        "unknowns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Important open questions the research did not answer.",
        },
    },
    "required": [
        "problem", "why_it_failed", "failure_category",
        "resurrection_hypothesis", "cheapest_validation_experiment",
        "confidence", "facts", "estimates", "assumptions", "unknowns",
    ],
}
