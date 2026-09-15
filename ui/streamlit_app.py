"""Streamlit client for the Docs Analyzer API. Run the API first: uv run uvicorn app.api:app"""
import os
import time

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")
FILE_TYPES = ["pdf", "docx", "pptx", "xlsx", "html", "md"]

st.set_page_config(page_title="Docs Analyzer")
st.title("Docs Analyzer")

uploaded = st.file_uploader("Upload a document", type=FILE_TYPES)
if uploaded and st.button("Process document", type="primary"):
    response = requests.post(f"{API_URL}/documents", files={"file": (uploaded.name, uploaded.getvalue())}, timeout=120)
    response.raise_for_status()
    st.session_state.doc_id = response.json()["doc_id"]
    st.session_state.messages = []

doc_id = st.session_state.get("doc_id")
if not doc_id:
    st.stop()

try:
    status = requests.get(f"{API_URL}/documents/{doc_id}", timeout=30).json()
except requests.RequestException as exc:
    st.warning(f"API not responding, retrying... ({exc.__class__.__name__})")
    time.sleep(5)
    st.rerun()
details = f"mode: {status.get('mode', '-')}, tokens: {status.get('tokens', '-')}, chunks: {status.get('chunks', '-')}"
st.progress(float(status.get("progress", 0)), text=f"{status['name']}: {status['status']} ({details})")

if status["status"] == "error":
    st.error(status.get("error", "Ingest failed"))
    st.stop()
if status["status"] != "done":
    time.sleep(2)
    st.rerun()


def render_citations(citations: list[dict]) -> None:
    with st.expander(f"Sources ({len(citations)})"):
        for c in citations:
            pages = ", ".join(map(str, c["pages"])) or "-"
            st.markdown(f"**[{c['n']}]** {c['source']}, pages: {pages}")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("citations"):
            render_citations(message["citations"])

if question := st.chat_input("Ask about the document"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Searching the document..."):
        response = requests.post(f"{API_URL}/chat", json={"doc_id": doc_id, "question": question}, timeout=600)
        if response.ok:
            body = response.json()
            st.markdown(body["answer"])
            render_citations(body["citations"])
            st.session_state.messages.append({"role": "assistant", "content": body["answer"], "citations": body["citations"]})
        else:
            st.error(f"{response.status_code}: {response.text}")
