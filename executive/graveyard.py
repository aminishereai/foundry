"""Internet Graveyard Pipeline — Foundry economic intelligence layer.

This module provides:
1. Real-world graveyard discovery using Hermes web tools
2. Deduplication via SHA-256 fingerprinting of opportunity metadata
3. Confidence tracking with evidence-based updates
4. Economic scoring with transparent accounting
5. Validation design with kill conditions
6. Learning loop for continuous improvement

DO NOT modify existing schemas.py - extend existing structures only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .economics import Budget, estimate_cost_usd
from .model_policy import call_with_fallback, tiers_for
from .schemas import OPPORTUNITY_HYPOTHESIS_SCHEMA
from .prompts.opportunity_analyst_prompt import OPPORTUNITY_ANALYST_INSTRUCTIONS

GRAVEYARD_DB_PATH = os.path.expanduser("~/.hermes/foundry/graveyard_db.json")


def compute_graveyard_id(source_project: str, url: str, failure_category: str, proposed_modern_approach: str) -> str:
    """Deterministic identifier for deduplication."""
    raw = f"{source_project}|{url}|{failure_category}|{proposed_modern_approach}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class GraveyardRecord:
    """A single dead/failed product analyzed for resurrection opportunity.
    Uses stable identity for deterministic deduplication.
    """
    graveyard_id: str
    source_project: str
    url: str
    failure_category: str
    proposed_modern_approach: str
    name: str
    category: str
    launch_date: str
    shutdown_date: str
    lifespan: str
    company: str
    founder: str
    what_it_did: str
    target_users: str
    business_model: str
    evidence_of_usage: List[str]
    reason_for_failure: str
    shutdown_reason_source: str
    replacement_competitors: List[str]
    surviving_user_problem: str
    current_alternatives: List[str]
    potential_gap: str
    confidence: float
    estimated_validation_cost_usd: Optional[float] = None
    estimated_build_cost_usd: Optional[float] = None
    estimated_operating_cost_usd: Optional[float] = None
    estimated_time_to_mvp_days: Optional[int] = None
    potential_revenue_usd: Optional[float] = None
    validation_hypothesis: str = ""
    success_threshold: str = ""
    failure_threshold: str = ""
    max_validation_budget_usd: float = 100.0
    time_limit_days: int = 30
    kill_condition: str = ""
    cheapest_validation_experiment: str = ""
    source_urls: List[str] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)
    estimates: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    first_seen: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    last_updated: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    update_history: List[Dict[str, Any]] = field(default_factory=list)


class GraveyardDB:
    """Persistent store for graveyard records with deduplication."""

    def __init__(self, path: str = GRAVEYARD_DB_PATH):
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._records: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, "r") as f:
                self._records = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._records = {}

    def _save(self) -> None:
        with open(self._path, "w") as f:
            json.dump(self._records, f, indent=2)

    def upsert(self, record: GraveyardRecord) -> bool:
        gid = record.graveyard_id
        existing = self._records.get(gid)
        is_new = existing is None

        if existing:
            old_confidence = existing.get("confidence", 0.0)
            record.update_history = existing.get("update_history", [])
            record.update_history.append({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "prev_confidence": old_confidence,
                "new_confidence": record.confidence,
                "change": record.confidence - old_confidence,
            })

        self._records[gid] = json.dumps(record.__dict__, default=str)
        self._save()
        return is_new

    def get(self, gid: str) -> Optional[GraveyardRecord]:
        raw = self._records.get(gid)
        if not raw:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return GraveyardRecord(**data)
        except (json.JSONDecodeError, ValueError):
            return None

    def all(self) -> List[GraveyardRecord]:
        records = []
        for raw in self._records.values():
            try:
                records.append(GraveyardRecord(**json.loads(raw)))
            except (json.JSONDecodeError, ValueError):
                continue
        return records

    def find_by_project(self, name: str) -> List[GraveyardRecord]:
        results = []
        for raw in self._records.values():
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict) and data.get("source_project", "").lower() == name.lower():
                try:
                    results.append(GraveyardRecord(**data))
                except ValueError:
                    continue
        return results

    def delete(self, gid: str) -> bool:
        if gid in self._records:
            del self._records[gid]
            self._save()
            return True
        return False


def graveyard_economic_score(record: GraveyardRecord, budget: Budget) -> float:
    """Economic attractiveness score.

    Factors:
    - Problem strength (based on confidence × evidence)
    - Economic viability (revenue/cost ratios, time penalties)
    - Confidence factor
    - Cost penalties (lower cost = higher score)
    - Time penalty (faster = better)
    - Monetization strength
    - Budget constraint compliance
    """
    evidence_strength = min(1.0, len(record.evidence_of_usage) / 5.0)
    problem_strength = max(0.1, min(1.0, record.confidence * (0.5 + 0.5 * evidence_strength)))

    total_cost = (record.estimated_validation_cost_usd or 1000) + (record.estimated_build_cost_usd or 100000)
    revenue = record.potential_revenue_usd or 0
    time_days = record.estimated_time_to_mvp_days or 365

    confidence_factor = max(0.1, record.confidence)

    if total_cost <= 0:
        cost_factor = 1.0
    else:
        cost_factor = 1.0 / (1.0 + total_cost / 1000.0)
        cost_factor = min(1.0, cost_factor)

    time_factor = 1.0 / (1.0 + time_days / 365.0)

    if record.estimated_build_cost_usd and record.estimated_build_cost_usd > 0 and record.potential_revenue_usd and record.potential_revenue_usd > 0:
        revenue_ratio = record.potential_revenue_usd / record.estimated_build_cost_usd
        monetization_strength = min(1.0, revenue_ratio / 10.0)
    else:
        monetization_strength = 0.1

    budget_factor = 1.0
    if record.estimated_validation_cost_usd is not None and record.estimated_validation_cost_usd > budget.status().limit_usd:
        budget_factor = 0.0

    score = (
        problem_strength
        * confidence_factor
        * cost_factor
        * time_factor
        * monetization_strength
        * budget_factor
    )

    return round(score, 4)


def update_confidence(record: GraveyardRecord, success: bool, evidence: str = "", actual_cost: float = 0.0) -> Dict[str, Any]:
    """Apply experiment results to a graveyard record.

    Updates confidence upward if successful, downward if failed.
    Records prediction and actual outcomes.
    """
    old_confidence = record.confidence

    if success:
        delta = 0.15 if len(evidence or "") > 50 else 0.10
        record.confidence = min(0.95, record.confidence + delta)
        prediction = evidence[:200] if evidence else "positive"
        actual_outcome = "confirmed"
        decision = "VALIDATE"
    else:
        delta = -0.25
        record.confidence = max(0.05, record.confidence + delta)
        prediction = f"Failed: {evidence[:200]}" if evidence else "failed"
        actual_outcome = "invalidated"
        decision = "KILL" if record.confidence < 0.3 else "PIVOT"

    record.update_history.append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prev_confidence": old_confidence,
        "new_confidence": record.confidence,
        "change": record.confidence - old_confidence,
        "prediction": prediction,
        "actual_outcome": actual_outcome,
        "decision": decision,
    })

    return {
        "old_confidence": old_confidence,
        "new_confidence": record.confidence,
        "delta": record.confidence - old_confidence,
        "prediction": prediction,
        "actual_outcome": actual_outcome,
        "decision": decision,
    }


class GraveyardPipeline:
    """Main execution engine for the Internet Graveyard system."""

    def __init__(self, llm_adapter: Any, tool_adapter: Any, budget: Optional[Budget] = None):
        self._llm = llm_adapter
        self._tools = tool_adapter
        self._budget = budget or Budget()
        self._db = GraveyardDB()

    def run_full_pipeline(self, query: str, max_candidates: int = 10, max_analyze: int = 5) -> Dict[str, Any]:
        """Execute complete pipeline: discover → research → analyze → score → rank."""
        candidates = self.discover_candidates(query, max_candidates)
        if not candidates:
            return {"status": "no_candidates_found", "query": query}

        records = []
        for candidate in candidates[:max_analyze]:
            try:
                research = self.research_candidate(candidate)
                analysis = self.analyze_opportunity(candidate, research)
                if analysis.get("success"):
                    record = self.create_record(candidate, analysis)
                    records.append({
                        "source_project": record.source_project,
                        "graveyard_id": record.graveyard_id,
                        "confidence": record.confidence,
                        "failure_category": record.failure_category,
                    })
            except Exception:
                continue

        ranking = self.score_and_rank()
        return {
            "status": "success",
            "query": query,
            "candidates_found": len(candidates),
            "records_processed": len(records),
            "all_records": len(ranking),
            "top_opportunity": ranking[0] if ranking else None,
            "confidence_analysis": "completed"
        }

    def discover_candidates(self, query: str, max_candidates: int = 10) -> List[Dict[str, Any]]:
        """DISCOVER: find real dead/abandoned products related to query."""
        research_obj = (
            f"Search the web for REAL products/services related to '{query}' "
            f"that shut down, were abandoned, or failed commercially. Include: "
            f"name, url, category, launch year, shutdown year, what it did, "
            f"target users, and reason for failure. Return up to {max_candidates} "
            f"results as structured JSON. Only include projects with real "
            f"public shutdown announcements or archived pages."
        )

        result = self._tools.dispatch("foundry_execute", {
            "objective": research_obj,
            "confirm_destructive": False,
        })

        candidates = []
        if isinstance(result, str):
            try:
                data = json.loads(result)
            except json.JSONDecodeError:
                data = {}

            if isinstance(data, dict):
                if isinstance(data.get("candidates"), list):
                    candidates = data["candidates"]
                elif data.get("name") and data.get("url"):
                    candidates.append(data)

        if not candidates and isinstance(result, dict) and result.get("executed_steps"):
            evidence = result.get("executed_steps", [{}])[-1].get("result", "")
            candidates = self._parse_candidates_from_text(evidence, query)

        return candidates[:max_candidates]

    def _parse_candidates_from_text(self, text: str, query: str) -> List[Dict[str, Any]]:
        candidates = []
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        for line in lines:
            url_match = re.search(r'https?://[^\s]+', line)
            if url_match:
                url = url_match.group(0)
                before_url = line[:url_match.start()].strip()
                name = re.sub(r'[:\-]', '', before_url).strip()
                if name and url:
                    candidates.append({
                        "name": name,
                        "url": url,
                        "description": line,
                        "failure_category": "unknown"
                    })

        return candidates

    def research_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """COLLECT: gather evidence from multiple sources about candidate."""
        research_obj = (
            f"Research '{candidate.get('name', '')}' at {candidate.get('url', '')}. "
            f"Gather evidence from: Wikipedia, Wayback Machine, shutdown announcements, "
            f"tech press (TechCrunch, WSJ, etc.), Hacker News, "
            f"Reddit from former users. "
            f"Extract: purpose, launch date, shutdown date, "
            f"key features, target users, business model, usage metrics, failure reason, "
            f"competitors that emerged, surviving user demand, any "
            f"publicly stated plans for replacement. "
            f"DO NOT make up facts. If a source doesn't have info, state that explicitly. "
            f"Cite each source URL."
        )

        result = self._tools.dispatch("foundry_execute", {
            "objective": research_obj,
            "confirm_destructive": False,
        })

        return {"candidate": candidate, "research_result": result}

    def analyze_opportunity(self, candidate: Dict[str, Any], research_result: Dict[str, Any]) -> Dict[str, Any]:
        """CLASSIFY→ANALYZE→IDENTIFY SURVIVING DEMAND→GENERATE OPPORTUNITY."""
        from .opportunity_analyst import OpportunityAnalyst

        query = candidate.get("name", "This project")
        research_steps = research_result.get("research_result", {}).get("executed_steps", [])

        if not research_steps:
            return {"success": False, "reason": "No research results"}

        # Build evidence list for Opportunity Analyst
        evidence_items = []
        for step in research_steps:
            result = step.get("result", {})
            if isinstance(result, dict):
                evidence_items.append({
                    "tool_name": step.get("tool_name", ""),
                    "result": result.get("result", ""),
                    "source": step.get("tool_name", "unknown")
                })

        input_text = f"Research query: {query}\n\nEvidence:\n"
        for item in evidence_items:
            input_text += f"- {item['tool_name']}: {item['result'][:200]}\n"

        input_text += "\nAnalyze and produce ONE structured opportunity hypothesis."

        kwargs = {
            "instructions": OPPORTUNITY_ANALYST_INSTRUCTIONS,
            "input": [{"type": "text", "text": input_text}],
            "json_schema": OPPORTUNITY_HYPOTHESIS_SCHEMA,
            "schema_name": "foundry.opportunity_hypothesis",
            "purpose": "foundry.opportunity_analyst",
            "temperature": 0.0,
            "max_tokens": 4000,
        }

        tiers = tiers_for("opportunity_analyst", "FOUNDRY_PLANNER_MODEL", "FOUNDRY_PLANNER_PROVIDER")
        result = call_with_fallback(self._llm, tiers, **kwargs)

        parsed = getattr(result, "parsed", {}) or {}

        # Map failure category
        failure_category = parsed.get("failure_category", "unclear_from_research")
        if failure_category == "unclear_from_research":
            why = parsed.get("why_it_failed", "").lower()
            if "timing" in why:
                failure_category = "bad_timing"
            elif "distribution" in why or "growth" in why:
                failure_category = "bad_distribution"
            elif "monetiz" in why or "revenue" in why:
                failure_category = "bad_economics"
            elif "competition" in why:
                failure_category = "market_change"
            elif "capital" in why or "funding" in why:
                failure_category = "capital_constraint"
            elif "technology" in why:
                failure_category = "technology_limitation"

        return {
            "success": True,
            "hypothesis": parsed.get("resurrection_hypothesis", ""),
            "confidence": float(parsed.get("confidence", 0.5)),
            "failure_category": failure_category,
            "facts": parsed.get("facts", []),
            "estimates": parsed.get("estimates", []),
            "assumptions": parsed.get("assumptions", []),
            "unknowns": parsed.get("unknowns", []),
            "resurrection_hypothesis": parsed.get("resurrection_hypothesis", ""),
            "cheapest_validation_experiment": parsed.get("cheapest_validation_experiment", ""),
        }

    def create_record(self, candidate: Dict[str, Any], analysis: Dict[str, Any]) -> GraveyardRecord:
        candidate_name = candidate.get("name", "Unknown")
        analysis_hypothesis = analysis.get("hypothesis", "")
        failure_category = analysis.get("failure_category", "unclear_from_research")

        estimates = analysis.get("estimates", [])
        build_cost = None
        validation_cost = None
        revenue = None
        time_to_mvp = None

        for est in estimates:
            est_lower = est.lower()
            nums = re.findall(r'\$?(\d+[\d,]*\.?\d*)', est)
            if "build" in est_lower and nums:
                try:
                    build_cost = float(nums[0].replace(",", ""))
                except ValueError:
                    pass
            elif "valid" in est_lower and nums:
                try:
                    validation_cost = float(nums[0].replace(",", ""))
                except ValueError:
                    pass
            elif "revenue" in est_lower and nums:
                try:
                    revenue = float(nums[0].replace(",", ""))
                except ValueError:
                    pass
            elif "mvp" in est_lower and "day" in est_lower and nums:
                try:
                    time_to_mvp = int(nums[0])
                except ValueError:
                    pass

        proposed_approach = analysis_hypothesis[:200] if analysis_hypothesis else "N/A"
        gid = compute_graveyard_id(
            candidate_name,
            candidate.get("url", ""),
            failure_category,
            proposed_approach,
        )

        record = GraveyardRecord(
            graveyard_id=gid,
            source_project=candidate_name,
            url=candidate.get("url", ""),
            failure_category=failure_category,
            proposed_modern_approach=proposed_approach,
            name=candidate_name,
            category=candidate.get("category", "Software"),
            launch_date=candidate.get("launch_date", "unknown"),
            shutdown_date=candidate.get("shutdown_date", "unknown"),
            lifespan=candidate.get("lifespan", "unknown"),
            company=candidate.get("company", "unknown"),
            founder=candidate.get("founder", "unknown"),
            what_it_did=candidate.get("description", ""),
            target_users=analysis_hypothesis.get("target_customer", "unknown"),
            business_model=analysis_hypothesis.get("business_model_summary", "unknown"),
            evidence_of_usage=analysis.get("facts", []),
            reason_for_failure=analysis_hypothesis.get("why_it_failed", "unclear"),
            shutdown_reason_source=analysis.get("failure_category", "unknown"),
            surviving_user_problem=analysis_hypothesis.get("problem", "unknown"),
            potential_gap=analysis_hypothesis.get("assumption_that_may_have_changed", ""),
            confidence=float(analysis.get("confidence", 0.5)),
            estimated_validation_cost_usd=validation_cost,
            estimated_build_cost_usd=build_cost,
            estimated_time_to_mvp_days=time_to_mvp,
            potential_revenue_usd=revenue,
            validation_hypothesis=analysis_hypothesis.get("problem", "unknown"),
            success_threshold=analysis_hypothesis.get("success_threshold", ""),
            failure_threshold=analysis_hypothesis.get("failure_threshold", ""),
            max_validation_budget_usd=float(validation_cost) if validation_cost else 100.0,
            time_limit_days=30,
            kill_condition=failure_category == "bad_idea",
            cheapest_validation_experiment=analysis_hypothesis.get("cheapest_validation_experiment", ""),
            source_urls=[],
            facts=analysis.get("facts", []),
            estimates=analysis.get("estimates", []),
            assumptions=analysis.get("assumptions", []),
            unknowns=analysis.get("unknowns", []),
        )

        return self._db.upsert(record)

    def score_and_rank(self) -> List[Dict[str, Any]]:
        records = self._db.all()
        scored = []

        for record in records:
            score = graveyard_economic_score(record, self._budget)
            scored.append({
                "graveyard_id": record.graveyard_id,
                "source_project": record.source_project,
                "failure_category": record.failure_category,
                "confidence": record.confidence,
                "economic_score": score,
                "estimated_validation_cost_usd": record.estimated_validation_cost_usd,
                "estimated_build_cost_usd": record.estimated_build_cost_usd,
                "potential_revenue_usd": record.potential_revenue_usd,
                "estimated_time_to_mvp_days": record.estimated_time_to_mvp_days,
                "kill_condition": record.kill_condition,
                "last_updated": record.last_updated,
            })

        scored.sort(key=lambda x: x["economic_score"], reverse=True)
        return scored

    def validate_opportunity(
        self, graveyard_id: str, experiment_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        record = self._db.get(graveyard_id)
        if not record:
            return {"status": "error", "error": f"Record {graveyard_id} not found"}

        if experiment_result is None:
            return {
                "status": "ok",
                "source_project": record.source_project,
                "current_confidence": record.confidence,
                "kill_condition": record.kill_condition,
                "validation_hypothesis": record.validation_hypothesis,
                "max_validation_budget_usd": record.max_validation_budget_usd,
                "time_limit_days": record.time_limit_days,
                "cheapest_validation_experiment": record.cheapest_validation_experiment,
            }

        success = experiment_result.get("success", False)
        evidence = experiment_result.get("evidence", "")
        actual_cost = experiment_result.get("cost_usd", 0.0)

        result = update_confidence(record, success, evidence, actual_cost)

        self._db.upsert(record)

        killed = record.confidence < 0.3 or result["decision"] == "KILL"

        return {
            "status": "ok",
            "graveyard_id": graveyard_id,
            "decision": result["decision"],
            "old_confidence": result["old_confidence"],
            "new_confidence": result["new_confidence"],
            "confidence_change": result["new_confidence"] - result["old_confidence"],
            "killed": killed,
            "prediction_error": record.update_history[-1]["prediction"] if record.update_history else "",
        }

    def execute_full_pipeline_with_validation(self, query: str) -> Dict[str, Any]:
        """Complete pipeline with validation simulation."""
        # Stage 1: Discover and analyze
        pipeline_result = self.run_full_pipeline(query)

        # Stage 2: Simulate validation for top opportunity
        top_graveyard_id = pipeline_result.get("top_opportunity", {}).get("graveyard_id")
        if top_graveyard_id:
            # Simulate validation experiment with success probability based on confidence
            import random
            success_prob = pipeline_result.get("top_opportunity", {}).get("confidence", 0.5)
            success = random.random() < success_prob
            validation_result = self.validate_opportunity(top_graveyard_id, {
                "success": success,
                "evidence": f"Validation experiment {'succeeded' if success else 'failed'} with confidence {success_prob:.2f}",
                "cost_usd": 25.0,
            })
            return {
                "pipeline_result": pipeline_result,
                "validation_result": validation_result,
                "status": "completed"
            }

        return pipeline_result