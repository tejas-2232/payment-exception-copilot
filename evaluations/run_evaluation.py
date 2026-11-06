"""Run a small labeled fictional evaluation; never send reference labels to the agent."""
import argparse
import json
from pathlib import Path
import time

from app.agent.langchain_agent import investigate_with_agent
from app.agent.orchestrator import DeterministicProvider, investigate
from app.schemas import Case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "agent"), default="offline")
    args = parser.parse_args()
    cases = json.loads((Path(__file__).parent / "held_out_cases.json").read_text())
    passed = 0
    for item in cases:
        case = Case.model_validate(item["case"])
        started = time.perf_counter()
        try:
            result = (investigate_with_agent(case) if args.mode == "agent"
                      else investigate(case, DeterministicProvider()))
            checks = {"category": result.category == item["expected_category"],
                      "citations": {e.document_id for e in result.evidence} == set(item["expected_evidence"]),
                      "abstention": (result.category == "insufficient_evidence") == item["abstain"],
                      "human_review": result.escalate_to_human}
            ok = all(checks.values())
            passed += ok
            print(json.dumps({"case_id": case.case_id, "checks": checks,
                              "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}))
        except Exception:
            print(json.dumps({"case_id": case.case_id, "error": "investigation failed",
                              "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}))
    print(f"Passed {passed}/{len(cases)} cases (category, citation IDs, abstention, human review)")
    return 0 if passed == len(cases) and cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
