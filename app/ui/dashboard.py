"""Payment-operations desk for reviewing exceptions and filing an approved case note."""
import os

import httpx
import streamlit as st

API_URL = os.environ.get("CASE_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _show_note_error(exc: httpx.HTTPError) -> None:
    detail = None
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except ValueError:
            detail = None
    if isinstance(detail, list):
        detail = "Enter the note wording before filing. Nothing was saved."
    st.error(detail or "The note was not filed. The case file is unchanged.")


def _submit_note(method: str, url: str, body: str | None, revision: int, outcome: str) -> None:
    payload = {"expected_revision": revision}
    if body is not None:
        payload["body"] = body
    try:
        response = httpx.request(method, url, json=payload, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _show_note_error(exc)
        return
    result = response.json()
    if outcome == "note_draft":
        st.session_state["note_draft"] = result
        st.session_state["note_notice"] = "Draft saved. It is not on the case history yet."
    elif outcome == "note_filed":
        st.session_state.pop("note_draft", None)
        st.session_state["note_notice"] = "Note filed. The payment was not changed."
    else:
        st.session_state.pop("note_draft", None)
        st.session_state["note_notice"] = "Draft discarded. Nothing was filed."
    st.rerun()
st.set_page_config(page_title="Exception Desk", page_icon="◈", layout="wide", initial_sidebar_state="auto")
st.markdown("""
<style>
html, body, [class*="css"], [data-testid="stAppViewContainer"] {font-family: 'DM Sans', sans-serif;}
[data-testid="stAppViewContainer"] {background: #f6f7f8; color: #172230;}
[data-testid="stSidebar"] {background: #102b32; border-right: 0;}
[data-testid="stSidebar"] * {color: #eaf4f1;}
[data-testid="stSidebar"] [data-baseweb="select"] * {color: #172230;}
[data-testid="stSidebar"] [data-testid="stButton"] button,
[data-testid="stSidebar"] [data-testid="stButton"] button * {color:#102b32 !important; background:#e7f3f0;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {color: #b8cdca;}
.block-container {padding-top: 4.5rem; padding-bottom: 4rem; max-width: 1500px;}
h1, h2, h3 {font-family: 'Manrope', sans-serif; letter-spacing: -0.035em;}
h1 {font-size: 2.25rem !important; font-weight: 800 !important;}
h2 {font-size: 1.18rem !important; font-weight: 700 !important;}
h3 {font-size: 1rem !important; font-weight: 700 !important;}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > div > div > .eyebrow) {background: #fff; border-radius: 14px;}
[data-testid="stMetric"] {background:#fff; border: 1px solid #e1e7e6; border-radius: 12px; padding: 15px 18px;}
[data-testid="stMetricLabel"] {color:#667874; font-size:.77rem;}
[data-testid="stMetricValue"] {color:#163b39; font-family:'Manrope',sans-serif; font-size:1.25rem;}
[data-testid="stButton"] button[kind="primary"] {background:#167a69; border-color:#167a69; border-radius:9px; font-weight:700;}
[data-testid="stButton"] button[kind="primary"]:hover {background:#0e6254; border-color:#0e6254;}
[data-testid="stTabs"] button {font-weight:600;}
.eyebrow {color:#167a69; font-size:.72rem; font-weight:800; letter-spacing:.15em; text-transform:uppercase; margin-bottom:.3rem;}
.brandmark {font-family:'Manrope',sans-serif; font-size:1.22rem; font-weight:800; letter-spacing:-.04em; color:#fff;}
.brandsub {color:#a9c3bc; font-size:.73rem; letter-spacing:.11em; text-transform:uppercase; margin-top:.3rem;}
.hero-note {color:#61716e; font-size:.98rem; margin:0 0 1rem;}
.section-label {color:#687a76; font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; font-weight:700; margin:0 0 .4rem;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="brandmark">◈ &nbsp;Exception Desk</div><div class="brandsub">Payment operations</div>', unsafe_allow_html=True)
    st.divider()
    st.caption("WORKSPACE")
    st.markdown("**◉  Exception queue**")
    st.caption("Simulated cases · Analyst approval")
    st.divider()
    st.caption("CASE QUEUE")

try:
    response = httpx.get(f"{API_URL}/cases", timeout=5.0)
    response.raise_for_status()
    cases = response.json()
except (httpx.HTTPError, ValueError):
    st.error("The case service is unavailable. Start the API and try again.")
    st.stop()

if not cases:
    st.info("No cases are available.")
    st.stop()

with st.sidebar:
    st.caption(f"{len(cases)} cases available")
    with st.expander("Review priority queue"):
        st.caption("Fictional offline scores; unscored cases appear first for review. Scores do not establish fraud or safety.")
        try:
            queue_response = httpx.get(f"{API_URL}/fraud-review-queue", timeout=5.0)
            queue_response.raise_for_status()
            for row in queue_response.json():
                score = f"{row['score']}/100" if row["score"] is not None else "Unscored"
                band = row.get("score_band") or ""
                label = f"{row['case_id']} · {score}"
                if row["score"] is not None and band:
                    label = f"{label} · {band}"
                st.write(label)
        except (httpx.HTTPError, ValueError):
            st.caption("Priority queue unavailable; review cases individually.")
    selected = st.selectbox("Select a case", [case["case_id"] for case in cases])
    if st.session_state.get("note_case") != selected:
        st.session_state["note_case"] = selected
        st.session_state.pop("note_draft", None)
        st.session_state.pop("note_notice", None)
    if st.button("Recent investigations", use_container_width=True):
        st.session_state["show_recent_runs"] = not st.session_state.get("show_recent_runs", False)
    if st.session_state.get("show_recent_runs"):
        runs = st.session_state.get("recent_runs", [])
        if not runs:
            st.caption("No investigation has been run in this session.")
        for item in runs:
            label = item["category"].replace("_", " ")
            st.write(f"{item['case_id']} · {label}")
            st.caption(f"{item['mode']} · {item['summary']}")
    st.caption("FILED NOTES")
    try:
        filed_response = httpx.get(f"{API_URL}/cases/{selected}/note-history", timeout=5.0)
        filed_response.raise_for_status()
        filed_notes = filed_response.json().get("approved_notes", [])
    except (httpx.HTTPError, ValueError):
        filed_notes = []
        st.caption("Filed notes are unavailable.")
    else:
        if not filed_notes:
            st.caption("No analyst note has been filed for this case.")
        for note in filed_notes:
            st.caption(note["approved_at"])
            st.write(note["body"])
    st.divider()
    st.caption("INVESTIGATION MODE")
    mode = st.radio("Choose workflow", ["offline", "agent"],
                    format_func=lambda value: "Offline rules" if value == "offline" else "AI agent",
                    help="AI agent mode sends fictional case information to the configured model provider.")
    st.divider()
    st.caption("SESSION ACTIVITY")
    ledger = st.session_state.get("investigation_costs", [])
    st.write(f"{len(ledger)} investigation{'s' if len(ledger) != 1 else ''} run")
    if ledger:
        known_costs = [cost for cost in ledger if cost is not None]
        if len(known_costs) == len(ledger):
            st.write(f"Estimated total: ${sum(known_costs):.6f}")
        else:
            st.write(f"Estimated total: unavailable ({len(ledger) - len(known_costs)} run(s) missing cost)")
    st.caption("Session totals reset with this browser session; failed attempts may also incur costs.")

try:
    response = httpx.get(f"{API_URL}/cases/{selected}", timeout=5.0)
    response.raise_for_status()
    case = response.json()
except (httpx.HTTPError, ValueError):
    st.error("Could not load the selected case. Please try again.")
    st.stop()

payment = case["payment"]
st.markdown('<div class="eyebrow">Payment operations / Exceptions</div>', unsafe_allow_html=True)
header, action = st.columns([3, 1], vertical_alignment="bottom")
with header:
    st.title("Exception desk")
    st.markdown('<p class="hero-note">Review the exception, check the evidence, and file a note only after you approve the wording. This desk does not move the payment.</p>', unsafe_allow_html=True)
with action:
    run = st.button("Investigate case", type="primary", use_container_width=True)

partner = case.get("partner_id", "unknown").replace("_", " ").title()
status = case.get("status", "unknown").replace("_", " ").title()
c1, c2, c3, c4 = st.columns(4)
c1.metric("CASE ID", case["case_id"])
c2.metric("STATUS", status)
c3.metric("PAYMENT PARTNER", partner)
c4.metric("PAYMENT", f"{payment['currency']} {payment['amount']:,.2f}")
st.write("")

if run:
    try:
        with st.spinner("Investigating the case…"):
            response = httpx.post(f"{API_URL}/investigations", json={"case_id": selected, "mode": mode}, timeout=120.0)
            response.raise_for_status()
            result = response.json()
        st.session_state["investigation"] = result
        st.session_state["investigation_mode"] = mode
        st.session_state.setdefault("investigation_costs", []).append((result.get("metrics") or {}).get("estimated_cost_usd"))
        recent = st.session_state.setdefault("recent_runs", [])
        recent.insert(0, {"case_id": result["case_id"], "mode": mode, "category": result["category"],
                          "summary": result["case_summary"]})
        del recent[8:]
        st.session_state["show_recent_runs"] = True
        st.rerun()
    except (httpx.HTTPError, ValueError) as exc:
        st.session_state.setdefault("investigation_costs", []).append(None)
        st.session_state.pop("investigation", None)
        # Only show the API's controlled error codes, never arbitrary provider output.
        code = exc.response.headers.get("X-Investigation-Error") if isinstance(exc, httpx.HTTPStatusError) else None
        messages = {
            "model_not_configured": "The AI model is not configured. Check OPENAI_API_KEY and OPENAI_MODEL.",
            "model_authentication_failed": "The model provider rejected authentication or access. Check your API key and model access.",
            "model_rate_or_credit_limit": "The model provider reported a rate or credit limit. Check API billing and limits.",
            "model_not_found": "The selected model was not found. Check OPENAI_MODEL and account access.",
            "model_request_rejected": "The model provider rejected the request. Check the selected model and configuration.",
            "model_service_unavailable": "The model provider is unavailable. Please retry later.",
            "model_connection_failed": "The model provider could not be reached or timed out. Check your connection.",
            "agent_response_invalid": "The agent response could not be verified against the case and evidence.",
        }
        message = messages.get(code, "Investigation unavailable. Please ask an analyst to review the case.")
        st.error(message)

result = st.session_state.get("investigation")
if not result or result["case_id"] != selected or st.session_state.get("investigation_mode") != mode:
    result = None

left, right = st.columns([1, 1.25], gap="large")
with left:
    with st.container(border=True):
        st.markdown('<div class="eyebrow">01 / Case overview</div>', unsafe_allow_html=True)
        st.subheader("Exception details")
        st.write(case["exception_message"])
        st.divider()
        st.markdown('<div class="section-label">Payment information</div>', unsafe_allow_html=True)
        st.write("**Payment ID**", payment["payment_id"])
        st.write("**Beneficiary**", payment["beneficiary_name"] or "Not provided")
        st.write("**Bank identifier**", payment["beneficiary_bank_identifier"] or "Not provided")
        st.divider()
        st.markdown('<div class="section-label">Partner response</div>', unsafe_allow_html=True)
        st.write(case.get("partner_response") or "No partner response provided.")
        st.markdown('<div class="section-label">Case history</div>', unsafe_allow_html=True)
        try:
            history_response = httpx.get(f"{API_URL}/cases/{selected}/note-history", timeout=5.0)
            history_response.raise_for_status()
            history = history_response.json()
        except (httpx.HTTPError, ValueError):
            history = {"file_notes": case["notes"], "approved_notes": []}
            st.caption("Filed notes are unavailable. The case file is unchanged.")
        if history["file_notes"]:
            st.caption("On the case file")
            for note in history["file_notes"]:
                st.write(note)
        else:
            st.write("No notes were on the case file.")
        if history["approved_notes"]:
            st.caption("Filed by an analyst")
            for note in history["approved_notes"]:
                st.write(note["approved_at"])
                st.write(note["body"])

with right:
    with st.container(border=True):
        st.markdown('<div class="eyebrow">02 / Investigation</div>', unsafe_allow_html=True)
        st.subheader("Analyst review")
        if result is None:
            st.info("Select an investigation mode and run the case to see a recommendation and its supporting evidence.")
            st.caption("All cases and procedures are fictional. An analyst makes the final decision.")
        else:
            if result["category"] == "insufficient_evidence":
                st.warning("Insufficient evidence · Analyst review required")
            else:
                st.success("Investigation complete · Analyst review required")
            st.write(result["case_summary"])
            st.markdown('<div class="section-label">Suggested next step</div>', unsafe_allow_html=True)
            for step in result["recommended_next_steps"]:
                st.write(step)
            st.write("**Missing information:**", ", ".join(result["missing_information"]) or "None identified")
            for uncertainty in result["uncertainties"]:
                st.caption(uncertainty)
            st.divider()
            evidence_tab, activity_tab, metrics_tab = st.tabs(["Evidence", "Activity", "Run metrics"])
            with evidence_tab:
                st.markdown('<div class="section-label">Case evidence</div>', unsafe_allow_html=True)
                if not result.get("case_evidence"):
                    st.caption("No case excerpts were returned.")
                for source in result.get("case_evidence", []):
                    st.write(f"**{source['source_id']}**")
                    st.write(source["excerpt"])
                st.markdown('<div class="section-label">Procedure evidence</div>', unsafe_allow_html=True)
                if not result["evidence"]:
                    st.caption("No supporting procedure was returned.")
                for evidence in result["evidence"]:
                    st.write(f"**{evidence['document_id']} · {evidence['section']} · v{evidence['version']}**")
                    st.write(evidence["excerpt"])
            with activity_tab:
                st.write("**Tools used**")
                st.write(" → ".join(result.get("tool_activity", [])) or "No agent tools used")
                st.write("**Procedure searches**")
                for attempt in result.get("search_attempts", []):
                    st.write(f"{attempt['query']} — {attempt['status']}")
                if not result.get("search_attempts"):
                    st.caption("No search activity was recorded.")
            with metrics_tab:
                metrics = result.get("metrics") or {}
                duration = metrics.get("total_duration_ms")
                first = metrics.get("first_model_output_ms")
                cost = metrics.get("estimated_cost_usd")
                m1, m2, m3 = st.columns(3)
                m1.metric("Total time", f"{duration / 1000:.2f}s" if duration is not None else "Unavailable")
                m2.metric("First model output", f"{first / 1000:.2f}s" if first is not None else "Unavailable")
                m3.metric("Estimated cost", f"${cost:.6f}" if cost is not None else "Unavailable")
                st.caption("First model output measures the first generated text or tool-call fragment from the start of its model call. It is not the time until the result appears on screen.")
                st.write(f"**Model calls:** {metrics.get('model_calls') if metrics.get('model_calls') is not None else 'Unavailable'}  ·  **Input tokens:** {metrics.get('input_tokens') if metrics.get('input_tokens') is not None else 'Unavailable'}  ·  **Output tokens:** {metrics.get('output_tokens') if metrics.get('output_tokens') is not None else 'Unavailable'}")
                st.caption(f"Cached input tokens reported: {metrics.get('cached_input_tokens') if metrics.get('cached_input_tokens') is not None else 'Unavailable'}")
                st.caption(metrics.get("pricing_status", "Usage unavailable") + ". Cost is an estimate, not a provider bill.")

st.divider()
with st.container(border=True):
    st.markdown('<div class="eyebrow">03 / Case note</div>', unsafe_allow_html=True)
    note_header, note_action = st.columns([3, 1], vertical_alignment="bottom")
    with note_header:
        st.subheader("File a case note")
        st.caption("The desk prepares a draft. Edit it if needed. Only the wording you approve is filed, and filing does not repair, release, return, or block the payment.")
    with note_action:
        prepare_note = st.button("Prepare draft", use_container_width=True)
    if prepare_note:
        try:
            draft_response = httpx.post(f"{API_URL}/cases/{selected}/note-drafts", timeout=30.0)
            draft_response.raise_for_status()
            st.session_state["note_draft"] = draft_response.json()
            st.session_state.pop("note_notice", None)
            st.rerun()
        except httpx.HTTPError as exc:
            _show_note_error(exc)
    draft = st.session_state.get("note_draft")
    if draft and draft.get("case_id") == selected and draft.get("status") == "open":
        st.write("**Case ID**", draft["case_id"])
        st.caption(f"Revision {draft['revision']}")
        edited = st.text_area("Exact note", value=draft["body"], height=220,
                              key=f"draft-body-{draft['draft_id']}-{draft['revision']}")
        st.markdown('<div class="section-label">Supporting evidence</div>', unsafe_allow_html=True)
        for item in draft.get("evidence", []):
            st.write(f"**{item['source_id']}**")
            st.write(item["excerpt"])
        save_col, approve_col, discard_col = st.columns(3)
        save_edit = save_col.button("Save edit", use_container_width=True)
        approve_note = approve_col.button("Approve and file", type="primary", use_container_width=True)
        discard_note = discard_col.button("Discard draft", use_container_width=True)
        if save_edit:
            _submit_note("patch", f"{API_URL}/note-drafts/{draft['draft_id']}", edited, draft["revision"], "note_draft")
        elif approve_note:
            _submit_note("post", f"{API_URL}/note-drafts/{draft['draft_id']}/approve", edited, draft["revision"], "note_filed")
        elif discard_note:
            _submit_note("post", f"{API_URL}/note-drafts/{draft['draft_id']}/discard", None, draft["revision"], "note_discarded")
    notice = st.session_state.get("note_notice")
    if notice:
        st.success(notice)

st.divider()
with st.container(border=True):
    fraud_header, fraud_action = st.columns([3, 1], vertical_alignment="bottom")
    with fraud_header:
        st.markdown('<div class="eyebrow">04 / Review priority</div>', unsafe_allow_html=True)
        st.subheader("Review priority signals")
        st.caption("A fictional review aid, not a fraud finding or probability. An analyst decides what to do.")
    with fraud_action:
        run_fraud = st.button("Assess review signals", use_container_width=True)
    if run_fraud:
        try:
            with st.spinner("Reviewing fictional history and changes…"):
                response = httpx.post(f"{API_URL}/fraud-reviews", json={"case_id": selected, "mode": mode}, timeout=120.0)
                response.raise_for_status()
                fraud_result = response.json()
            st.session_state["fraud_review"] = fraud_result
            st.session_state["fraud_review_mode"] = mode
            st.session_state.setdefault("investigation_costs", []).append((fraud_result.get("metrics") or {}).get("estimated_cost_usd"))
            st.rerun()
        except (httpx.HTTPError, ValueError):
            st.session_state.setdefault("investigation_costs", []).append(None)
            st.session_state.pop("fraud_review", None)
            st.error("Review unavailable. Ask an analyst to review the case; no priority score was assigned.")
    review = st.session_state.get("fraud_review")
    if review and review["case_id"] == selected and st.session_state.get("fraud_review_mode") == mode:
        if review["status"] == "insufficient_data":
            st.warning("Insufficient data — no priority score assigned")
            for item in review["missing_information"]:
                st.write("- " + item)
        else:
            score_col, context_col = st.columns([1, 3])
            with score_col:
                st.metric("Review priority", f"{review['score']} / {review['score_max']}")
                st.caption((review.get("score_band") or "not scored").replace("_", " "))
                st.progress(min(max(review["score"], 0), review["score_max"]) / review["score_max"])
            with context_col:
                st.write("**Signals identified**" if review["signals"] else "**No configured signals identified**")
                st.caption("The band orders the review queue. It is not a fraud probability, and zero does not mean the payment is safe.")
            rubric = review.get("rubric") or []
            if rubric:
                st.markdown('<div class="section-label">Priority rubric</div>', unsafe_allow_html=True)
                for check in rubric:
                    state = "Identified" if check["fired"] else "Not identified"
                    st.write(f"**{state} · {check['title']} · +{check['points']}**")
                    st.caption(check["explanation"])
            for signal in review["signals"]:
                for source_id in signal["evidence_ids"]:
                    st.caption(f"{source_id}: {review['evidence'][source_id]}")
        st.write("**Suggested review:**", review["next_step"])
        if review["evidence"].get("context.analyst_note"):
            st.write("**Context to verify:**", review["evidence"]["context.analyst_note"])
        with st.expander("Fictional review inputs"):
            for source_id, excerpt in review["evidence"].items():
                st.write(f"**{source_id}:** {excerpt}")
        with st.expander("Fictional procedure, rubric and activity"):
            st.write("**F-01 · Fictional fraud-review guidance**")
            st.write(review["procedure_excerpt"])
            st.write("Scoring: newly added beneficiary within 30 days +25; instruction change within 24 hours +35; amount above three times the supplied historical average +40. Weights are invented for this prototype.")
            st.write("**Tools used:**", " → ".join(review.get("tool_activity", [])) or "No agent tools used")
        st.info("Human review required. The application does not label fraud or take payment actions.")
