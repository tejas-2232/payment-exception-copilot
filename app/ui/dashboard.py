import os

import httpx
import streamlit as st

API_URL = os.environ.get("CASE_API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="Payment exception cases")
st.title("Payment exception cases")
st.caption("Fictional training data · Read-only prototype")

try:
    response = httpx.get(f"{API_URL}/cases", timeout=5.0)
    response.raise_for_status()
    cases = response.json()
except (httpx.HTTPError, ValueError):
    st.error("Could not load cases. Check that the case API is running.")
    st.stop()

if not cases:
    st.info("No cases are available.")
    st.stop()

case_ids = [case["case_id"] for case in cases]
selected = st.selectbox("Select a case", case_ids)
try:
    response = httpx.get(f"{API_URL}/cases/{selected}", timeout=5.0)
    response.raise_for_status()
    case = response.json()
except (httpx.HTTPError, ValueError):
    st.error("Could not load the selected case.")
    st.stop()

st.subheader(case["exception_message"])
st.write("Status:", case["status"])
st.subheader("Payment context")
st.json(case["payment"])
if case.get("partner_response"):
    st.subheader("Partner response")
    st.write(case["partner_response"])
st.subheader("Notes")
for note in case["notes"]:
    st.write(note)
st.divider()
st.subheader("Investigation")
mode = st.selectbox("Investigation mode", ["offline", "agent"], help="The agent requires a configured model and sends fictional case data to the provider.")
if st.button("Investigate", key=f"investigate-{selected}"):
    try:
        response = httpx.post(f"{API_URL}/investigations", json={"case_id": selected, "mode": mode}, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        st.session_state["investigation"] = result
        st.session_state["investigation_mode"] = mode
    except (httpx.HTTPError, ValueError):
        st.session_state.pop("investigation", None)
        st.error("Investigation is unavailable. Ask an analyst to review the case.")

result = st.session_state.get("investigation")
if result and result["case_id"] == selected and st.session_state.get("investigation_mode") == mode:
    st.write(result["case_summary"])
    st.write("Suggested next steps:")
    for step in result["recommended_next_steps"]:
        st.write("- " + step)
    st.write("Missing information:", ", ".join(result["missing_information"]) or "None identified")
    for uncertainty in result["uncertainties"]:
        st.warning(uncertainty)
    if result.get("tool_activity"):
        st.write("Tools used:", " → ".join(result["tool_activity"]))
    if result.get("case_evidence"):
        st.subheader("Case evidence")
        for source in result["case_evidence"]:
            st.write(f"{source['source_id']}: {source['excerpt']}")
    st.subheader("Procedure evidence")
    if not result["evidence"]:
        st.write("No supporting procedure found.")
    for evidence in result["evidence"]:
        st.markdown(f"**{evidence['document_id']} · {evidence['section']} · version {evidence['version']}**")
        st.write(evidence["excerpt"])
    st.info("Human review required. The analyst verifies the evidence and decides what to do.")
