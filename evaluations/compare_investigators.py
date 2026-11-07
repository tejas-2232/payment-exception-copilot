"""Compare two investigators on a small fictional development benchmark."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from app.agent.langchain_agent import investigate_with_agent
from app.agent.orchestrator import DeterministicProvider, investigate
from app.schemas import Case


def run_one(item, mode):
    case = Case.model_validate(item["case"])
    started = perf_counter()
    try:
        result = (investigate(case, DeterministicProvider()) if mode == "offline"
                  else investigate_with_agent(case))
        procedure_ids = {e.document_id for e in result.evidence}
        source_ids = {e.source_id for e in result.case_evidence}
        required_procedures = {item["procedure"]} if item["procedure"] else set()
        checks = {"category": result.category == item["category"],
                  "procedure": procedure_ids == required_procedures,
                  "case_sources": set(item["sources"]).issubset(source_ids),
                  "human_review": result.escalate_to_human}
        return {"case_id": case.case_id, "mode": mode, "category": result.category,
                "checks": checks, "passed": all(checks.values()),
                "expected_category": item["category"],
                "elapsed_ms": round((perf_counter() - started) * 1000, 1)}
    except Exception:
        return {"case_id": case.case_id, "mode": mode, "error": "investigation failed",
                "passed": False, "elapsed_ms": round((perf_counter() - started) * 1000, 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "agent", "both"], default="offline")
    args = parser.parse_args()
    items = json.loads((Path(__file__).parent / "comparison_cases.json").read_text())
    modes = ["offline", "agent"] if args.mode == "both" else [args.mode]
    outputs = [run_one(item, mode) for item in items for mode in modes]
    for output in outputs:
        print(json.dumps(output))
    for mode in modes:
        runs = [r for r in outputs if r["mode"] == mode]
        completed = [r for r in runs if "error" not in r]
        abstention_cases = [r for r in completed if r["expected_category"] == "insufficient_evidence"]
        metrics = {"mode": mode, "total": len(runs), "completed": len(completed),
                   "errors": len(runs) - len(completed), "all_checks_passed": sum(r["passed"] for r in completed),
                   "false_recommendations": sum(r["category"] != "insufficient_evidence" for r in abstention_cases),
                   "correct_abstentions": sum(r["category"] == "insufficient_evidence" for r in abstention_cases),
                   "completed_abstention_expected": len(abstention_cases),
                   "false_abstentions": sum(r["category"] == "insufficient_evidence" and r["expected_category"] != "insufficient_evidence" for r in completed),
                   "citation_id_checks_passed": sum(r["checks"]["procedure"] and r["checks"]["case_sources"] for r in completed),
                   "median_elapsed_ms": round(median(r["elapsed_ms"] for r in completed), 1) if completed else None,
                   "cost": "unavailable; inspect provider usage"}
        print(json.dumps(metrics))
    return 1 if any("error" in r for r in outputs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
