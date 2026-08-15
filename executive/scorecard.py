"""Scorecard — Foundry's real, evidence-based track record.

This is what makes autonomy expansion honest instead of fabricated: a
tool only becomes eligible for auto-approval once its ACTUAL recorded
outcomes (real Critic verdicts, real dispatch results) clear a real
threshold — never because Foundry "decided to trust it."

Same hybrid persistence pattern as OpportunityBacklog/CapitalLedger:
in-process cache as source of truth for a live session, best-effort
durable write-through to the memory tool for cross-restart recovery.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

_TAG_PREFIX = "FOUNDRY_SCORE|"
_TAG_RE = re.compile(r"FOUNDRY_SCORE\|(.*)")


class Scorecard:
    def __init__(self, tool_adapter: Any) -> None:
        self._tools = tool_adapter
        # tool_name -> {"successes": int, "failures": int, "last_updated_unix": int}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._rehydrate()

    def _rehydrate(self) -> None:
        try:
            raw = self._tools.dispatch("read_file", {"path": "/home/ubuntu/.hermes/memories/MEMORY.md"})
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            content = parsed.get("content", "") if isinstance(parsed, dict) else ""
        except Exception:  # noqa: BLE001
            content = ""

        for line in content.splitlines():
            match = _TAG_RE.search(line)
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
                tool_name = data["tool"]
                self._cache[tool_name] = {
                    "successes": data.get("s", 0),
                    "failures": data.get("f", 0),
                    "last_updated_unix": data.get("t", 0),
                }
            except (KeyError, ValueError, json.JSONDecodeError):
                continue

    def record_outcome(self, tool_name: str, success: bool) -> None:
        """Record ONE real outcome for a tool — success means a Critic
        verdict of 'satisfied', or a dispatch that completed without
        error when no Critic ran. Never a guess, never a prediction."""
        entry = self._cache.setdefault(tool_name, {"successes": 0, "failures": 0, "last_updated_unix": 0})
        if success:
            entry["successes"] += 1
        else:
            entry["failures"] += 1
        entry["last_updated_unix"] = int(time.time())

        try:
            compact = {
                "tool": tool_name,
                "s": entry["successes"],
                "f": entry["failures"],
                "t": entry["last_updated_unix"],
            }
            content = f"{_TAG_PREFIX}{json.dumps(compact)}"
            # 'replace' would need the exact old text; since old_text
            # matching against a changing counter is fragile, each
            # update is a fresh 'add' — rehydration takes the LAST
            # (most recent) entry per tool_name, which is correct since
            # dict overwrite on rehydrate naturally keeps the latest.
            self._tools.dispatch("memory", {"target": "memory", "action": "add", "content": content})
        except Exception:  # noqa: BLE001 — durability is best-effort
            pass

    def get(self, tool_name: str) -> Dict[str, Any]:
        entry = self._cache.get(tool_name, {"successes": 0, "failures": 0, "last_updated_unix": 0})
        total = entry["successes"] + entry["failures"]
        success_rate = entry["successes"] / total if total > 0 else None
        return {
            "tool_name": tool_name,
            "successes": entry["successes"],
            "failures": entry["failures"],
            "total": total,
            "success_rate": success_rate,
        }

    def all(self) -> List[Dict[str, Any]]:
        return [self.get(name) for name in sorted(self._cache.keys())]

    def is_earned_autonomous(self, tool_name: str, min_successes: int, min_success_rate: float) -> bool:
        """Real, evidence-gated check — never a default 'trust it'.
        Both real thresholds must be cleared."""
        record = self.get(tool_name)
        if record["total"] < min_successes:
            return False
        if record["success_rate"] is None or record["success_rate"] < min_success_rate:
            return False
        return True