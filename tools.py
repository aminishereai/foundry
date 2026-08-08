"""Tool handlers — the code that runs when Hermes calls Foundry's tool(s).

Per Hermes' plugin contract: handlers receive (args: dict, **kwargs) and
must always return a JSON string, never raise.
"""

import json


def foundry_execute(args: dict, *, executive, **kwargs) -> str:
    """Handler for the foundry_execute tool.

    `executive` is bound at registration time via functools.partial in
    __init__.py — it is not part of Hermes' handler contract, it's how
    this plugin closes over its own Executive instance.
    """
    objective = (args.get("objective") or "").strip()
    if not objective:
        return json.dumps({"status": "error", "error": "No objective provided"})

    confirm_destructive = bool(args.get("confirm_destructive", False))

    try:
        result = executive.run(objective, confirm_destructive=confirm_destructive)
    except Exception as exc:  # noqa: BLE001 — handlers must never raise
        return json.dumps({
            "status": "error",
            "stage": "handler",
            "objective": objective,
            "error": str(exc),
        })

    return json.dumps(result)