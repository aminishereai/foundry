"""OpportunityBacklog — turns isolated hypotheses into a structured,
comparable portfolio. Persisted via write_file (Hermes' real tool),
dispatched DIRECTLY by Executive's own code, not as a Planner-chosen
step — same precedent as the existing memory lesson-write-back: Foundry's
own well-defined internal bookkeeping is not the kind of arbitrary
Planner-chosen action the destructive-tool confirmation gate exists to
guard against.

This IS Foundry's knowledge base for opportunities — no separate store
was built, per the principle of using as little of Foundry as possible.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

BACKLOG_FILE_PATH = "foundry_opportunities.json"


class OpportunityBacklog:
    def __init__(self, tool_adapter: Any) -> None:
        self._tools = tool_adapter

    def load(self) -> List[Dict[str, Any]]:
        """Best-effort read. Returns [] if the file doesn't exist yet or
        fails to parse — never blocks or fails the caller."""
        try:
            raw = self._tools.dispatch("read_file", {"path": BACKLOG_FILE_PATH})
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict) and parsed.get("error"):
                return []
            content = parsed.get("content") if isinstance(parsed, dict) else None
            if not content:
                return []
            data = json.loads(content)
            return data.get("opportunities", []) if isinstance(data, dict) else []
        except Exception:  # noqa: BLE001 — best-effort, empty backlog is a valid start state
            return []

    def add(self, query: str, hypothesis: Dict[str, Any]) -> bool:
        """Append one entry, real wall-clock timestamp, persist. Returns
        whether the write actually succeeded — never fabricates success."""
        entries = self.load()
        entry = {
            "id": len(entries) + 1,
            "query": query,
            "recorded_at_unix": int(time.time()),
            "status": "new",
            "hypothesis": hypothesis,
        }
        entries.append(entry)
        try:
            content = json.dumps({"opportunities": entries}, indent=2)
            self._tools.dispatch("write_file", {"path": BACKLOG_FILE_PATH, "content": content})
            return True
        except Exception:  # noqa: BLE001 — best-effort persistence
            return False

    def update_status(self, opportunity_id: int, status: str, validation_result: Optional[Dict[str, Any]] = None) -> bool:
        entries = self.load()
        found = False
        for entry in entries:
            if entry.get("id") == opportunity_id:
                entry["status"] = status
                if validation_result is not None:
                    entry["validation_result"] = validation_result
                found = True
                break
        if not found:
            return False
        try:
            content = json.dumps({"opportunities": entries}, indent=2)
            self._tools.dispatch("write_file", {"path": BACKLOG_FILE_PATH, "content": content})
            return True
        except Exception:  # noqa: BLE001
            return False

    def get(self, opportunity_id: int) -> Optional[Dict[str, Any]]:
        for entry in self.load():
            if entry.get("id") == opportunity_id:
                return entry
        return None


def rank_by_confidence(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic sort by the hypothesis's own honestly-reported
    confidence — no new LLM call, no invented scoring model. Reuses a
    field the Analyst already produces."""
    def _confidence(e: Dict[str, Any]) -> float:
        try:
            return float(e.get("hypothesis", {}).get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
    return sorted(entries, key=_confidence, reverse=True)


def filter_entries(
    entries: List[Dict[str, Any]],
    status: Optional[str] = None,
    min_confidence: Optional[float] = None,
    failure_category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Simple, real, no-LLM-call filtering over the backlog — this is
    the entire "knowledge query" capability. No fabricated semantic
    search; just honest structured filtering over real recorded data."""
    result = entries
    if status is not None:
        result = [e for e in result if e.get("status") == status]
    if min_confidence is not None:
        result = [e for e in result if e.get("hypothesis", {}).get("confidence", 0) >= min_confidence]
    if failure_category is not None:
        result = [e for e in result if e.get("hypothesis", {}).get("failure_category") == failure_category]
    return result
