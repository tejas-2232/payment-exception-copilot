"""Evaluate fictional priority signals; agent mode makes paid model requests."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from app.agent.fraud_agent import fraud_review_with_agent
from app.agent.fraud_review import load_context, review_fraud
from app.api.main import load_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "agent", "both"], default="offline")
    args = parser.parse_args()
    examples = json.loads((Path(__file__).parent / "fraud_review_cases.json").read_text())
    cases = {case.case_id: case for case in load_cases()}
    modes = ["offline", "agent"] if args.mode == "both" else [args.mode]
    results = []
    for example in examples:
        for mode in modes:
            started = perf_counter()
            try:
                case = cases[example["case_id"]]
                context = load_context(case.case_id)
                result = (review_fraud(case, context) if mode == "offline"
                          else fraud_review_with_agent(case, context))
                checks = {"status": result.status == example["status"], "score": result.score == example["score"],
                          "signals": {s.signal_id for s in result.signals} == set(example["signals"]),
                          "human_review": result.human_review_required}
                output = {"case_id": case.case_id, "mode": mode, "checks": checks,
                          "passed": all(checks.values()), "elapsed_ms": round((perf_counter() - started) * 1000, 1)}
            except Exception:
                output = {"case_id": example["case_id"], "mode": mode, "error": "review failed", "passed": False}
            results.append(output)
            print(json.dumps(output))
    for mode in modes:
        subset = [r for r in results if r["mode"] == mode]
        print(json.dumps({"mode": mode, "total": len(subset), "passed": sum(r["passed"] for r in subset),
                          "errors": sum("error" in r for r in subset),
                          "semantic_support": "manual review required; not automatically scored"}))
    return 1 if not results or any(not result["passed"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
