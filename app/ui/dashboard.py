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
st.subheader("Notes")
for note in case["notes"]:
    st.write(note)
st.info("Investigations and recommendations are planned for a later milestone. An analyst remains responsible for decisions.")
