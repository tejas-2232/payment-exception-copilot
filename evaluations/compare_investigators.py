"""Compare two investigators on a small fictional development benchmark."""
import argparse
import json
from pathlib import Path
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
        print(f"{mode}: {sum(r['passed'] for r in runs)}/{len(runs)} passed; {sum('error' in r for r in runs)} errors")
    return 1 if any("error" in r for r in outputs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
