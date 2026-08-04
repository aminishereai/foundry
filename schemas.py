"""Hermes-facing tool schema.

This is the ONLY schema Hermes' model sees for Foundry in Phase 0. It
describes the single entry point into the Executive. Internal schemas
(e.g. what the Planner's own structured LLM call returns) live in
executive/schemas.py — the model never sees those directly.
"""

FOUNDRY_EXECUTE = {
    "name": "foundry_execute",
    "description": (
        "Hand an objective to Foundry's Executive. The Executive asks its "
        "Planner to choose one concrete Hermes tool call that makes real "
        "progress toward the objective, then delegates that call back "
        "through Hermes and returns the result. Use this when the user "
        "wants executive-level reasoning about WHAT to do next, not when "
        "you already know which tool to call yourself — in that case call "
        "the tool directly."
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
        },
        "required": ["objective"],
    },
}
