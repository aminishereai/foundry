"""Hermes-facing tool schema.

This is the ONLY schema Hermes' model sees for Foundry. It describes the
single entry point into the Executive. Internal schemas live in
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