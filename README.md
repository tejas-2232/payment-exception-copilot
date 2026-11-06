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

## LangChain agent and evaluation

The dashboard's **agent** mode runs a LangChain tool-calling agent. Set `OPENAI_API_KEY` and `OPENAI_MODEL` in the API process before starting it. The model receives fictional case and partner information and may incur costs. The offline mode remains the default and needs no credentials. The agent can read only the selected case and its fictional partner profile, and search that partner's allowed procedure documents. Calls are limited; it has no write, payment, messaging, shell, or arbitrary network tools. The server checks citations against retrieved passages and requires the result to agree with the deterministic baseline; disagreements or provider failures return an error for human review. This conservative check limits what the agent can recommend and does not prove that advice is supported or safe. The fictional partner profiles currently use the same procedures; they are not claims about real partners.

Run the small labeled evaluation from the repository root with `python -m evaluations.run_evaluation` for the offline baseline, or `python -m evaluations.run_evaluation --mode agent` for the configured model. The latter sends fictional cases to the model provider and can incur cost. Reference labels are not supplied to the agent. The runner reports case-level category, citation ID, abstention and human-review checks and elapsed time; it does not assess semantic support, quality of wording or real-world performance. The four held-out examples are illustrative and too few for a performance claim. Do not tune against them and then report them as independent evaluation.

LangSmith tracing is disabled by default. To opt in, set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and optionally `LANGSMITH_PROJECT` in the process environment before running the agent or evaluation. Traces can contain model inputs, outputs, fictional cases, and tool results and are sent to LangSmith; review its terms and only use fictional data. Never put keys in files committed to Git. Tracing and live model access require network access and separate credentials. No LangSmith evaluation dataset is uploaded automatically; the local runner supplies the checks, while LangSmith provides optional trace inspection.

For an opt-in LangSmith experiment, create a fictional dataset in LangSmith with each example's inputs shaped as `{"case": <case object>}` and reference outputs shaped as `{"category": "...", "evidence_ids": ["P-01"], "abstain": false}`. Then set `LANGSMITH_API_KEY` and run `python -m evaluations.langsmith_evaluation --dataset YOUR_DATASET --mode offline` (or `--mode agent` with the model credentials). This explicitly creates an experiment and sends run outputs and scores to LangSmith; agent mode also sends case data to the model provider. The experiment checks category, exact citation IDs, abstention, and human review, not semantic correctness. Live LangSmith integration requires credentials and has not been verified in this workspace.
