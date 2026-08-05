"""Internal schemas used by Foundry's own structured LLM calls.

These are never registered with Hermes and never seen by the user-facing
model — they only shape the JSON Foundry asks its Planner's LLM call to
return via ctx.llm.complete_structured.
"""

PLAN_STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_name": {
            "type": "string",
            "description": (
                "The Hermes tool to call — must be one of the names "
                "confirmed in tools/registry.py (e.g. 'read_file', "
                "'search_files', 'terminal', 'execute_code', "
                "'delegate_task'). Empty string if no single tool call "
                "can make progress on the objective."
            ),
        },
        "tool_args": {
            "type": "object",
            "description": "Arguments for the chosen tool, in the shape that tool expects.",
        },
        "reasoning": {
            "type": "string",
            "description": "One or two sentences on why this tool and these args were chosen.",
        },
    },
    "required": ["tool_name", "tool_args", "reasoning"],
}