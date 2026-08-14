"""CapitalLedger — same hybrid persistence redesign as OpportunityBacklog
(see that module's docstring for the full rationale: write_file proved
unreliable for new files in this Hermes environment; in-process cache is
the primary source of truth for a live session, with best-effort durable
write-through to the proven-reliable `memory` tool for cross-restart
recovery).

Honest scope, unchanged: Foundry has no bank/payment integration and
cannot observe real money automatically. Every entry here is
human-reported. Durable records are compact (type, amount, truncated
description) for the same shared-memory-budget reasons as the backlog.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

_TAG_PREFIX = "FOUNDRY_CAP|"
_TAG_RE = re.compile(r"FOUNDRY_CAP\|(\d+)\|(.*)")


class CapitalLedger:
    def __init__(self, tool_adapter: Any) -> None:
        self._tools = tool_adapter
        self._cache: List[Dict[str, Any]] = []
        self._next_id = 1
        self._rehydrate()

    def _rehydrate(self) -> None:
        """Best-effort recovery from a prior process's durable records,
        via the same real read path used for memory context elsewhere."""
        try:
            raw = self._tools.dispatch("read_file", {"path": "/home/ubuntu/.hermes/memories/MEMORY.md"})
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            content = parsed.get("content", "") if isinstance(parsed, dict) else ""
        except Exception:  # noqa: BLE001 — best-effort, empty ledger is a valid start state
            content = ""

        recovered: Dict[int, Dict[str, Any]] = {}
        for line in content.splitlines():
            match = _TAG_RE.search(line)
            if not match:
                continue
            try:
                entry_id = int(match.group(1))
                compact = json.loads(match.group(2))
            except (ValueError, json.JSONDecodeError):
                continue
            recovered[entry_id] = {
                "id": entry_id,
                "type": compact.get("ty", ""),
                "amount_usd": compact.get("a", 0.0),
                "description": compact.get("d", ""),
                "opportunity_id": compact.get("o"),
                "recorded_at_unix": compact.get("t", 0),
                "recovered_from_durable_record": True,
            }

        if recovered:
            self._cache = list(recovered.values())
            self._next_id = max(recovered.keys()) + 1

    def load(self) -> List[Dict[str, Any]]:
        """Instant — in-process cache, no dispatch call needed."""
        return list(self._cache)

    def record(
        self,
        entry_type: str,
        amount_usd: float,
        description: str,
        opportunity_id: Optional[int] = None,
    ) -> bool:
        """Real, human-reported cost or revenue — never estimated. Adds
        to the in-process cache (always succeeds) and best-effort
        durably records a compact version via the memory tool. Returns
        whether the DURABLE write succeeded."""
        entry = {
            "id": self._next_id,
            "type": entry_type,
            "amount_usd": amount_usd,
            "description": description,
            "opportunity_id": opportunity_id,
            "recorded_at_unix": int(time.time()),
        }
        self._cache.append(entry)
        self._next_id += 1

        try:
            compact = {
                "ty": entry_type,
                "a": amount_usd,
                "d": description[:100],
                "o": opportunity_id,
                "t": entry["recorded_at_unix"],
            }
            content = f"{_TAG_PREFIX}{entry['id']}|{json.dumps(compact)}"
            self._tools.dispatch("memory", {"target": "memory", "action": "add", "content": content})
            return True
        except Exception:  # noqa: BLE001 — durability is best-effort; the in-process record already succeeded
            return False

    def summary(self) -> Dict[str, Any]:
        entries = self._cache
        total_cost = sum(e["amount_usd"] for e in entries if e.get("type") == "cost")
        total_revenue = sum(e["amount_usd"] for e in entries if e.get("type") == "revenue")
        return {
            "total_cost_usd": round(total_cost, 2),
            "total_revenue_usd": round(total_revenue, 2),
            "net_usd": round(total_revenue - total_cost, 2),
            "entry_count": len(entries),
        }