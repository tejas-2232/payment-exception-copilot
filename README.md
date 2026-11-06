# Payment exception investigation assistant

A personal, fictional, read-only prototype. The app lets an analyst inspect five sample cases and request a bounded, procedure-grounded recommendation for human review. It does not represent a real bank or its policies.

## Run locally
Requires Python 3.10 or newer. From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

In a second terminal, activate the same environment and run `streamlit run app/ui/dashboard.py`. The dashboard connects to the API on port 8000; set `CASE_API_URL` to change the API address. Run `pytest` and `ruff check .` for offline checks. All examples are fictional; see [data card](data/DATA_CARD.md) and [discovery](docs/discovery.md).

## Investigations and limitations

Select a case and choose **Investigate**. The default provider is deterministic and runs offline. The API retrieves passages from the fictional procedures, validates citations, and returns a bounded recommendation or an insufficient-evidence response. Every result requires analyst review; the app takes no payment or case actions. Case notes are untrusted data. This prototype uses simple rules and keyword search: it cannot reliably detect all conflicts or prompt injections, and matching citations does not prove the advice is correct. These five development cases are not a held-out evaluation.

An optional OpenAI provider can be selected with `INVESTIGATION_PROVIDER=openai`, `OPENAI_MODEL`, and `OPENAI_API_KEY` in the API process environment. It sends the fictional case and a single permitted option to the provider and asks it to select that option; it does not generate free-form advice. This is a connectivity demonstration, not a comparison of model quality, and may incur charges. Use only fictional data, review provider terms, and never commit credentials. Provider failures return a review message. The default requires no key.
