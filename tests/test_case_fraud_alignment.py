"""Fail when case files, fraud context, partner procedures, or labeled scores drift apart."""
import json
from pathlib import Path

from app.agent.fraud_review import load_context, review_fraud
from app.api.main import load_cases

CASES = Path("data/cases")
CONTEXTS = Path("data/fraud_context")
PARTNERS = Path("data/partners")
PROCEDURES = Path("data/procedures")
LABELS = Path("evaluations/fraud_review_cases.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_case_files_and_fraud_labels_stay_in_step():
    cases = {}
    for path in sorted(CASES.glob("*.json")):
        case = _read_json(path)
        assert case["case_id"] not in cases, f"Duplicate case id {case['case_id']}"
        cases[case["case_id"]] = case

    contexts = {}
    for path in sorted(CONTEXTS.glob("*.json")):
        context = _read_json(path)
        assert path.stem == context["case_id"], f"{path.name} does not match {context['case_id']}"
        assert context["case_id"] not in contexts, f"Duplicate fraud context {context['case_id']}"
        contexts[context["case_id"]] = context

    missing_context = sorted(set(cases) - set(contexts))
    orphan_context = sorted(set(contexts) - set(cases))
    assert not missing_context, f"Cases missing fraud context: {missing_context}"
    assert not orphan_context, f"Fraud context without a case file: {orphan_context}"

    procedure_ids = {path.stem for path in PROCEDURES.glob("*.md")}
    for path in sorted(PARTNERS.glob("*.json")):
        partner = _read_json(path)
        missing = sorted(set(partner["procedure_ids"]) - procedure_ids)
        assert not missing, f"{partner['partner_id']} names missing procedures: {missing}"

    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    label_ids = [item["case_id"] for item in labels]
    assert len(label_ids) == len(set(label_ids)), "Fraud labels repeat a case id"
    unknown = sorted(set(label_ids) - set(cases))
    assert not unknown, f"Fraud labels name unknown cases: {unknown}"

    loaded = {case.case_id: case for case in load_cases()}
    for item in labels:
        result = review_fraud(loaded[item["case_id"]], load_context(item["case_id"]))
        assert result.status == item["status"], item["case_id"]
        assert result.score == item["score"], item["case_id"]
        assert {signal.signal_id for signal in result.signals} == set(item["signals"]), item["case_id"]
