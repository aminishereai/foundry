"""Internal schemas used by Foundry's own structured LLM calls.

These are never registered with Hermes and never seen by the user-facing
model — they only shape the JSON Foundry asks its Planner's LLM call to
return via ctx.llm.complete_structured.
"""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "description": (
                "Ordered sequence of 0-4 tool calls. Empty list means no "
                "sequence of tool calls meaningfully advances the objective."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": (
                            "The Hermes tool to call — must be one of the "
                            "names confirmed in tools/registry.py (e.g. "
                            "'read_file', 'search_files', 'terminal', "
                            "'execute_code', 'delegate_task')."
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
        "overall_reasoning": {
            "type": "string",
            "description": (
                "One or two sentences on the overall strategy, or why zero "
                "steps were chosen."
            ),
        },
    },
    "required": ["steps", "overall_reasoning"],
}
