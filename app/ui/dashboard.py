"""Analyst workspace for fictional, read-only payment investigations."""
import os

import httpx
import streamlit as st

API_URL = os.environ.get("CASE_API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="Exception Desk", page_icon="◈", layout="wide", initial_sidebar_state="auto")
st.markdown("""
<style>
html, body, [class*="css"], [data-testid="stAppViewContainer"] {font-family: 'DM Sans', sans-serif;}
[data-testid="stAppViewContainer"] {background: #f6f7f8; color: #172230;}
[data-testid="stSidebar"] {background: #102b32; border-right: 0;}
[data-testid="stSidebar"] * {color: #eaf4f1;}
[data-testid="stSidebar"] [data-baseweb="select"] * {color: #172230;}
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
    st.markdown('<div class="brandmark">◈ &nbsp;Exception Desk</div><div class="brandsub">Operations workspace</div>', unsafe_allow_html=True)
    st.divider()
    st.caption("WORKSPACE")
    st.markdown("**◉  Investigations**")
    st.caption("Fictional data · Read-only")
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
    selected = st.selectbox("Select a case", [case["case_id"] for case in cases])
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
st.markdown('<div class="eyebrow">Operations / Investigations</div>', unsafe_allow_html=True)
header, action = st.columns([3, 1], vertical_alignment="bottom")
with header:
    st.title("Case investigation")
    st.markdown('<p class="hero-note">Review the payment, examine the evidence, and decide what happens next.</p>', unsafe_allow_html=True)
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
        st.rerun()
    except (httpx.HTTPError, ValueError):
        st.session_state.setdefault("investigation_costs", []).append(None)
        st.session_state.pop("investigation", None)
        st.error("Investigation unavailable. Please ask an analyst to review the case.")

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
        st.markdown('<div class="section-label">Case notes</div>', unsafe_allow_html=True)
        for note in case["notes"]:
            st.write(note)
        if not case["notes"]:
            st.write("No notes available.")

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
