"""Run an opt-in LangSmith experiment on a user-provided fictional dataset."""
import argparse

from langsmith import evaluate

from app.agent.langchain_agent import investigate_with_agent
from app.agent.orchestrator import DeterministicProvider, investigate
from app.schemas import Case


def main():
    parser = argparse.ArgumentParser(description="Run a LangSmith evaluation (uploads experiment results).")
    parser.add_argument("--dataset", required=True, help="Name of an existing fictional LangSmith dataset")
    parser.add_argument("--mode", choices=("offline", "agent"), default="offline")
    args = parser.parse_args()

    def target(inputs: dict) -> dict:
        case = Case.model_validate(inputs["case"])
        result = (investigate_with_agent(case) if args.mode == "agent"
                  else investigate(case, DeterministicProvider()))
        return {"category": result.category, "evidence_ids": [e.document_id for e in result.evidence],
                "abstain": result.category == "insufficient_evidence",
                "human_review": result.escalate_to_human}

    def evaluate_result(outputs: dict, reference_outputs: dict) -> dict:
        checks = {
            "category": outputs.get("category") == reference_outputs.get("category"),
            "citations": set(outputs.get("evidence_ids", [])) == set(reference_outputs.get("evidence_ids", [])),
            "abstention": outputs.get("abstain") == reference_outputs.get("abstain"),
            "human_review": outputs.get("human_review") is True,
        }
        return {"key": "all_checks_pass", "score": float(all(checks.values())),
                "comment": ", ".join(f"{key}={value}" for key, value in checks.items())}

    evaluate(target, data=args.dataset, evaluators=[evaluate_result], experiment_prefix="fictional-payment-investigation", max_concurrency=1)


if __name__ == "__main__":
    main()
