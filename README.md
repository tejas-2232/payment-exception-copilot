# Payment exception investigation assistant

A personal, fictional, read-only prototype. The app lets an analyst inspect fourteen sample cases and request a bounded, procedure-grounded recommendation for human review. It does not represent a real bank or its policies.

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

Select a case and choose **Investigate**. The default provider is deterministic and runs offline. The API retrieves passages from the fictional procedures, validates citations, and returns a bounded recommendation or an insufficient-evidence response. Every result requires analyst review; the app takes no payment or case actions. Case notes are untrusted data. This prototype uses simple rules and keyword search: it cannot reliably detect all conflicts or prompt injections, and matching citations does not prove the advice is correct. These development cases are not a held-out evaluation.

An optional OpenAI provider can be selected with `INVESTIGATION_PROVIDER=openai`, `OPENAI_MODEL`, and `OPENAI_API_KEY` in the API process environment. It sends the fictional case and a single permitted option to the provider and asks it to select that option; it does not generate free-form advice. This is a connectivity demonstration, not a comparison of model quality, and may incur charges. Use only fictional data, review provider terms, and never commit credentials. Provider failures return a review message. The default requires no key.

## LangChain agent and evaluation

The dashboard's **agent** mode runs a LangChain tool-calling agent. Set `OPENAI_API_KEY` and `OPENAI_MODEL` in the API process before starting it. The model receives fictional case and partner information and may incur costs. The offline mode remains the default and needs no credentials. The agent can read only the selected case and its fictional partner profile, and search that partner's allowed procedure documents. Calls are limited; it has no write, payment, messaging, shell, or arbitrary network tools. The server checks cited case sources and retrieved partner-authorized passages, and maps the agent's category to a fixed human-review action. The agent can disagree with the deterministic baseline. Searches must include terms from the case and may be retried once; generic searches return no candidates. For selected fictional categories, conservative rule checks require relevant case facts before a specific recommendation is returned; unsupported results become insufficient evidence. These checks can miss valid variations and do not establish semantic correctness or protect against every injection. Analysts must review the actual passages. The fictional partners have distinct example procedures, which are not claims about real partners.

Run the small labeled evaluation from the repository root with `python -m evaluations.run_evaluation` for the offline baseline, or `python -m evaluations.run_evaluation --mode agent` for the configured model. The latter sends fictional cases to the model provider and can incur cost. Reference labels are not supplied to the agent. The runner reports case-level category, citation ID, abstention and human-review checks and elapsed time; it does not assess semantic support, quality of wording or real-world performance. The four legacy evaluation examples were previously used during development; they are not an independently held-out set and are too few for a performance claim. Do not tune against them and then report them as independent evaluation.

LangSmith tracing is disabled by default. To opt in, set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and optionally `LANGSMITH_PROJECT` in the process environment before running the agent or evaluation. Traces can contain model inputs, outputs, fictional cases, and tool results and are sent to LangSmith; review its terms and only use fictional data. Never put keys in files committed to Git. Tracing and live model access require network access and separate credentials. No LangSmith evaluation dataset is uploaded automatically; the local runner supplies the checks, while LangSmith provides optional trace inspection.

For an opt-in LangSmith experiment, create a fictional dataset in LangSmith with each example's inputs shaped as `{"case": <case object>}` and reference outputs shaped as `{"category": "...", "evidence_ids": ["P-01"], "abstain": false}`. Then set `LANGSMITH_API_KEY` and run `python -m evaluations.langsmith_evaluation --dataset YOUR_DATASET --mode offline` (or `--mode agent` with the model credentials). This explicitly creates an experiment and sends run outputs and scores to LangSmith; agent mode also sends case data to the model provider. The experiment checks category, exact citation IDs, abstention, and human review, not semantic correctness. Live LangSmith integration requires credentials and has not been verified in this workspace.

## Comparing richer cases

Cases 006–008 include fictional partner responses and notes. Northstar procedure N-01 covers a reference discrepancy, while Harbor procedure H-01 covers a beneficiary-name discrepancy. The agent cites the exact case sources as well as a retrieved partner procedure; it cannot send a message, update a case or resubmit a payment. The response remains a suggestion for human review.

Run `python -m evaluations.compare_investigators --mode offline` for the rules baseline, or `--mode both` to compare both approaches using a configured model. The 32 comparison cases are a small development benchmark created alongside this feature, not an independent held-out evaluation. The script reports category, required procedure and source IDs, review flag, errors and latency separately for each case. It checks identifiers, not whether the text actually supports the answer. Provider errors count as errors and are never treated as a correct abstention. Run the comparison to see the current baseline and agent results. A live agent comparison remains unverified until model credentials are configured.

The CMP-003 regression tests cover a vague search, one case-specific retry, and a fabricated Harbor mismatch despite retrieved procedure text. They use a simulated model and do not measure live model accuracy. Rerun the comparison with a configured live model to assess the changed behavior; results may vary and the comparison set is a development benchmark.

The first procedure search uses the reported partner response (or exception message when there is no response), rather than the model's proposed query. One case-specific retry is allowed; the dashboard shows the query actually used and the result status. Abstentions show the reported case facts, but a search match does not prove a procedure applies. The example Harbor guard recognizes only a few fictional response patterns and a narrow name suffix format; alternative valid wording can lead to an abstention.

The comparison summary reports completed runs and errors separately, false recommendations and correct abstentions among completed cases expecting abstention, false abstentions, citation-ID matches, and median latency. Citation-ID matches do not measure semantic support. The evaluation runner does not calculate cost; inspect provider usage. The cases were created during development and are not an independent evaluation.

## Expanded fictional evaluation

The development comparison now contains 32 scenarios; a separate 10-case candidate set is available with `python -m evaluations.compare_investigators --dataset candidate --mode offline` (or `--mode both` for a live agent comparison). Both datasets and labels were authored in the same development process and require independent human review; neither is evidence of real-world performance. Expected actions are written for reviewer use and are not automatically scored or sent to the model.

The comparison reports incorrect non-abstaining categories both overall and separately when a specific recommendation was expected, as well as abstentions, errors, latency and citation-ID checks. Citation-ID matches do not prove semantic support. Review the cited source and recommended action manually; the evaluation runner does not calculate cost; check your provider or tracing service. LangSmith and model runs are opt-in, may incur cost, and may send fictional case content to those services.

Cases marked closed, with both beneficiary fields missing, or containing words indicating resolved, corrected or historical context are conservatively sent for human review. This is a keyword-based precaution that can also cause unnecessary abstention; it is not reliable resolution or temporal reasoning.

GitHub Actions is configured to run linting and the offline test suite on pushes and pull requests. It does not run live model evaluations or need model keys.

## Investigation timing and estimated cost

The dashboard's **Run metrics** tab shows total backend investigation time and first model output. First model output is measured from the start of the first model call that emits a generated text or tool-call fragment to that first fragment. It is not time to first visible answer: the dashboard waits for the full investigation. Offline mode has no model first token. A provider or model that does not stream the necessary event will show this timing as unavailable.

The API aggregates provider-reported input, output and cached-input tokens across model calls in one investigation. To enable a per-investigation USD estimate, set these non-secret environment variables in the API process using the current prices for your selected model, **in USD per million tokens**:

```dotenv
MODEL_PRICING_MODEL=the-exact-OPENAI_MODEL-value
MODEL_INPUT_PRICE_PER_MILLION_USD=your-input-rate
MODEL_OUTPUT_PRICE_PER_MILLION_USD=your-output-rate
MODEL_CACHED_INPUT_PRICE_PER_MILLION_USD=your-cached-input-rate
```

Look up and maintain the rates at [OpenAI pricing](https://openai.com/api/pricing/). Do not enter the placeholder text as a price. The cached-input rate is required when the provider reports cached input. The estimate uses uncached input × input rate + cached input × cached rate + output × output rate, divided by one million. It assumes any cache usage the provider does not report is uncached; other fees, discounts, taxes and failed calls are not included. If usage or matching valid prices are unavailable, the app shows unavailable rather than guessing. The optional legacy offline OpenAI provider does not report usage to the dashboard.

The sidebar adds up known estimates for investigations in the current browser session; if any attempted run has unavailable cost, it displays the total as unavailable. The session total resets when the session ends and is not an account-wide total or invoice. Check provider billing for actual charges, especially after errors.

If an investigation returns 503, the dashboard displays a safe diagnostic when available, and the API logs an `Investigation failed:` code without printing case text or provider error details. The comparison runner also includes an `error_code` for failed runs. A model rate or credit limit can have several causes; check your provider account and sanitized LangSmith trace. Unverified agent output is treated as an error and requires analyst review, not a successful abstention.

## Fictional fraud-review priority

The dashboard has a separate **Review priority signals** section and an optional queue. The queue uses offline rules and shows unscored cases first so missing information remains visible; an analyst determines the actual review order. Select a case and choose **Assess review signals** in offline or agent mode. The response is read-only and is never a fraud finding, a probability, proof of safety, or a payment decision. No personal, demographic, account or behavioral data from real people is used.

The score is an invented 0–100 point total: beneficiary added within 30 days (+25), instructions changed within 24 hours (+35), and amount greater than three times the average of at least three supplied same-currency historical payments (+40). It uses the fictional review timestamp in the case context. These thresholds and weights are not calibrated and have no demonstrated real-world predictive validity. A zero means only that no configured signal was identified; a documented explanation is displayed for the analyst and does not automatically erase a signal.

No score is assigned if the review context is absent, history is incomplete or too short, currencies differ, required timestamps are missing, timezone-naive or in the future, the case is closed, or the amount is invalid. Human review is always required. The historical fixture asserts that entries are prior payments and that history is complete; the prototype does not independently verify those assertions.

In agent mode, LangChain can call two scoped read-only tools to inspect the selected fictional context and guidance. The agent identifies signal IDs but cannot set the score; the server returns a result only if the agent output agrees with its fixed rule checks. Disagreement or model failure returns an error for analyst review. Model inputs, including fictional notes, may be sent to the model and to LangSmith if tracing is enabled. No live agent test is included in CI.

Run `python -m evaluations.run_fraud_review --mode offline` to check 14 labeled development fixtures, or `python -m evaluations.run_fraud_review --mode both` for a live comparison using your configured model and credits. The labels and thresholds were created during development; the 12 fixtures are not independently reviewed, held out, or evidence of fraud-detection accuracy. Offline/simulated-agent tests run with `pytest`. Evidence support, potential disparate impacts, and real-world validity have not been assessed.
