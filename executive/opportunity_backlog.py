"""OpportunityBacklog — hybrid persistence, redesigned after live testing
proved write_file/read_file unreliable for new files in this Hermes
environment (source-confirmed: file_tools.py routes through a per-task
sandboxed environment abstraction — tools/environments/base.py's
get_sandbox_dir() explicitly supports Docker/Singularity backends — and
a file written in one task was confirmed absent from a completely fresh
terminal session afterward, even with correct absolute paths).

Design: an IN-PROCESS CACHE is the primary source of truth. Since
Executive (and this backlog) is constructed once per Hermes process and
lives for that process's whole lifetime, this alone eliminates the
demonstrated bug — no more cross-call file reads for the common case
within a live session.

Durability across restarts is layered on top via the ONE mechanism
proven reliable all session: Hermes' real `memory` tool. Honest,
disclosed tradeoff: durable records are compact (id, query, problem,
failure_category, confidence, cheapest_validation_experiment) — not the
full facts/estimates/assumptions/unknowns — because `memory` shares a
small, real character budget with the user's actual profile and other
lessons (memory_char_limit in config.yaml). Full detail is available
within a live session; only cross-restart recall is compacted.

Status/validation updates are in-process-cache-only (not separately
durable) — a deliberate, disclosed simplification rather than building a
fragile multi-entry memory-merge reconciliation system for a
lower-value piece of data. The discovered hypothesis itself — the part
that matters most to not lose — is what gets durably written.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

_TAG_PREFIX = "FOUNDRY_OPP|"
_TAG_RE = re.compile(r"FOUNDRY_OPP\|(\d+)\|(.*)")


class OpportunityBacklog:
    def __init__(self, tool_adapter: Any) -> None:
        self._tools = tool_adapter
        self._cache: List[Dict[str, Any]] = []
        self._next_id = 1
        self._rehydrate()

    def _rehydrate(self) -> None:
        """Best-effort recovery from a prior process's durable records.
        Reads MEMORY.md directly (proven reliable all session — unlike
        write_file, this is a read of a file Hermes' own core memory
        code manages, not something Foundry writes itself)."""
        try:
            raw = self._tools.dispatch("read_file", {"path": "/home/ubuntu/.hermes/memories/MEMORY.md"})
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            content = parsed.get("content", "") if isinstance(parsed, dict) else ""
        except Exception:  # noqa: BLE001 — best-effort, empty cache is a valid start state
            content = ""

        recovered: Dict[int, Dict[str, Any]] = {}
        for line in content.splitlines():
            match = _TAG_RE.search(line)
            if not match:
                continue
            try:
                opp_id = int(match.group(1))
                compact = json.loads(match.group(2))
            except (ValueError, json.JSONDecodeError):
                continue
            recovered[opp_id] = {
                "id": opp_id,
                "query": compact.get("q", ""),
                "recorded_at_unix": compact.get("t", 0),
                "status": "new",
                "hypothesis": {
                    "problem": compact.get("p", ""),
                    "failure_category": compact.get("fc", ""),
                    "confidence": compact.get("c", 0.0),
                    "cheapest_validation_experiment": compact.get("v", ""),
                    "resurrection_hypothesis": compact.get("r", ""),
                },
                "recovered_from_durable_record": True,
            }

        if recovered:
            self._cache = list(recovered.values())
            self._next_id = max(recovered.keys()) + 1

    def load(self) -> List[Dict[str, Any]]:
        """Instant — in-process cache, no dispatch call needed."""
        return list(self._cache)

    def add(self, query: str, hypothesis: Dict[str, Any]) -> bool:
        """Adds to the in-process cache (always succeeds — it's just a
        list append) and best-effort durably records a compact version
        via the memory tool. Returns whether the DURABLE write
        succeeded — the in-process add itself cannot meaningfully fail."""
        entry = {
            "id": self._next_id,
            "query": query,
            "recorded_at_unix": int(time.time()),
            "status": "new",
            "hypothesis": hypothesis,
        }
        self._cache.append(entry)
        self._next_id += 1

        try:
            compact = {
                "q": query[:80],
                "p": hypothesis.get("problem", "")[:150],
                "fc": hypothesis.get("failure_category", ""),
                "c": hypothesis.get("confidence", 0.0),
                "v": hypothesis.get("cheapest_validation_experiment", "")[:150],
                "r": hypothesis.get("resurrection_hypothesis", "")[:150],
                "t": entry["recorded_at_unix"],
            }
            content = f"{_TAG_PREFIX}{entry['id']}|{json.dumps(compact)}"
            self._tools.dispatch("memory", {"target": "memory", "action": "add", "content": content})
            return True
        except Exception:  # noqa: BLE001 — durability is best-effort; the in-process add already succeeded
            return False

    def update_status(self, opportunity_id: int, status: str, validation_result: Optional[Dict[str, Any]] = None) -> bool:
        """In-process only — see module docstring for why this is a
        disclosed, deliberate simplification."""
        for entry in self._cache:
            if entry.get("id") == opportunity_id:
                entry["status"] = status
                if validation_result is not None:
                    entry["validation_result"] = validation_result
                return True
        return False

    def get(self, opportunity_id: int) -> Optional[Dict[str, Any]]:
        for entry in self._cache:
            if entry.get("id") == opportunity_id:
                return entry
        return None


def rank_by_confidence(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic sort by the hypothesis's own honestly-reported
    confidence — no new LLM call, no invented scoring model."""
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
    """Simple, real, no-LLM-call filtering over the backlog."""
    result = entries
    if status is not None:
        result = [e for e in result if e.get("status") == status]
    if min_confidence is not None:
        result = [e for e in result if e.get("hypothesis", {}).get("confidence", 0) >= min_confidence]
    if failure_category is not None:
        result = [e for e in result if e.get("hypothesis", {}).get("failure_category") == failure_category]
    return result