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
