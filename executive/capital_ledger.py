"""CapitalLedger — a real, structured record of economic outcomes.

Honest scope: Foundry has no bank/payment integration and cannot observe
real money automatically. This ledger is fed by explicit reports (from
you, or eventually a real integration) — it never estimates or fabricates
a cost/revenue figure. This is the difference between a real bookkeeping
tool and a fake "AI tracks your business" claim.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

LEDGER_FILE_PATH = os.path.expanduser("~/.hermes/plugins/foundry/data_capital_ledger.json")


class CapitalLedger:
    def __init__(self, tool_adapter: Any) -> None:
        self._tools = tool_adapter

    def load(self) -> List[Dict[str, Any]]:
        try:
            raw = self._tools.dispatch("read_file", {"path": LEDGER_FILE_PATH})
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict) and parsed.get("error"):
                return []
            content = parsed.get("content") if isinstance(parsed, dict) else None
            if not content:
                return []
            data = json.loads(content)
            return data.get("entries", []) if isinstance(data, dict) else []
        except Exception:  # noqa: BLE001
            return []

    def record(
        self,
        entry_type: str,
        amount_usd: float,
        description: str,
        opportunity_id: Optional[int] = None,
    ) -> bool:
        """entry_type: 'cost' or 'revenue'. Real number, human-reported —
        never estimated."""
        entries = self.load()
        entries.append({
            "id": len(entries) + 1,
            "type": entry_type,
            "amount_usd": amount_usd,
            "description": description,
            "opportunity_id": opportunity_id,
            "recorded_at_unix": int(time.time()),
        })
        try:
            content = json.dumps({"entries": entries}, indent=2)
            self._tools.dispatch("write_file", {"path": LEDGER_FILE_PATH, "content": content})
            return True
        except Exception:  # noqa: BLE001
            return False

    def summary(self) -> Dict[str, Any]:
        entries = self.load()
        total_cost = sum(e["amount_usd"] for e in entries if e.get("type") == "cost")
        total_revenue = sum(e["amount_usd"] for e in entries if e.get("type") == "revenue")
        return {
            "total_cost_usd": round(total_cost, 2),
            "total_revenue_usd": round(total_revenue, 2),
            "net_usd": round(total_revenue - total_cost, 2),
            "entry_count": len(entries),
        }
